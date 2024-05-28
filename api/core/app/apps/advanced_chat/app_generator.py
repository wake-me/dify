import logging
import os
import threading
import uuid
from collections.abc import Generator
from typing import Union

from flask import Flask, current_app
from pydantic import ValidationError

from core.app.app_config.features.file_upload.manager import FileUploadConfigManager
from core.app.apps.advanced_chat.app_config_manager import AdvancedChatAppConfigManager
from core.app.apps.advanced_chat.app_runner import AdvancedChatAppRunner
from core.app.apps.advanced_chat.generate_response_converter import AdvancedChatAppGenerateResponseConverter
from core.app.apps.advanced_chat.generate_task_pipeline import AdvancedChatAppGenerateTaskPipeline
from core.app.apps.base_app_queue_manager import AppQueueManager, GenerateTaskStoppedException, PublishFrom
from core.app.apps.message_based_app_generator import MessageBasedAppGenerator
from core.app.apps.message_based_app_queue_manager import MessageBasedAppQueueManager
from core.app.entities.app_invoke_entities import AdvancedChatAppGenerateEntity, InvokeFrom
from core.app.entities.task_entities import ChatbotAppBlockingResponse, ChatbotAppStreamResponse
from core.file.message_file_parser import MessageFileParser
from core.model_runtime.errors.invoke import InvokeAuthorizationError, InvokeError
from extensions.ext_database import db
from models.account import Account
from models.model import App, Conversation, EndUser, Message
from models.workflow import Workflow

logger = logging.getLogger(__name__)


