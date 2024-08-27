from datetime import datetime, timezone
from typing import Optional, Union

from sqlalchemy import asc, desc, or_

from core.app.entities.app_invoke_entities import InvokeFrom
from core.llm_generator.llm_generator import LLMGenerator
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
    def pagination_by_last_id(
        cls,
        app_model: App,
        user: Optional[Union[Account, EndUser]],
        last_id: Optional[str],
        limit: int,
        invoke_from: InvokeFrom,
        include_ids: Optional[list] = None,
        exclude_ids: Optional[list] = None,
        sort_by: str = "-updated_at",
    ) -> InfiniteScrollPagination:
        if not user:
            return InfiniteScrollPagination(data=[], limit=limit, has_more=False)

        # 构建基础查询语句，包括应用筛选、用户类型和用户ID的筛选
        base_query = db.session.query(Conversation).filter(
            Conversation.is_deleted == False,
            Conversation.app_id == app_model.id,
            Conversation.from_source == ("api" if isinstance(user, EndUser) else "console"),
            Conversation.from_end_user_id == (user.id if isinstance(user, EndUser) else None),
            Conversation.from_account_id == (user.id if isinstance(user, Account) else None),
            or_(Conversation.invoke_from.is_(None), Conversation.invoke_from == invoke_from.value),
        )

        # 如果有指定包含的对话ID，则添加到查询条件中
        if include_ids is not None:
            base_query = base_query.filter(Conversation.id.in_(include_ids))

        # 如果有指定排除的对话ID，则添加到查询条件中
        if exclude_ids is not None:
            base_query = base_query.filter(~Conversation.id.in_(exclude_ids))

        # define sort fields and directions
        sort_field, sort_direction = cls._get_sort_params(sort_by)

        if last_id:
            last_conversation = base_query.filter(Conversation.id == last_id).first()
            if not last_conversation:
                raise LastConversationNotExistsError()

            # build filters based on sorting
            filter_condition = cls._build_filter_condition(sort_field, sort_direction, last_conversation)
            base_query = base_query.filter(filter_condition)

        base_query = base_query.order_by(sort_direction(getattr(Conversation, sort_field)))

        conversations = base_query.limit(limit).all()

        # 判断是否还有更多的对话需要加载
        has_more = False
        if len(conversations) == limit:
            current_page_last_conversation = conversations[-1]
            rest_filter_condition = cls._build_filter_condition(
                sort_field, sort_direction, current_page_last_conversation, is_next_page=True
            )
            rest_count = base_query.filter(rest_filter_condition).count()

            if rest_count > 0:
                has_more = True

        return InfiniteScrollPagination(data=conversations, limit=limit, has_more=has_more)

    @classmethod
    def _get_sort_params(cls, sort_by: str) -> tuple[str, callable]:
        if sort_by.startswith("-"):
            return sort_by[1:], desc
        return sort_by, asc

    @classmethod
    def _build_filter_condition(
        cls, sort_field: str, sort_direction: callable, reference_conversation: Conversation, is_next_page: bool = False
    ):
        field_value = getattr(reference_conversation, sort_field)
        if (sort_direction == desc and not is_next_page) or (sort_direction == asc and is_next_page):
            return getattr(Conversation, sort_field) < field_value
        else:
            return getattr(Conversation, sort_field) > field_value

    @classmethod
    def rename(
        cls,
        app_model: App,
        conversation_id: str,
        user: Optional[Union[Account, EndUser]],
        name: str,
        auto_generate: bool,
    ):
        conversation = cls.get_conversation(app_model, conversation_id, user)

        if auto_generate:
            # 如果设置为自动生成名称，则调用函数生成并返回新的会话对象
            return cls.auto_generate_name(app_model, conversation)
        else:
            # 否则，更新会话名称并提交到数据库
            conversation.name = name
            conversation.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.session.commit()

        return conversation  # 返回更新后的会话对象

    @classmethod
    def auto_generate_name(cls, app_model: App, conversation: Conversation):
        # get conversation first message
        message = (
            db.session.query(Message)
            .filter(Message.app_id == app_model.id, Message.conversation_id == conversation.id)
            .order_by(Message.created_at.asc())
            .first()
        )

        # 如果第一条消息不存在，则抛出异常
        if not message:
            raise MessageNotExistsError()

        # 尝试根据消息内容生成对话名称
        try:
            name = LLMGenerator.generate_conversation_name(
                app_model.tenant_id, message.query, conversation.id, app_model.id
            )
            conversation.name = name
        except:
            # 如果生成对话名称过程中出现异常，则不做任何处理
            pass

        # 提交数据库会话以保存更改
        db.session.commit()

        return conversation

    @classmethod
    def get_conversation(cls, app_model: App, conversation_id: str, user: Optional[Union[Account, EndUser]]):
        conversation = (
            db.session.query(Conversation)
            .filter(
                Conversation.id == conversation_id,
                Conversation.app_id == app_model.id,
                Conversation.from_source == ("api" if isinstance(user, EndUser) else "console"),
                Conversation.from_end_user_id == (user.id if isinstance(user, EndUser) else None),
                Conversation.from_account_id == (user.id if isinstance(user, Account) else None),
                Conversation.is_deleted == False,
            )
            .first()
        )

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
