from typing import Optional, Union

from core.generator.llm_generator import LLMGenerator
from extensions.ext_database import db
from libs.infinite_scroll_pagination import InfiniteScrollPagination
from models.account import Account
from models.model import App, Conversation, EndUser, Message
from services.errors.conversation import ConversationNotExistsError, LastConversationNotExistsError
from services.errors.message import MessageNotExistsError


class ConversationService:
    """
    会话服务类，提供以下会话相关操作方法：

    - pagination_by_last_id：根据最后一条消息ID进行分页查询，返回指定数量的会话记录。
    - rename：重命名指定会话，支持自动或手动指定新名称。
    - auto_generate_name：为指定会话自动生成名称，基于其第一条消息内容。
    - get_conversation：获取指定ID的会话信息。
    - delete：删除指定会话。
    """
    
    @classmethod
    def pagination_by_last_id(cls, app_model: App, user: Optional[Union[Account, EndUser]],
                            last_id: Optional[str], limit: int,
                            include_ids: Optional[list] = None, exclude_ids: Optional[list] = None,
                            exclude_debug_conversation: bool = False) -> InfiniteScrollPagination:
        """
        根据用户的最后一条对话ID进行分页查询，支持包含和排除特定对话ID，以及是否排除调试对话的设置。
        
        :param cls: 类的引用，用于调用数据库会话等。
        :param app_model: 应用模型，用于确定查询的应用。
        :param user: 可选，进行查询的用户，可以是账户或终端用户。
        :param last_id: 可选，最后一条对话的ID，用于分页查询。
        :param limit: 查询限制的数量。
        :param include_ids: 可选，需要包含的对话ID列表。
        :param exclude_ids: 可选，需要排除的对话ID列表。
        :param exclude_debug_conversation: 是否排除调试对话。
        :return: 返回一个InfiniteScrollPagination对象，包含对话数据、限制数量和是否有更多数据的标志。
        """
        # 如果没有指定用户，则直接返回空数据的分页对象
        if not user:
            return InfiniteScrollPagination(data=[], limit=limit, has_more=False)

        # 构建基础查询语句，包括应用筛选、用户类型和用户ID的筛选
        base_query = db.session.query(Conversation).filter(
            Conversation.is_deleted == False,
            Conversation.app_id == app_model.id,
            Conversation.from_source == ('api' if isinstance(user, EndUser) else 'console'),
            Conversation.from_end_user_id == (user.id if isinstance(user, EndUser) else None),
            Conversation.from_account_id == (user.id if isinstance(user, Account) else None),
        )

        # 如果有指定包含的对话ID，则添加到查询条件中
        if include_ids is not None:
            base_query = base_query.filter(Conversation.id.in_(include_ids))

        # 如果有指定排除的对话ID，则添加到查询条件中
        if exclude_ids is not None:
            base_query = base_query.filter(~Conversation.id.in_(exclude_ids))

        # 如果需要排除调试对话，则添加条件
        if exclude_debug_conversation:
            base_query = base_query.filter(Conversation.override_model_configs == None)

        # 如果提供了last_id，则基于此进行进一步的查询
        if last_id:
            last_conversation = base_query.filter(
                Conversation.id == last_id,
            ).first()

            # 如果找不到基于last_id的对话，则抛出异常
            if not last_conversation:
                raise LastConversationNotExistsError()

            # 执行查询，获取符合条件的对话列表
            conversations = base_query.filter(
                Conversation.created_at < last_conversation.created_at,
                Conversation.id != last_conversation.id
            ).order_by(Conversation.created_at.desc()).limit(limit).all()
        else:
            # 如果没有提供last_id，则直接按照创建时间倒序查询
            conversations = base_query.order_by(Conversation.created_at.desc()).limit(limit).all()

        # 判断是否还有更多的对话需要加载
        has_more = False
        if len(conversations) == limit:
            current_page_first_conversation = conversations[-1]
            rest_count = base_query.filter(
                Conversation.created_at < current_page_first_conversation.created_at,
                Conversation.id != current_page_first_conversation.id
            ).count()

            if rest_count > 0:
                has_more = True

        # 返回包含对话数据、限制数量和是否有更多数据的分页对象
        return InfiniteScrollPagination(
            data=conversations,
            limit=limit,
            has_more=has_more
        )

    @classmethod
    def rename(cls, app_model: App, conversation_id: str,
            user: Optional[Union[Account, EndUser]], name: str, auto_generate: bool):
        """
        重命名会话。

        参数:
        - cls: 类的引用。
        - app_model: 应用模型，表示特定的应用。
        - conversation_id: 会话的唯一标识符。
        - user: 可选，进行操作的用户，可以是账户或终端用户。
        - name: 新的会话名称。
        - auto_generate: 布尔值，指示是否自动生成会话名称。

        返回值:
        - 重命名后的会话对象。
        """
        conversation = cls.get_conversation(app_model, conversation_id, user)  # 获取指定的会话

        if auto_generate:
            # 如果设置为自动生成名称，则调用函数生成并返回新的会话对象
            return cls.auto_generate_name(app_model, conversation)
        else:
            # 否则，更新会话名称并提交到数据库
            conversation.name = name
            db.session.commit()

        return conversation  # 返回更新后的会话对象

    @classmethod
    def auto_generate_name(cls, app_model: App, conversation: Conversation):
        """
        自动为对话生成名称。
        
        参数:
        - cls: 类的引用，此处未使用。
        - app_model: App模型的实例，代表一个特定的应用。
        - conversation: Conversation模型的实例，代表一个特定的对话。
        
        返回值:
        - 返回更新后的conversation实例。
        
        抛出:
        - MessageNotExistsError: 如果对话中的第一条消息不存在，则抛出此错误。
        """
        # 尝试获取对话的第一条消息
        message = db.session.query(Message) \
            .filter(
                Message.app_id == app_model.id,
                Message.conversation_id == conversation.id
            ).order_by(Message.created_at.asc()).first()

        # 如果第一条消息不存在，则抛出异常
        if not message:
            raise MessageNotExistsError()

        # 尝试根据消息内容生成对话名称
        try:
            name = LLMGenerator.generate_conversation_name(app_model.tenant_id, message.query)
            conversation.name = name
        except:
            # 如果生成对话名称过程中出现异常，则不做任何处理
            pass

        # 提交数据库会话以保存更改
        db.session.commit()

        return conversation

    @classmethod
    def get_conversation(cls, app_model: App, conversation_id: str, user: Optional[Union[Account, EndUser]]):
        """
        根据对话ID和用户信息，从数据库中获取对话记录。
        
        :param cls: 类的引用，用于调用数据库会话。
        :param app_model: 应用模型实例，代表一个特定的应用。
        :param conversation_id: 对话的唯一标识符。
        :param user: 参与对话的用户，可以是终端用户或账户。此参数为可选。
        :return: 查询到的对话记录。
        :raises ConversationNotExistsError: 如果对话不存在，则抛出异常。
        """
        # 查询数据库，尝试获取符合条件的对话记录
        conversation = db.session.query(Conversation) \
            .filter(
            Conversation.id == conversation_id,
            Conversation.app_id == app_model.id,
            Conversation.from_source == ('api' if isinstance(user, EndUser) else 'console'),
            Conversation.from_end_user_id == (user.id if isinstance(user, EndUser) else None),
            Conversation.from_account_id == (user.id if isinstance(user, Account) else None),
            Conversation.is_deleted == False
        ).first()

        # 如果查询结果为空，则抛出对话不存在异常
        if not conversation:
            raise ConversationNotExistsError()

        return conversation

    @classmethod
    def delete(cls, app_model: App, conversation_id: str, user: Optional[Union[Account, EndUser]]):
        """
        删除指定的对话。

        参数:
        - cls: 类的引用，用于调用类方法。
        - app_model: App 类的实例，代表一个应用程序。
        - conversation_id: 字符串，指定要删除的对话的ID。
        - user: 可选参数，可以是 Account 或 EndUser 的实例，代表执行删除操作的用户。

        返回值:
        - 无
        """
        conversation = cls.get_conversation(app_model, conversation_id, user)  # 获取指定对话

        conversation.is_deleted = True  # 标记对话为已删除
        db.session.commit()  # 提交数据库会话，使删除操作生效
