import logging
import os
import threading
import uuid
from collections.abc import Generator
from typing import Union

from flask import Flask, current_app
from pydantic import ValidationError

from core.app.app_config.features.file_upload.manager import FileUploadConfigManager
from core.app.apps.base_app_generator import BaseAppGenerator
from core.app.apps.base_app_queue_manager import AppQueueManager, GenerateTaskStoppedException, PublishFrom
from core.app.apps.workflow.app_config_manager import WorkflowAppConfigManager
from core.app.apps.workflow.app_queue_manager import WorkflowAppQueueManager
from core.app.apps.workflow.app_runner import WorkflowAppRunner
from core.app.apps.workflow.generate_response_converter import WorkflowAppGenerateResponseConverter
from core.app.apps.workflow.generate_task_pipeline import WorkflowAppGenerateTaskPipeline
from core.app.entities.app_invoke_entities import InvokeFrom, WorkflowAppGenerateEntity
from core.app.entities.task_entities import WorkflowAppBlockingResponse, WorkflowAppStreamResponse
from core.file.message_file_parser import MessageFileParser
from core.model_runtime.errors.invoke import InvokeAuthorizationError, InvokeError
from extensions.ext_database import db
from models.account import Account
from models.model import App, EndUser
from models.workflow import Workflow

logger = logging.getLogger(__name__)


class WorkflowAppGenerator(BaseAppGenerator):
    def generate(self, app_model: App,
                workflow: Workflow,
                user: Union[Account, EndUser],
                args: dict,
                invoke_from: InvokeFrom,
                stream: bool = True) \
            -> Union[dict, Generator[dict, None, None]]:
        """
        生成App响应。

        :param app_model: App模型，代表一个应用。
        :param workflow: 工作流，定义了应用的处理流程。
        :param user: 账户或终端用户，执行操作的用户。
        :param args: 请求参数。
        :param invoke_from: 调用来源。
        :param stream: 是否流式返回结果，默认为True。
        :return: 返回一个字典或生成器，包含应用的响应信息。
        """
        # 解析输入参数
        inputs = args['inputs']

        # 解析文件参数
        files = args['files'] if 'files' in args and args['files'] else []
        message_file_parser = MessageFileParser(tenant_id=app_model.tenant_id, app_id=app_model.id)
        file_extra_config = FileUploadConfigManager.convert(workflow.features_dict, is_vision=False)
        if file_extra_config:
            file_objs = message_file_parser.validate_and_transform_files_arg(
                files,
                file_extra_config,
                user
            )
        else:
            file_objs = []

        # 转换为应用配置
        app_config = WorkflowAppConfigManager.get_app_config(
            app_model=app_model,
            workflow=workflow
        )

        # 初始化应用生成实体
        application_generate_entity = WorkflowAppGenerateEntity(
            task_id=str(uuid.uuid4()),
            app_config=app_config,
            inputs=self._get_cleaned_inputs(inputs, app_config),
            files=file_objs,
            user_id=user.id,
            stream=stream,
            invoke_from=invoke_from
        )

        # 初始化队列管理器
        queue_manager = WorkflowAppQueueManager(
            task_id=application_generate_entity.task_id,
            user_id=application_generate_entity.user_id,
            invoke_from=application_generate_entity.invoke_from,
            app_mode=app_model.mode
        )

        # 在新线程中执行工作
        worker_thread = threading.Thread(target=self._generate_worker, kwargs={
            'flask_app': current_app._get_current_object(),
            'application_generate_entity': application_generate_entity,
            'queue_manager': queue_manager
        })
        worker_thread.start()

        # 处理响应或返回流式生成器
        response = self._handle_response(
            application_generate_entity=application_generate_entity,
            workflow=workflow,
            queue_manager=queue_manager,
            user=user,
            stream=stream
        )

        # 转换响应格式
        return WorkflowAppGenerateResponseConverter.convert(
            response=response,
            invoke_from=invoke_from
        )

    def _generate_worker(self, flask_app: Flask,
                         application_generate_entity: WorkflowAppGenerateEntity,
                         queue_manager: AppQueueManager) -> None:
        """
        在新线程中生成worker。
        :param flask_app: Flask应用实例，用于提供应用上下文。
        :param application_generate_entity: 用于工作流应用生成的实体对象。
        :param queue_manager: 队列管理器，用于任务的发布和管理。
        :return: 无返回值。
        """
        with flask_app.app_context():
            try:
                # 初始化工作流应用运行器并执行生成任务
                runner = WorkflowAppRunner()
                runner.run(
                    application_generate_entity=application_generate_entity,
                    queue_manager=queue_manager
                )
            except GenerateTaskStoppedException:
                # 生成任务被停止，直接跳过处理
                pass
            except InvokeAuthorizationError:
                # 授权错误，发布错误信息到队列
                queue_manager.publish_error(
                    InvokeAuthorizationError('Incorrect API key provided'),
                    PublishFrom.APPLICATION_MANAGER
                )
            except ValidationError as e:
                # 验证错误，发布错误信息到队列
                logger.exception("Validation Error when generating")
                queue_manager.publish_error(e, PublishFrom.APPLICATION_MANAGER)
            except (ValueError, InvokeError) as e:
                if os.environ.get("DEBUG") and os.environ.get("DEBUG").lower() == 'true':
                    logger.exception("Error when generating")
                queue_manager.publish_error(e, PublishFrom.APPLICATION_MANAGER)
            except Exception as e:
                # 未知错误，记录异常并发布错误信息到队列
                logger.exception("Unknown Error when generating")
                queue_manager.publish_error(e, PublishFrom.APPLICATION_MANAGER)
            finally:
                # 清理数据库会话
                db.session.remove()

    def _handle_response(self, application_generate_entity: WorkflowAppGenerateEntity,
                        workflow: Workflow,
                        queue_manager: AppQueueManager,
                        user: Union[Account, EndUser],
                        stream: bool = False) -> Union[
            WorkflowAppBlockingResponse,
            Generator[WorkflowAppStreamResponse, None, None]
        ]:
            """
            处理响应。
            :param application_generate_entity: 用于工作流应用生成的实体
            :param workflow: 工作流实例
            :param queue_manager: 队列管理器，用于管理任务队列
            :param user: 账户或终端用户，标识请求的发起者
            :param stream: 是否采用流式处理，默认为False
            :return: 根据流式处理标志返回不同的响应类型，如果stream为True，则返回一个生成器对象；否则返回一个阻塞响应对象
            """
            # 初始化生成任务管道
            generate_task_pipeline = WorkflowAppGenerateTaskPipeline(
                application_generate_entity=application_generate_entity,
                workflow=workflow,
                queue_manager=queue_manager,
                user=user,
                stream=stream
            )

            try:
                # 处理生成任务，并返回响应
                return generate_task_pipeline.process()
            except ValueError as e:
                # 忽略"文件被关闭"的错误，其它错误记录日志并抛出
                if e.args[0] == "I/O operation on closed file.":  # 忽略此错误
                    raise GenerateTaskStoppedException()
                else:
                    logger.exception(e)
                    raise e
