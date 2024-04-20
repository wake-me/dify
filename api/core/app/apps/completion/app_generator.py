import logging
import os
import threading
import uuid
from collections.abc import Generator
from typing import Any, Union

from flask import Flask, current_app
from pydantic import ValidationError

from core.app.app_config.easy_ui_based_app.model_config.converter import ModelConfigConverter
from core.app.app_config.features.file_upload.manager import FileUploadConfigManager
from core.app.apps.base_app_queue_manager import AppQueueManager, GenerateTaskStoppedException, PublishFrom
from core.app.apps.completion.app_config_manager import CompletionAppConfigManager
from core.app.apps.completion.app_runner import CompletionAppRunner
from core.app.apps.completion.generate_response_converter import CompletionAppGenerateResponseConverter
from core.app.apps.message_based_app_generator import MessageBasedAppGenerator
from core.app.apps.message_based_app_queue_manager import MessageBasedAppQueueManager
from core.app.entities.app_invoke_entities import CompletionAppGenerateEntity, InvokeFrom
from core.file.message_file_parser import MessageFileParser
from core.model_runtime.errors.invoke import InvokeAuthorizationError, InvokeError
from extensions.ext_database import db
from models.account import Account
from models.model import App, EndUser, Message
from services.errors.app import MoreLikeThisDisabledError
from services.errors.message import MessageNotExistsError

logger = logging.getLogger(__name__)


