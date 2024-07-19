import json
import logging
from collections.abc import Generator
from typing import Optional, Union

from sqlalchemy import and_

from core.app.app_config.entities import EasyUIBasedAppModelConfigFrom
from core.app.apps.base_app_generator import BaseAppGenerator
from core.app.apps.base_app_queue_manager import AppQueueManager, GenerateTaskStoppedException
from core.app.entities.app_invoke_entities import (
    AdvancedChatAppGenerateEntity,
    AgentChatAppGenerateEntity,
    AppGenerateEntity,
    ChatAppGenerateEntity,
    CompletionAppGenerateEntity,
    InvokeFrom,
)
from core.app.entities.task_entities import (
    ChatbotAppBlockingResponse,
    ChatbotAppStreamResponse,
    CompletionAppBlockingResponse,
    CompletionAppStreamResponse,
)
from core.app.task_pipeline.easy_ui_based_generate_task_pipeline import EasyUIBasedGenerateTaskPipeline
from core.prompt.utils.prompt_template_parser import PromptTemplateParser
from extensions.ext_database import db
from models.account import Account
from models.model import App, AppMode, AppModelConfig, Conversation, EndUser, Message, MessageFile
from services.errors.app_model_config import AppModelConfigBrokenError
from services.errors.conversation import ConversationCompletedError, ConversationNotExistsError

logger = logging.getLogger(__name__)


