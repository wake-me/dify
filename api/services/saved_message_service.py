from typing import Optional, Union

from extensions.ext_database import db
from libs.infinite_scroll_pagination import InfiniteScrollPagination
from models.account import Account
from models.model import App, EndUser
from models.web import SavedMessage
from services.message_service import MessageService


class SavedMessageService:
    """
    保存消息服务类，提供消息的分页查询、保存和删除功能。
    """
    
    @classmethod
    def pagination_by_last_id(cls, app_model: App, user: Optional[Union[Account, EndUser]],
                              last_id: Optional[str], limit: int) -> InfiniteScrollPagination:
        """
        根据最后一条消息的ID进行分页查询。
        
        :param app_model: 应用模型，用于指定查询的应用。
        :param user: 用户模型，可以是账户或终端用户，用于指定查询的用户。
        :param last_id: 最后一条消息的ID，用于指定查询的起点。
        :param limit: 限制返回消息的数量。
        :return: 返回一个无限滚动分页对象。
        """
        # 根据应用、用户类型和用户ID查询已保存的消息，并按创建时间降序排序
        saved_messages = db.session.query(SavedMessage).filter(
            SavedMessage.app_id == app_model.id,
            SavedMessage.created_by_role == ('account' if isinstance(user, Account) else 'end_user'),
            SavedMessage.created_by == user.id
        ).order_by(SavedMessage.created_at.desc()).all()
        message_ids = [sm.message_id for sm in saved_messages]

        # 调用消息服务的分页查询方法，包含已保存消息的ID
        return MessageService.pagination_by_last_id(
            app_model=app_model,
            user=user,
            last_id=last_id,
            limit=limit,
            include_ids=message_ids
        )

    @classmethod
    def save(cls, app_model: App, user: Optional[Union[Account, EndUser]], message_id: str):
        """
        保存一条消息。
        
        :param app_model: 应用模型，指定消息所属的应用。
        :param user: 用户模型，可以是账户或终端用户，指定保存消息的用户。
        :param message_id: 消息ID，指定要保存的消息。
        """
        # 检查消息是否已经被保存
        saved_message = db.session.query(SavedMessage).filter(
            SavedMessage.app_id == app_model.id,
            SavedMessage.message_id == message_id,
            SavedMessage.created_by_role == ('account' if isinstance(user, Account) else 'end_user'),
            SavedMessage.created_by == user.id
        ).first()

        if saved_message:
            return  # 如果已存在，则不重复保存

        # 获取消息，并创建新的保存记录
        message = MessageService.get_message(
            app_model=app_model,
            user=user,
            message_id=message_id
        )

        saved_message = SavedMessage(
            app_id=app_model.id,
            message_id=message.id,
            created_by_role='account' if isinstance(user, Account) else 'end_user',
            created_by=user.id
        )

        db.session.add(saved_message)
        db.session.commit()  # 提交事务

    @classmethod
    def delete(cls, app_model: App, user: Optional[Union[Account, EndUser]], message_id: str):
        """
        删除一条保存的消息。
        
        :param app_model: 应用模型，指定消息所属的应用。
        :param user: 用户模型，可以是账户或终端用户，指定删除消息的用户。
        :param message_id: 消息ID，指定要删除的消息。
        """
        # 检查是否存在该保存记录
        saved_message = db.session.query(SavedMessage).filter(
            SavedMessage.app_id == app_model.id,
            SavedMessage.message_id == message_id,
            SavedMessage.created_by_role == ('account' if isinstance(user, Account) else 'end_user'),
            SavedMessage.created_by == user.id
        ).first()

        if not saved_message:
            return  # 如果不存在，则不进行删除操作

        db.session.delete(saved_message)
        db.session.commit()  # 提交事务