class CompletionAppGenerator(MessageBasedAppGenerator):
    def generate(self, app_model: App,
                user: Union[Account, EndUser],
                args: Any,
                invoke_from: InvokeFrom,
                stream: bool = True) \
            -> Union[dict, Generator[dict, None, None]]:
        """
        生成App响应。

        :param app_model: App模型，代表一个具体的应用。
        :param user: 账户或终端用户，标识请求的发起者。
        :param args: 请求参数，包括查询语句和输入等信息。
        :param invoke_from: 调用来源，标识请求是从哪里发起的。
        :param stream: 是否流式返回结果，默认为True。
        :return: 根据请求配置，返回字典或生成器，包含App的响应数据。

        该方法主要流程如下：
        1. 校验并处理请求参数中的查询字符串和输入。
        2. 获取并验证可能存在的自定义模型配置。
        3. 解析并处理文件参数。
        4. 根据应用模型和可能的自定义配置，生成应用配置。
        5. 初始化生成记录和队列管理器。
        6. 在新线程中启动生成工作。
        7. 根据流式返回的配置，处理并返回响应数据。
        """

        # 校验查询参数必须为字符串
        query = args['query']
        if not isinstance(query, str):
            raise ValueError('query must be a string')

        query = query.replace('\x00', '')
        inputs = args['inputs']

        extras = {}

        # 获取会话信息
        conversation = None

        # 获取应用模型配置
        app_model_config = self._get_app_model_config(
            app_model=app_model,
            conversation=conversation
        )

        # 验证并处理覆盖模型配置的参数
        override_model_config_dict = None
        if args.get('model_config'):
            if invoke_from != InvokeFrom.DEBUGGER:
                raise ValueError('Only in App debug mode can override model config')

            # 验证配置
            override_model_config_dict = CompletionAppConfigManager.config_validate(
                tenant_id=app_model.tenant_id,
                config=args.get('model_config')
            )

        # 解析文件参数
        files = args['files'] if 'files' in args and args['files'] else []
        message_file_parser = MessageFileParser(tenant_id=app_model.tenant_id, app_id=app_model.id)
        file_extra_config = FileUploadConfigManager.convert(override_model_config_dict or app_model_config.to_dict())
        if file_extra_config:
            file_objs = message_file_parser.validate_and_transform_files_arg(
                files,
                file_extra_config,
                user
            )
        else:
            file_objs = []

        # 转换为应用配置
        app_config = CompletionAppConfigManager.get_app_config(
            app_model=app_model,
            app_model_config=app_model_config,
            override_config_dict=override_model_config_dict
        )

        # 初始化应用生成实体
        application_generate_entity = CompletionAppGenerateEntity(
            task_id=str(uuid.uuid4()),
            app_config=app_config,
            model_config=ModelConfigConverter.convert(app_config),
            inputs=self._get_cleaned_inputs(inputs, app_config),
            query=query,
            files=file_objs,
            user_id=user.id,
            stream=stream,
            invoke_from=invoke_from,
            extras=extras
        )

        # 初始化生成记录
        (
            conversation,
            message
        ) = self._init_generate_records(application_generate_entity)

        # 初始化队列管理器
        queue_manager = MessageBasedAppQueueManager(
            task_id=application_generate_entity.task_id,
            user_id=application_generate_entity.user_id,
            invoke_from=application_generate_entity.invoke_from,
            conversation_id=conversation.id,
            app_mode=conversation.mode,
            message_id=message.id
        )

        # 在新线程中启动生成工作
        worker_thread = threading.Thread(target=self._generate_worker, kwargs={
            'flask_app': current_app._get_current_object(),
            'application_generate_entity': application_generate_entity,
            'queue_manager': queue_manager,
            'message_id': message.id,
        })
        worker_thread.start()

        # 根据配置处理并返回响应
        response = self._handle_response(
            application_generate_entity=application_generate_entity,
            queue_manager=queue_manager,
            conversation=conversation,
            message=message,
            user=user,
            stream=stream
        )

        # 转换并返回最终的响应对象
        return CompletionAppGenerateResponseConverter.convert(
            response=response,
            invoke_from=invoke_from
        )

    def _generate_worker(self, flask_app: Flask,
                         application_generate_entity: CompletionAppGenerateEntity,
                         queue_manager: AppQueueManager,
                         message_id: str) -> None:
        """
        在新线程中生成工作器。
        :param flask_app: Flask应用实例
        :param application_generate_entity: 应用生成实体，包含生成任务的具体信息
        :param queue_manager: 队列管理器，用于任务的发布和管理
        :param message_id: 消息ID，用于标识特定的消息
        :return: 无返回值
        """
        with flask_app.app_context():
            try:
                # 根据消息ID获取消息内容
                message = self._get_message(message_id)

                # 初始化并运行聊天机器人应用
                runner = CompletionAppRunner()
                runner.run(
                    application_generate_entity=application_generate_entity,
                    queue_manager=queue_manager,
                    message=message
                )
            except GenerateTaskStoppedException:
                # 生成任务被停止，直接跳过处理
                pass
            except InvokeAuthorizationError:
                # 调用授权错误，发布错误消息
                queue_manager.publish_error(
                    InvokeAuthorizationError('Incorrect API key provided'),
                    PublishFrom.APPLICATION_MANAGER
                )
            except ValidationError as e:
                # 验证错误，发布错误消息
                logger.exception("Validation Error when generating")
                queue_manager.publish_error(e, PublishFrom.APPLICATION_MANAGER)
            except (ValueError, InvokeError) as e:
                if os.environ.get("DEBUG") and os.environ.get("DEBUG").lower() == 'true':
                    logger.exception("Error when generating")
                queue_manager.publish_error(e, PublishFrom.APPLICATION_MANAGER)
            except Exception as e:
                # 未知错误，记录异常并发布错误消息
                logger.exception("Unknown Error when generating")
                queue_manager.publish_error(e, PublishFrom.APPLICATION_MANAGER)
            finally:
                # 确保数据库会话关闭
                db.session.close()

    def generate_more_like_this(self, app_model: App,
                                message_id: str,
                                user: Union[Account, EndUser],
                                invoke_from: InvokeFrom,
                                stream: bool = True) \
            -> Union[dict, Generator[dict, None, None]]:
        """
        生成类似于指定消息的回复。

        :param app_model: 应用模型，定义了应用的配置和行为。
        :param message_id: 消息ID，用于查找原始消息。
        :param user: 账户或终端用户，指定消息的发送者。
        :param invoke_from: 调用来源，标识消息生成的触发源。
        :param stream: 是否流式返回结果，默认为True。
        :return: 根据stream参数，返回字典或生成器，包含生成的消息回复信息。
        """
        # 根据提供的条件查询原始消息
        message = db.session.query(Message).filter(
            Message.id == message_id,
            Message.app_id == app_model.id,
            Message.from_source == ('api' if isinstance(user, EndUser) else 'console'),
            Message.from_end_user_id == (user.id if isinstance(user, EndUser) else None),
            Message.from_account_id == (user.id if isinstance(user, Account) else None),
        ).first()

        # 如果查询不到对应消息，抛出异常
        if not message:
            raise MessageNotExistsError()

        # 获取当前应用模型的配置，并检查是否启用了"更多类似此"的选项
        current_app_model_config = app_model.app_model_config
        more_like_this = current_app_model_config.more_like_this_dict

        if not current_app_model_config.more_like_this or more_like_this.get("enabled", False) is False:
            raise MoreLikeThisDisabledError()

        # 处理模型配置，以用于生成回复
        app_model_config = message.app_model_config
        override_model_config_dict = app_model_config.to_dict()
        model_dict = override_model_config_dict['model']
        completion_params = model_dict.get('completion_params')
        completion_params['temperature'] = 0.9  # 设置生成的随机性
        model_dict['completion_params'] = completion_params
        override_model_config_dict['model'] = model_dict

        # 解析文件，准备文件参数
        message_file_parser = MessageFileParser(tenant_id=app_model.tenant_id, app_id=app_model.id)
        file_extra_config = FileUploadConfigManager.convert(override_model_config_dict or app_model_config.to_dict())
        if file_extra_config:
            file_objs = message_file_parser.validate_and_transform_files_arg(
                message.files,
                file_extra_config,
                user
            )
        else:
            file_objs = []

        # 将处理后的配置转换为应用配置
        app_config = CompletionAppConfigManager.get_app_config(
            app_model=app_model,
            app_model_config=app_model_config,
            override_config_dict=override_model_config_dict
        )

        # 初始化应用生成实体
        application_generate_entity = CompletionAppGenerateEntity(
            task_id=str(uuid.uuid4()),
            app_config=app_config,
            model_config=ModelConfigConverter.convert(app_config),
            inputs=message.inputs,
            query=message.query,
            files=file_objs,
            user_id=user.id,
            stream=stream,
            invoke_from=invoke_from,
            extras={}
        )

        # 初始化生成记录
        (
            conversation,
            message
        ) = self._init_generate_records(application_generate_entity)

        # 初始化队列管理器
        queue_manager = MessageBasedAppQueueManager(
            task_id=application_generate_entity.task_id,
            user_id=application_generate_entity.user_id,
            invoke_from=application_generate_entity.invoke_from,
            conversation_id=conversation.id,
            app_mode=conversation.mode,
            message_id=message.id
        )

        # 启动新线程处理生成任务
        worker_thread = threading.Thread(target=self._generate_worker, kwargs={
            'flask_app': current_app._get_current_object(),
            'application_generate_entity': application_generate_entity,
            'queue_manager': queue_manager,
            'message_id': message.id,
        })
        worker_thread.start()

        # 根据stream参数处理并返回响应
        response = self._handle_response(
            application_generate_entity=application_generate_entity,
            queue_manager=queue_manager,
            conversation=conversation,
            message=message,
            user=user,
            stream=stream
        )

        # 转换响应格式，返回给调用者
        return CompletionAppGenerateResponseConverter.convert(
            response=response,
            invoke_from=invoke_from
        )