class MessageBasedAppGenerator(BaseAppGenerator):

    def _handle_response(
        self, application_generate_entity: Union[
            ChatAppGenerateEntity,
            CompletionAppGenerateEntity,
            AgentChatAppGenerateEntity,
            AdvancedChatAppGenerateEntity
        ],
        queue_manager: AppQueueManager,
        conversation: Conversation,
        message: Message,
        user: Union[Account, EndUser],
        stream: bool = False,
    ) -> Union[
        ChatbotAppBlockingResponse,
        CompletionAppBlockingResponse,
        Generator[Union[ChatbotAppStreamResponse, CompletionAppStreamResponse], None, None]
    ]:
        """
        处理响应。
        
        :param application_generate_entity: 应用生成实体，代表不同类型的对话应用生成的实体。
        :param queue_manager: 队列管理器，用于管理应用生成实体的队列。
        :param conversation: 对话上下文，包含对话的相关信息。
        :param message: 消息对象，代表用户发送的消息或系统消息。
        :param user: 用户对象，可以是账户信息或终端用户信息。
        :param stream: 是否为流式响应，默认为False。如果为True，则响应将以流的形式返回。
        :return: 根据流式参数stream的不同，返回不同的响应类型。要么是阻塞响应，要么是生成器形式的流式响应。
        """
        # 初始化生成任务管道
        generate_task_pipeline = EasyUIBasedGenerateTaskPipeline(
            application_generate_entity=application_generate_entity,
            queue_manager=queue_manager,
            conversation=conversation,
            message=message,
            user=user,
            stream=stream
        )

        try:
            # 处理生成任务，并返回响应
            return generate_task_pipeline.process()
        except ValueError as e:
            # 忽略"文件被关闭"的错误，其它错误记录日志并抛出
            if e.args[0] == "I/O operation on closed file.":  # 忽略该错误
                raise GenerateTaskStoppedException()
            else:
                logger.exception(e)
                raise e

    def _get_conversation_by_user(self, app_model: App, conversation_id: str,
                                user: Union[Account, EndUser]) -> Conversation:
        """
        根据用户和对话ID获取对话对象。
        
        :param app_model: 应用模型，表示特定的应用。
        :param conversation_id: 对话的唯一标识符。
        :param user: 参与对话的用户，可以是Account（后台账户）或EndUser（终端用户）。
        :return: 返回匹配的Conversation对象。
        """
        # 构建对话查询条件
        conversation_filter = [
            Conversation.id == conversation_id,
            Conversation.app_id == app_model.id,
            Conversation.status == 'normal'
        ]

        # 根据用户类型添加查询条件
        if isinstance(user, Account):
            conversation_filter.append(Conversation.from_account_id == user.id)
        else:
            conversation_filter.append(Conversation.from_end_user_id == user.id if user else None)

        # 执行数据库查询
        conversation = db.session.query(Conversation).filter(and_(*conversation_filter)).first()

        # 查询结果为空时抛出对话不存在异常
        if not conversation:
            raise ConversationNotExistsError()

        # 对话状态不为'normal'时抛出对话已完成异常
        if conversation.status != 'normal':
            raise ConversationCompletedError()

        return conversation

    def _get_app_model_config(self, app_model: App,
                            conversation: Optional[Conversation] = None) \
            -> AppModelConfig:
        """
        获取应用模型的配置信息。
        
        :param app_model: App模型对象，代表一个具体的应用。
        :param conversation: 可选的对话对象。如果提供，将尝试从对话中获取应用模型配置。
        :return: 返回一个AppModelConfig对象，代表应用模型的配置。
        """
        if conversation:
            # 如果提供了对话对象，尝试从数据库中查询对应的配置
            app_model_config = db.session.query(AppModelConfig).filter(
                AppModelConfig.id == conversation.app_model_config_id,
                AppModelConfig.app_id == app_model.id
            ).first()

            if not app_model_config:
                # 如果查询不到配置，抛出异常
                raise AppModelConfigBrokenError()
        else:
            # 如果没有提供对话对象，从app_model中直接获取配置
            if app_model.app_model_config_id is None:
                # 如果app_model中没有配置ID，抛出异常
                raise AppModelConfigBrokenError()

            app_model_config = app_model.app_model_config

            if not app_model_config:
                # 如果app_model中配置为空，抛出异常
                raise AppModelConfigBrokenError()

        return app_model_config

    def _init_generate_records(self,
                                application_generate_entity: Union[
                                    ChatAppGenerateEntity,
                                    CompletionAppGenerateEntity,
                                    AgentChatAppGenerateEntity,
                                    AdvancedChatAppGenerateEntity
                                ],
                                conversation: Optional[Conversation] = None) \
                -> tuple[Conversation, Message]:
        """
        初始化生成记录
        :param application_generate_entity: 应用生成实体，包含应用配置和用户信息等
        :return: 返回一个元组，包含对话和消息实体
        """
        # 获取应用配置
        app_config = application_generate_entity.app_config

        # 根据调用来源设置用户ID和账号ID
        end_user_id = None
        account_id = None
        if application_generate_entity.invoke_from in [InvokeFrom.WEB_APP, InvokeFrom.SERVICE_API]:
            from_source = 'api'
            end_user_id = application_generate_entity.user_id
        else:
            from_source = 'console'
            account_id = application_generate_entity.user_id

        # 根据应用生成实体类型获取模型配置信息
        if isinstance(application_generate_entity, AdvancedChatAppGenerateEntity):
            app_model_config_id = None
            override_model_configs = None
            model_provider = None
            model_id = None
        else:
            app_model_config_id = app_config.app_model_config_id
            model_provider = application_generate_entity.model_conf.provider
            model_id = application_generate_entity.model_conf.model
            override_model_configs = None
            if app_config.app_model_config_from == EasyUIBasedAppModelConfigFrom.ARGS \
                    and app_config.app_mode in [AppMode.AGENT_CHAT, AppMode.CHAT, AppMode.COMPLETION]:
                override_model_configs = app_config.app_model_config_dict

        # 获取对话介绍
        introduction = self._get_conversation_introduction(application_generate_entity)

        # 如果对话实体未提供，则创建新的对话实体并保存到数据库
        if not conversation:
            conversation = Conversation(
                # 对话相关字段初始化
                app_id=app_config.app_id,
                app_model_config_id=app_model_config_id,
                model_provider=model_provider,
                model_id=model_id,
                override_model_configs=json.dumps(override_model_configs) if override_model_configs else None,
                mode=app_config.app_mode.value,
                name='New conversation',
                inputs=application_generate_entity.inputs,
                introduction=introduction,
                system_instruction="",
                system_instruction_tokens=0,
                status='normal',
                invoke_from=application_generate_entity.invoke_from.value,
                from_source=from_source,
                from_end_user_id=end_user_id,
                from_account_id=account_id,
            )

            db.session.add(conversation)
            db.session.commit()
            db.session.refresh(conversation)

        # 创建消息实体并保存到数据库
        message = Message(
            # 消息相关字段初始化
            app_id=app_config.app_id,
            model_provider=model_provider,
            model_id=model_id,
            override_model_configs=json.dumps(override_model_configs) if override_model_configs else None,
            conversation_id=conversation.id,
            inputs=application_generate_entity.inputs,
            query=application_generate_entity.query or "",
            message="",
            message_tokens=0,
            message_unit_price=0,
            message_price_unit=0,
            answer="",
            answer_tokens=0,
            answer_unit_price=0,
            answer_price_unit=0,
            provider_response_latency=0,
            total_price=0,
            currency='USD',
            invoke_from=application_generate_entity.invoke_from.value,
            from_source=from_source,
            from_end_user_id=end_user_id,
            from_account_id=account_id
        )

        db.session.add(message)
        db.session.commit()
        db.session.refresh(message)

        # 如果存在文件信息，则为消息添加文件附件
        for file in application_generate_entity.files:
            message_file = MessageFile(
                message_id=message.id,
                type=file.type.value,
                transfer_method=file.transfer_method.value,
                belongs_to='user',
                url=file.url,
                upload_file_id=file.related_id,
                created_by_role=('account' if account_id else 'end_user'),
                created_by=account_id or end_user_id,
            )
            db.session.add(message_file)
            db.session.commit()

        return conversation, message

    def _get_conversation_introduction(self, application_generate_entity: AppGenerateEntity) -> str:
        """
        获取对话介绍
        :param application_generate_entity: 应用生成实体，包含应用配置和输入信息
        :return: 对话介绍文本
        """
        # 获取应用配置
        app_config = application_generate_entity.app_config
        # 尝试从应用配置的额外特性中获取开场白
        introduction = app_config.additional_features.opening_statement

        if introduction:
            try:
                # 获取输入参数
                inputs = application_generate_entity.inputs
                # 解析开场白模板
                prompt_template = PromptTemplateParser(template=introduction)
                # 根据模板提取需要的输入参数
                prompt_inputs = {k: inputs[k] for k in prompt_template.variable_keys if k in inputs}
                # 格式化开场白，替换参数
                introduction = prompt_template.format(prompt_inputs)
            except KeyError:
                # 如果缺少参数，则不进行格式化，保持原样
                pass

        return introduction

    def _get_conversation(self, conversation_id: str) -> Conversation:
        """
        通过对话id获取对话信息
        :param conversation_id: 对话的唯一标识符
        :return: 对话对象
        """
        # 从数据库中查询与给定对话id匹配的对话记录
        conversation = (
            db.session.query(Conversation)
            .filter(Conversation.id == conversation_id)
            .first()
        )

        return conversation

    def _get_message(self, message_id: str) -> Message:
        """
        根据消息ID获取消息对象
        :param message_id: 消息的唯一标识符
        :return: 返回与指定消息ID匹配的消息对象
        """
        # 从数据库中查询与消息ID匹配的第一条消息
        message = (
            db.session.query(Message)
            .filter(Message.id == message_id)
            .first()
        )

        return message
