from sqlalchemy.dialects.postgresql import UUID

from extensions.ext_database import db
from models.model import Message


class SavedMessage(db.Model):
    """
    SavedMessage 类表示一个保存的消息模型，用于数据库操作。
    
    属性:
    - id: 消息的唯一标识符，使用UUID生成。
    - app_id: 关联的应用程序的UUID。
    - message_id: 关联的消息的UUID。
    - created_by_role: 创建消息的角色，例如终端用户。
    - created_by: 创建消息的用户的UUID。
    - created_at: 消息创建的时间戳。
    
    方法:
    - message: 一个属性方法，用于获取与当前SavedMessage关联的Message对象。
    """
    
    __tablename__ = 'saved_messages'  # 指定数据库表名为 saved_messages
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='saved_message_pkey'),  # 指定id为表的主键
        db.Index('saved_message_message_idx', 'app_id', 'message_id', 'created_by_role', 'created_by'),  # 创建索引以优化查询
    )

    # 定义数据库表的列
    id = db.Column(UUID, server_default=db.text('uuid_generate_v4()'))  # id列，使用UUID生成器
    app_id = db.Column(UUID, nullable=False)  # app_id列，不可为空
    message_id = db.Column(UUID, nullable=False)  # message_id列，不可为空
    created_by_role = db.Column(db.String(255), nullable=False, server_default=db.text("'end_user'::character varying"))  # 创建者的角色，默认为终端用户
    created_by = db.Column(UUID, nullable=False)  # 创建者的ID，不可为空
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))  # 创建时间，不可为空，默认为当前时间

    @property
    def message(self):
        """
        message 属性，用于获取与当前保存消息关联的原始消息对象。
        
        返回值:
        - 返回一个Message对象，如果找不到则返回None。
        """
        return db.session.query(Message).filter(Message.id == self.message_id).first()

class PinnedConversation(db.Model):
    """
    被固定的对话模型类，用于表示一个应用中被标记为重要的对话。

    属性:
    id: 对话的唯一标识符，使用UUID生成。
    app_id: 关联的应用的唯一标识符，不可为空。
    conversation_id: 对话的唯一标识符，不可为空。
    created_by_role: 创建对话标记的用户角色，默认为'end_user'。
    created_by: 创建对话标记的用户的唯一标识符，不可为空。
    created_at: 对话标记创建的时间，不可为空，默认为当前时间。
    """
    __tablename__ = 'pinned_conversations'  # 指定数据库表名为pinned_conversations
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='pinned_conversation_pkey'),  # 指定id为表的主键
        db.Index('pinned_conversation_conversation_idx', 'app_id', 'conversation_id', 'created_by_role', 'created_by'),  # 创建索引以优化查询
    )

    id = db.Column(UUID, server_default=db.text('uuid_generate_v4()'))  # 为对话生成一个唯一的UUID
    app_id = db.Column(UUID, nullable=False)  # 关联的应用ID
    conversation_id = db.Column(UUID, nullable=False)  # 对话的ID
    created_by_role = db.Column(db.String(255), nullable=False, server_default=db.text("'end_user'::character varying"))  # 创建者角色，默认为终端用户
    created_by = db.Column(UUID, nullable=False)  # 创建者的ID
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))  # 创建时间，默认为当前时间