class AdvancedChatAppGenerator(MessageBasedAppGenerator):
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
        :param workflow: 工作流，定义了应用处理请求的流程。
        :param user: 账户或终端用户，表示发起请求的用户。
        :param args: 请求参数。
        :param invoke_from: 调用来源。
        :param stream: 是否流式返回结果，默认为True。
        :return: 根据流式返回设置，可能返回字典或生成器。

        该方法主要负责处理应用程序的生成流程，包括解析查询、处理文件、初始化会话和生成记录、启动工作线程，
        以及最终返回处理结果。
        """

        # 校验查询参数
        if not args.get('query'):
            raise ValueError('query is required')

        query = args['query']
        if not isinstance(query, str):
            raise ValueError('query must be a string')

        query = query.replace('\x00', '')
        inputs = args['inputs']

        # 额外参数初始化
        extras = {
            "auto_generate_conversation_name": args['auto_generate_name'] if 'auto_generate_name' in args else False
        }

        # 尝试根据会话ID获取会话
        conversation = None
        if args.get('conversation_id'):
            conversation = self._get_conversation_by_user(app_model, args.get('conversation_id'), user)

        # parse files
        files = args['files'] if args.get('files') else []
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
        app_config = AdvancedChatAppConfigManager.get_app_config(
            app_model=app_model,
            workflow=workflow
        )

        # 初始化应用生成实体
        application_generate_entity = AdvancedChatAppGenerateEntity(
            task_id=str(uuid.uuid4()),
            app_config=app_config,
            conversation_id=conversation.id if conversation else None,
            inputs=conversation.inputs if conversation else self._get_cleaned_inputs(inputs, app_config),
            query=query,
            files=file_objs,
            user_id=user.id,
            stream=stream,
            invoke_from=invoke_from,
            extras=extras
        )

        return self._generate(
            app_model=app_model,
            workflow=workflow,
            user=user,
            invoke_from=invoke_from,
            application_generate_entity=application_generate_entity,
            conversation=conversation,
            stream=stream
        )
    
    def single_iteration_generate(self, app_model: App,
                                  workflow: Workflow,
                                  node_id: str,
                                  user: Account,
                                  args: dict,
                                  stream: bool = True) \
            -> Union[dict, Generator[dict, None, None]]:
        """
        Generate App response.

        :param app_model: App
        :param workflow: Workflow
        :param user: account or end user
        :param args: request args
        :param invoke_from: invoke from source
        :param stream: is stream
        """
        if not node_id:
            raise ValueError('node_id is required')
        
        if args.get('inputs') is None:
            raise ValueError('inputs is required')
        
        extras = {
            "auto_generate_conversation_name": False
        }

        # get conversation
        conversation = None
        if args.get('conversation_id'):
            conversation = self._get_conversation_by_user(app_model, args.get('conversation_id'), user)

        # convert to app config
        app_config = AdvancedChatAppConfigManager.get_app_config(
            app_model=app_model,
            workflow=workflow
        )

        # init application generate entity
        application_generate_entity = AdvancedChatAppGenerateEntity(
            task_id=str(uuid.uuid4()),
            app_config=app_config,
            conversation_id=conversation.id if conversation else None,
            inputs={},
            query='',
            files=[],
            user_id=user.id,
            stream=stream,
            invoke_from=InvokeFrom.DEBUGGER,
            extras=extras,
            single_iteration_run=AdvancedChatAppGenerateEntity.SingleIterationRunEntity(
                node_id=node_id,
                inputs=args['inputs']
            )
        )

        return self._generate(
            app_model=app_model,
            workflow=workflow,
            user=user,
            invoke_from=InvokeFrom.DEBUGGER,
            application_generate_entity=application_generate_entity,
            conversation=conversation,
            stream=stream
        )

    def _generate(self, app_model: App,
                 workflow: Workflow,
                 user: Union[Account, EndUser],
                 invoke_from: InvokeFrom,
                 application_generate_entity: AdvancedChatAppGenerateEntity,
                 conversation: Conversation = None,
                 stream: bool = True) \
            -> Union[dict, Generator[dict, None, None]]:
        is_first_conversation = False
        if not conversation:
            is_first_conversation = True

        # 初始化生成记录
        (
            conversation,
            message
        ) = self._init_generate_records(application_generate_entity, conversation)

        if is_first_conversation:
            # 更新会话特征
            conversation.override_model_configs = workflow.features
            db.session.commit()
            db.session.refresh(conversation)

        # 初始化队列管理器
        queue_manager = MessageBasedAppQueueManager(
            task_id=application_generate_entity.task_id,
            user_id=application_generate_entity.user_id,
            invoke_from=application_generate_entity.invoke_from,
            conversation_id=conversation.id,
            app_mode=conversation.mode,
            message_id=message.id
        )

        # 启动工作线程
        worker_thread = threading.Thread(target=self._generate_worker, kwargs={
            'flask_app': current_app._get_current_object(),
            'application_generate_entity': application_generate_entity,
            'queue_manager': queue_manager,
            'conversation_id': conversation.id,
            'message_id': message.id,
        })
        worker_thread.start()

        # 处理并返回响应
        response = self._handle_advanced_chat_response(
            application_generate_entity=application_generate_entity,
            workflow=workflow,
            queue_manager=queue_manager,
            conversation=conversation,
            message=message,
            user=user,
            stream=stream
        )

        return AdvancedChatAppGenerateResponseConverter.convert(
            response=response,
            invoke_from=invoke_from
        )

    def _generate_worker(self, flask_app: Flask,
                         application_generate_entity: AdvancedChatAppGenerateEntity,
                         queue_manager: AppQueueManager,
                         conversation_id: str,
                         message_id: str) -> None:
        """
        在新线程中生成工作器。
        :param flask_app: Flask应用实例
        :param application_generate_entity: 应用生成实体，包含生成所需数据
        :param queue_manager: 队列管理器，用于任务调度和错误处理
        :param conversation_id: 会话ID
        :param message_id: 消息ID
        :return: 无返回值
        """
        with flask_app.app_context():
            try:
                runner = AdvancedChatAppRunner()
                if application_generate_entity.single_iteration_run:
                    single_iteration_run = application_generate_entity.single_iteration_run
                    runner.single_iteration_run(
                        app_id=application_generate_entity.app_config.app_id,
                        workflow_id=application_generate_entity.app_config.workflow_id,
                        queue_manager=queue_manager,
                        inputs=single_iteration_run.inputs,
                        node_id=single_iteration_run.node_id,
                        user_id=application_generate_entity.user_id
                    )
                else:
                    # get conversation and message
                    conversation = self._get_conversation(conversation_id)
                    message = self._get_message(message_id)

                    # chatbot app
                    runner = AdvancedChatAppRunner()
                    runner.run(
                        application_generate_entity=application_generate_entity,
                        queue_manager=queue_manager,
                        conversation=conversation,
                        message=message
                    )
            except GenerateTaskStoppedException:
                # 生成任务被停止，直接跳过
                pass
            except InvokeAuthorizationError:
                # 调用授权错误，发布错误信息
                queue_manager.publish_error(
                    InvokeAuthorizationError('Incorrect API key provided'),
                    PublishFrom.APPLICATION_MANAGER
                )
            except ValidationError as e:
                # 验证错误，记录异常并发布错误信息
                logger.exception("Validation Error when generating")
                queue_manager.publish_error(e, PublishFrom.APPLICATION_MANAGER)
            except (ValueError, InvokeError) as e:
                if os.environ.get("DEBUG") and os.environ.get("DEBUG").lower() == 'true':
                    logger.exception("Error when generating")
                queue_manager.publish_error(e, PublishFrom.APPLICATION_MANAGER)
            except Exception as e:
                # 未知错误，记录异常并发布错误信息
                logger.exception("Unknown Error when generating")
                queue_manager.publish_error(e, PublishFrom.APPLICATION_MANAGER)
            finally:
                # 关闭数据库会话
                db.session.close()

    def _handle_advanced_chat_response(self, application_generate_entity: AdvancedChatAppGenerateEntity,
                                        workflow: Workflow,
                                        queue_manager: AppQueueManager,
                                        conversation: Conversation,
                                        message: Message,
                                        user: Union[Account, EndUser],
                                        stream: bool = False) \
                -> Union[ChatbotAppBlockingResponse, Generator[ChatbotAppStreamResponse, None, None]]:
            """
            处理高级聊天响应。
            
            :param application_generate_entity: 应用生成实体，包含聊天应用的生成配置信息。
            :param workflow: 工作流，定义了处理聊天请求的步骤序列。
            :param queue_manager: 队列管理器，用于管理聊天请求的队列。
            :param conversation: 对话，表示用户和聊天机器人之间的一次会话。
            :param message: 消息，用户发送的消息或聊天机器人回复的消息。
            :param user: 账户或终端用户，标识发起聊天请求的用户。
            :param stream: 是否为流式响应，默认为False。如果为True，则响应将以流的形式返回。
            :return: 返回一个聊天应用的阻塞响应或一个生成器，用于逐个返回流式响应。
            """
            # 初始化生成任务管道
            generate_task_pipeline = AdvancedChatAppGenerateTaskPipeline(
                application_generate_entity=application_generate_entity,
                workflow=workflow,
                queue_manager=queue_manager,
                conversation=conversation,
                message=message,
                user=user,
                stream=stream
            )

            try:
                # 处理生成任务，并返回结果
                return generate_task_pipeline.process()
            except ValueError as e:
                # 忽略"文件被关闭"的错误
                if e.args[0] == "I/O operation on closed file.":  
                    raise GenerateTaskStoppedException()
                else:
                    # 记录其他异常，并抛出
                    logger.exception(e)
                    raise e
