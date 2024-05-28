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
from core.app.apps.chat.app_config_manager import ChatAppConfigManager
from core.app.apps.chat.app_runner import ChatAppRunner
from core.app.apps.chat.generate_response_converter import ChatAppGenerateResponseConverter
from core.app.apps.message_based_app_generator import MessageBasedAppGenerator
from core.app.apps.message_based_app_queue_manager import MessageBasedAppQueueManager
from core.app.entities.app_invoke_entities import ChatAppGenerateEntity, InvokeFrom
from core.file.message_file_parser import MessageFileParser
from core.model_runtime.errors.invoke import InvokeAuthorizationError, InvokeError
from extensions.ext_database import db
from models.account import Account
from models.model import App, EndUser

logger = logging.getLogger(__name__)


class ChatAppGenerator(MessageBasedAppGenerator):
    def generate(self, app_model: App,
                user: Union[Account, EndUser],
                args: Any,
                invoke_from: InvokeFrom,
                stream: bool = True) \
            -> Union[dict, Generator[dict, None, None]]:
        """
        生成App响应。

        :param app_model: App模型，代表一个应用。
        :param user: 账户或终端用户，标识请求的发起者。
        :param args: 请求参数，包括查询内容和输入等。
        :param invoke_from: 调用来源，标识请求是从哪里发起的。
        :param stream: 是否流式返回结果，默认为True。
        :return: 根据请求设置，可能返回字典或生成器，其中包含App的响应信息。
        """
        # 校验查询参数
        if not args.get('query'):
            raise ValueError('query is required')

        query = args['query']
        if not isinstance(query, str):
            raise ValueError('query must be a string')

        query = query.replace('\x00', '')
        inputs = args['inputs']

        # 准备额外信息，如会话名称生成策略
        extras = {
            "auto_generate_conversation_name": args['auto_generate_name'] if 'auto_generate_name' in args else True
        }

        # 尝试根据会话ID获取会话
        conversation = None
        if args.get('conversation_id'):
            conversation = self._get_conversation_by_user(app_model, args.get('conversation_id'), user)

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
            override_model_config_dict = ChatAppConfigManager.config_validate(
                tenant_id=app_model.tenant_id,
                config=args.get('model_config')
            )

        # parse files
        files = args['files'] if args.get('files') else []
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
        app_config = ChatAppConfigManager.get_app_config(
            app_model=app_model,
            app_model_config=app_model_config,
            conversation=conversation,
            override_config_dict=override_model_config_dict
        )

        # 初始化应用生成实体
        application_generate_entity = ChatAppGenerateEntity(
            task_id=str(uuid.uuid4()),
            app_config=app_config,
            model_config=ModelConfigConverter.convert(app_config),
            conversation_id=conversation.id if conversation else None,
            inputs=conversation.inputs if conversation else self._get_cleaned_inputs(inputs, app_config),
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
        ) = self._init_generate_records(application_generate_entity, conversation)

        # 初始化队列管理器
        queue_manager = MessageBasedAppQueueManager(
            task_id=application_generate_entity.task_id,
            user_id=application_generate_entity.user_id,
            invoke_from=application_generate_entity.invoke_from,
            conversation_id=conversation.id,
            app_mode=conversation.mode,
            message_id=message.id
        )

        # 启动工作线程处理生成任务
        worker_thread = threading.Thread(target=self._generate_worker, kwargs={
            'flask_app': current_app._get_current_object(),
            'application_generate_entity': application_generate_entity,
            'queue_manager': queue_manager,
            'conversation_id': conversation.id,
            'message_id': message.id,
        })
        worker_thread.start()

        # 根据流式返回设置处理响应
        response = self._handle_response(
            application_generate_entity=application_generate_entity,
            queue_manager=queue_manager,
            conversation=conversation,
            message=message,
            user=user,
            stream=stream
        )

        # 转换响应格式后返回
        return ChatAppGenerateResponseConverter.convert(
            response=response,
            invoke_from=invoke_from
        )

    def _generate_worker(self, flask_app: Flask,
                         application_generate_entity: ChatAppGenerateEntity,
                         queue_manager: AppQueueManager,
                         conversation_id: str,
                         message_id: str) -> None:
        """
        在新线程中生成工作器。
        :param flask_app: Flask应用实例
        :param application_generate_entity: 应用生成实体，包含生成任务所需的数据和逻辑
        :param queue_manager: 队列管理器，用于任务的发布和管理
        :param conversation_id: 会话ID
        :param message_id: 消息ID
        :return: 无返回值
        """
        with flask_app.app_context():
            try:
                # 获取会话和消息
                conversation = self._get_conversation(conversation_id)
                message = self._get_message(message_id)

                # 实例化并运行聊天应用
                runner = ChatAppRunner()
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
