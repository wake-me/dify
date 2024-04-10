import json
from typing import Optional, Union

from core.app.apps.advanced_chat.app_config_manager import AdvancedChatAppConfigManager
from core.app.entities.app_invoke_entities import InvokeFrom
from core.llm_generator.llm_generator import LLMGenerator
from core.memory.token_buffer_memory import TokenBufferMemory
from core.model_manager import ModelManager
from core.model_runtime.entities.model_entities import ModelType
from extensions.ext_database import db
from libs.infinite_scroll_pagination import InfiniteScrollPagination
from models.account import Account
from models.model import App, AppMode, AppModelConfig, EndUser, Message, MessageFeedback
from services.conversation_service import ConversationService
from services.errors.conversation import ConversationCompletedError, ConversationNotExistsError
from services.errors.message import (
    FirstMessageNotExistsError,
    LastMessageNotExistsError,
    MessageNotExistsError,
    SuggestedQuestionsAfterAnswerDisabledError,
)
from services.workflow_service import WorkflowService


class MessageService:
    @classmethod
    def pagination_by_first_id(cls, app_model: App, user: Optional[Union[Account, EndUser]],
                                conversation_id: str, first_id: Optional[str], limit: int) -> InfiniteScrollPagination:
        """
        根据第一个消息的ID进行分页查询会话历史记录。

        :param cls: 类名，用于指示方法属于哪个类。
        :param app_model: 应用模型实例，用于查询会话信息。
        :param user: 用户模型，可以是账户或终端用户，用于查询会话信息。
        :param conversation_id: 会话ID，用于查询具体的会话。
        :param first_id: 第一个消息的ID，用于指定查询的起始位置。如果为None，则从最新消息开始查询。
        :param limit: 查询限制的数量。
        :return: 返回一个InfiniteScrollPagination实例，包含查询到的数据、限制数量和是否有更多数据的标志。

        该方法首先检查用户和会话ID是否存在，然后通过conversation_id和first_id查询会话历史消息。
        如果first_id提供，则从该消息之前的消息开始查询，否则从最新消息开始查询。
        查询结果将根据创建时间倒序返回，并标记是否还有更多的历史消息可供查询。
        """

        # 检查用户是否提供
        if not user:
            return InfiniteScrollPagination(data=[], limit=limit, has_more=False)

        # 检查会话ID是否提供
        if not conversation_id:
            return InfiniteScrollPagination(data=[], limit=limit, has_more=False)

        # 根据提供的app_model, user, conversation_id获取会话信息
        conversation = ConversationService.get_conversation(
            app_model=app_model,
            user=user,
            conversation_id=conversation_id
        )

        # 根据first_id查询起始消息，并获取该消息之前的消息
        if first_id:
            first_message = db.session.query(Message) \
                .filter(Message.conversation_id == conversation.id, Message.id == first_id).first()

            # 如果起始消息不存在，则抛出异常
            if not first_message:
                raise FirstMessageNotExistsError()

            history_messages = db.session.query(Message).filter(
                Message.conversation_id == conversation.id,
                Message.created_at < first_message.created_at,
                Message.id != first_message.id
            ) \
                .order_by(Message.created_at.desc()).limit(limit).all()
        else:
            # 如果没有提供first_id，则直接查询最新的消息
            history_messages = db.session.query(Message).filter(Message.conversation_id == conversation.id) \
                .order_by(Message.created_at.desc()).limit(limit).all()

        # 判断是否还有更多的消息可供查询
        has_more = False
        if len(history_messages) == limit:
            current_page_first_message = history_messages[-1]
            rest_count = db.session.query(Message).filter(
                Message.conversation_id == conversation.id,
                Message.created_at < current_page_first_message.created_at,
                Message.id != current_page_first_message.id
            ).count()

            if rest_count > 0:
                has_more = True

        # 将消息列表反转，以便按照创建时间倒序返回
        history_messages = list(reversed(history_messages))

        # 构建并返回分页结果
        return InfiniteScrollPagination(
            data=history_messages,
            limit=limit,
            has_more=has_more
        )

    @classmethod
    def pagination_by_last_id(cls, app_model: App, user: Optional[Union[Account, EndUser]],
                            last_id: Optional[str], limit: int, conversation_id: Optional[str] = None,
                            include_ids: Optional[list] = None) -> InfiniteScrollPagination:
        """
        根据用户的最后一个消息ID，进行分页查询，支持无限滚动。
        
        :param cls: 未使用的类参数，可能用于未来扩展。
        :param app_model: 应用模型，用于查询时的上下文绑定。
        :param user: 执行查询的用户，可以是账户或终端用户，None表示不进行用户限制的查询。
        :param last_id: 上一次查询的最后一条消息的ID，用于获取该消息之前的最新消息。
        :param limit: 每次查询的消息数量限制。
        :param conversation_id: 对话ID，如果提供，则查询该对话中的消息。
        :param include_ids: 包含的消息ID列表，如果提供，则只查询这些ID的消息。
        :return: 返回一个InfiniteScrollPagination对象，包含查询到的消息数据、限制数和是否有更多消息的标志。
        """
        # 如果没有指定用户，则直接返回空数据的分页对象
        if not user:
            return InfiniteScrollPagination(data=[], limit=limit, has_more=False)

        # 基础查询，从数据库会话中查询消息
        base_query = db.session.query(Message)

        # 如果提供了对话ID，过滤查询结果，只包含指定对话的消息
        if conversation_id is not None:
            conversation = ConversationService.get_conversation(
                app_model=app_model,
                user=user,
                conversation_id=conversation_id
            )
            base_query = base_query.filter(Message.conversation_id == conversation.id)

        # 如果提供了包含的消息ID列表，进一步过滤查询结果
        if include_ids is not None:
            base_query = base_query.filter(Message.id.in_(include_ids))

        # 如果提供了last_id，查询该ID之前的消息，否则查询最新的消息
        if last_id:
            last_message = base_query.filter(Message.id == last_id).first()
            # 如果找不到指定的最后一条消息，抛出异常
            if not last_message:
                raise LastMessageNotExistsError()
            # 查询最后一条消息之前的消息，按创建时间降序排列，限制查询数量
            history_messages = base_query.filter(
                Message.created_at < last_message.created_at,
                Message.id != last_message.id
            ).order_by(Message.created_at.desc()).limit(limit).all()
        else:
            history_messages = base_query.order_by(Message.created_at.desc()).limit(limit).all()

        # 判断是否还有更多的消息可供查询
        has_more = False
        if len(history_messages) == limit:
            current_page_first_message = history_messages[-1]
            rest_count = base_query.filter(
                Message.created_at < current_page_first_message.created_at,
                Message.id != current_page_first_message.id
            ).count()

            if rest_count > 0:
                has_more = True

        # 返回查询结果的分页对象
        return InfiniteScrollPagination(
            data=history_messages,
            limit=limit,
            has_more=has_more
        )

    @classmethod
    def create_feedback(cls, app_model: App, message_id: str, user: Optional[Union[Account, EndUser]],
                            rating: Optional[str]) -> MessageFeedback:
        """
        创建或更新消息反馈。

        参数:
        - cls: 类的引用。
        - app_model: 应用模型实例，表示特定的应用。
        - message_id: 消息的唯一标识符。
        - user: 提供反馈的用户，可以是终端用户或管理员。可为None。
        - rating: 用户给的消息评分。可为None。

        返回值:
        - MessageFeedback实例。

        抛出:
        - ValueError: 如果user为None或在不存在反馈时rating为None，则抛出此异常。
        """
        if not user:
            raise ValueError('user cannot be None')

        # 根据提供的app_model, user和message_id获取消息实例
        message = cls.get_message(
            app_model=app_model,
            user=user,
            message_id=message_id
        )

        # 根据用户类型选择合适的反馈类型
        feedback = message.user_feedback if isinstance(user, EndUser) else message.admin_feedback

        # 判断是否存在反馈和评分，进行相应的操作：删除、更新或创建反馈
        if not rating and feedback:
            db.session.delete(feedback)  # 删除现有反馈
        elif rating and feedback:
            feedback.rating = rating  # 更新反馈的评分
        elif not rating and not feedback:
            raise ValueError('rating cannot be None when feedback not exists')  # 无评分且无反馈时抛出异常
        else:
            # 创建新的反馈记录
            feedback = MessageFeedback(
                app_id=app_model.id,
                conversation_id=message.conversation_id,
                message_id=message.id,
                rating=rating,
                from_source=('user' if isinstance(user, EndUser) else 'admin'),
                from_end_user_id=(user.id if isinstance(user, EndUser) else None),
                from_account_id=(user.id if isinstance(user, Account) else None),
            )
            db.session.add(feedback)

        db.session.commit()  # 提交数据库事务

        return feedback

    @classmethod
    def get_message(cls, app_model: App, user: Optional[Union[Account, EndUser]], message_id: str):
        """
        根据提供的参数获取相应的消息对象。
        
        :param cls: 类的引用，用于调用本方法。
        :param app_model: App模型的实例，代表一个特定的应用。
        :param user: 可选参数，可以是Account或EndUser的实例，代表发起消息的用户。
        :param message_id: 消息的唯一标识符。
        :return: 返回与给定条件匹配的消息对象。
        :raises MessageNotExistsError: 如果找不到对应的消息，则抛出异常。
        """
        # 查询数据库，尝试获取满足条件的消息对象
        message = db.session.query(Message).filter(
            Message.id == message_id,
            Message.app_id == app_model.id,
            Message.from_source == ('api' if isinstance(user, EndUser) else 'console'),
            Message.from_end_user_id == (user.id if isinstance(user, EndUser) else None),
            Message.from_account_id == (user.id if isinstance(user, Account) else None),
        ).first()

        # 如果查询结果为空，则抛出消息不存在异常
        if not message:
            raise MessageNotExistsError()

        return message

    @classmethod
    def get_suggested_questions_after_answer(cls, app_model: App, user: Optional[Union[Account, EndUser]],
                                             message_id: str, invoke_from: InvokeFrom) -> list[Message]:
        if not user:
            raise ValueError('user cannot be None')

        # 根据提供的app_model, user和message_id获取消息
        message = cls.get_message(
            app_model=app_model,
            user=user,
            message_id=message_id
        )

        # 获取对话
        conversation = ConversationService.get_conversation(
            app_model=app_model,
            conversation_id=message.conversation_id,
            user=user
        )

        if not conversation:
            raise ConversationNotExistsError()

        # 检查对话状态是否正常
        if conversation.status != 'normal':
            raise ConversationCompletedError()

        model_manager = ModelManager()

        if app_model.mode == AppMode.ADVANCED_CHAT.value:
            workflow_service = WorkflowService()
            if invoke_from == InvokeFrom.DEBUGGER:
                workflow = workflow_service.get_draft_workflow(app_model=app_model)
            else:
                workflow = workflow_service.get_published_workflow(app_model=app_model)

            if workflow is None:
                return []

            app_config = AdvancedChatAppConfigManager.get_app_config(
                app_model=app_model,
                workflow=workflow
            )

            if not app_config.additional_features.suggested_questions_after_answer:
                raise SuggestedQuestionsAfterAnswerDisabledError()

            model_instance = model_manager.get_default_model_instance(
                tenant_id=app_model.tenant_id,
                model_type=ModelType.LLM
            )
        else:
            if not conversation.override_model_configs:
                app_model_config = db.session.query(AppModelConfig).filter(
                    AppModelConfig.id == conversation.app_model_config_id,
                    AppModelConfig.app_id == app_model.id
                ).first()
            else:
                conversation_override_model_configs = json.loads(conversation.override_model_configs)
                app_model_config = AppModelConfig(
                    id=conversation.app_model_config_id,
                    app_id=app_model.id,
                )

                app_model_config = app_model_config.from_model_config_dict(conversation_override_model_configs)

            suggested_questions_after_answer = app_model_config.suggested_questions_after_answer_dict
            if suggested_questions_after_answer.get("enabled", False) is False:
                raise SuggestedQuestionsAfterAnswerDisabledError()

            model_instance = model_manager.get_model_instance(
                tenant_id=app_model.tenant_id,
                provider=app_model_config.model_dict['provider'],
                model_type=ModelType.LLM,
                model=app_model_config.model_dict['name']
            )

        # get memory of conversation (read-only)
        memory = TokenBufferMemory(
            conversation=conversation,
            model_instance=model_instance
        )

        # 获取历史对话文本
        histories = memory.get_history_prompt_text(
            max_token_limit=3000,
            message_limit=3,
        )

        # 生成建议的问题
        questions = LLMGenerator.generate_suggested_questions_after_answer(
            tenant_id=app_model.tenant_id,
            histories=histories
        )

        return questions
