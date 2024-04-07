from typing import Optional, Union

from extensions.ext_database import db
from libs.infinite_scroll_pagination import InfiniteScrollPagination
from models.account import Account
from models.model import App, EndUser
from models.web import PinnedConversation
from services.conversation_service import ConversationService


class WebConversationService:
    @classmethod
    def pagination_by_last_id(cls, app_model: App, user: Optional[Union[Account, EndUser]],
                            last_id: Optional[str], limit: int, pinned: Optional[bool] = None,
                            exclude_debug_conversation: bool = False) -> InfiniteScrollPagination:
        """
        根据用户的最后一条消息ID进行分页查询，可选地根据是否固定了会话列表来包括或排除这些会话。
        
        :param cls: 类的引用，通常用于调用类方法。
        :param app_model: 应用模型实例，用于查询与特定应用相关的会话。
        :param user: 用户实例，可以是账户或终端用户，用于查询与特定用户相关的会话。
        :param last_id: 最后一条消息的ID，用于分页查询。
        :param limit: 查询结果的限制数量。
        :param pinned: 可选参数，指定是否查询用户固定会话。True表示包括固定会话，False表示排除。
        :param exclude_debug_conversation: 是否排除调试会话，默认为False。
        :return: 返回一个InfiniteScrollPagination实例，包含分页查询的结果。
        """
        include_ids = None
        exclude_ids = None
        # 处理固定会话逻辑，根据pinned参数决定是包含还是排除这些会话
        if pinned is not None:
            # 查询用户（账户或终端用户）固定的所有会话
            pinned_conversations = db.session.query(PinnedConversation).filter(
                PinnedConversation.app_id == app_model.id,
                PinnedConversation.created_by_role == ('account' if isinstance(user, Account) else 'end_user'),
                PinnedConversation.created_by == user.id
            ).order_by(PinnedConversation.created_at.desc()).all()
            pinned_conversation_ids = [pc.conversation_id for pc in pinned_conversations]
            if pinned:
                include_ids = pinned_conversation_ids
            else:
                exclude_ids = pinned_conversation_ids

        # 调用ConversationService中的pagination_by_last_id方法进行分页查询
        return ConversationService.pagination_by_last_id(
            app_model=app_model,
            user=user,
            last_id=last_id,
            limit=limit,
            include_ids=include_ids,
            exclude_ids=exclude_ids,
            exclude_debug_conversation=exclude_debug_conversation
        )

    @classmethod
    def pin(cls, app_model: App, conversation_id: str, user: Optional[Union[Account, EndUser]]):
        """
        将会话固定到用户界面的显眼位置。

        参数:
        - cls: 类的引用，用于调用数据库会话等类方法。
        - app_model: App 类的实例，代表一个特定的应用。
        - conversation_id: 字符串，指定要固定的会话的ID。
        - user: Account 或 EndUser 类型的实例，表示执行此操作的用户。可以为 None。

        返回值:
        - 无
        """
        # 尝试从数据库中查询已存在的固定会话信息
        pinned_conversation = db.session.query(PinnedConversation).filter(
            PinnedConversation.app_id == app_model.id,
            PinnedConversation.conversation_id == conversation_id,
            PinnedConversation.created_by_role == ('account' if isinstance(user, Account) else 'end_user'),
            PinnedConversation.created_by == user.id
        ).first()

        # 如果已经存在固定的会话，则直接返回不做处理
        if pinned_conversation:
            return

        # 通过会话ID获取会话详情
        conversation = ConversationService.get_conversation(
            app_model=app_model,
            conversation_id=conversation_id,
            user=user
        )

        # 创建一个新的固定会话记录并保存到数据库
        pinned_conversation = PinnedConversation(
            app_id=app_model.id,
            conversation_id=conversation.id,
            created_by_role='account' if isinstance(user, Account) else 'end_user',
            created_by=user.id
        )

        db.session.add(pinned_conversation)
        db.session.commit()

    @classmethod
    def unpin(cls, app_model: App, conversation_id: str, user: Optional[Union[Account, EndUser]]):
        """
        取消固定对话。

        参数:
        - cls: 类的引用。
        - app_model: 应用模型的实例，代表一个特定的应用。
        - conversation_id: 对话的唯一标识符。
        - user: 取消固定对话的用户，可以是Account或EndUser类型的实例。如果是None，则不执行任何操作。

        返回值:
        - 无
        """
        # 查询当前用户和应用下对应的已固定对话
        pinned_conversation = db.session.query(PinnedConversation).filter(
            PinnedConversation.app_id == app_model.id,
            PinnedConversation.conversation_id == conversation_id,
            PinnedConversation.created_by_role == ('account' if isinstance(user, Account) else 'end_user'),
            PinnedConversation.created_by == user.id
        ).first()


        # 如果没有找到对应的固定对话，则不执行任何操作
        if not pinned_conversation:
            return

        # 删除指定的固定对话记录，并提交数据库事务
        db.session.delete(pinned_conversation)
        db.session.commit()