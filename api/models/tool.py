import json
from enum import Enum

from extensions.ext_database import db
from models import StringUUID


class ToolProviderName(Enum):
    # ToolProviderName 枚举类，定义了工具提供商的名称。
    SERPAPI = 'serpapi'

    @staticmethod
    def value_of(value):
        """
        根据值获取枚举成员。

        参数:
        value - 要查找的枚举成员的值。

        返回:
        与给定值匹配的枚举成员。

        异常:
        ValueError - 如果没有找到与给定值匹配的枚举成员时抛出。
        """
        for member in ToolProviderName:
            if member.value == value:
                return member
        raise ValueError(f"No matching enum found for value '{value}'")

class ToolProvider(db.Model):
    """
    ToolProvider 类，代表工具提供商的信息，是一个数据库模型。

    属性:
    id - 工具提供商的唯一标识符。
    tenant_id - 租户的唯一标识符，不可为空。
    tool_name - 工具的名称，不可为空。
    encrypted_credentials - 加密的凭证信息，可能为空。
    is_enabled - 标记工具提供商是否启用，不可为空，默认为 False。
    created_at - 记录创建时间，不可为空，默认为当前时间。
    updated_at - 记录更新时间，不可为空，默认为当前时间。
    """

    __tablename__ = 'tool_providers'
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='tool_provider_pkey'),  # 主键约束
        db.UniqueConstraint('tenant_id', 'tool_name', name='unique_tool_provider_tool_name')  # 唯一性约束
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    tenant_id = db.Column(StringUUID, nullable=False)
    tool_name = db.Column(db.String(40), nullable=False)
    encrypted_credentials = db.Column(db.Text, nullable=True)
    is_enabled = db.Column(db.Boolean, nullable=False, server_default=db.text('false'))
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))

    @property
    def credentials_is_set(self):
        """
        判断加密凭证信息是否已设置。

        返回:
        bool - 如果加密凭证信息不为 None，则返回 True，表示凭证已设置。
        """
        return self.encrypted_credentials is not None

    @property
    def credentials(self):
        """
        获取解密的凭证信息。

        返回:
        dict - 如果加密凭证信息存在，则返回解密后的凭证信息；否则，返回 None。
        """
        return json.loads(self.encrypted_credentials) if self.encrypted_credentials is not None else None