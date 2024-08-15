# 导入枚举类
import enum

# 导入数据库扩展模块
from extensions.ext_database import db

from .types import StringUUID


# 定义基于API的扩展点枚举类
class APIBasedExtensionPoint(enum.Enum):
    """
    基于API的扩展点枚举类，定义了不同的扩展点标识符。
    """
    APP_EXTERNAL_DATA_TOOL_QUERY = 'app.external_data_tool.query'  # 应用外部数据工具查询
    PING = 'ping'  # 心跳检查
    APP_MODERATION_INPUT = 'app.moderation.input'  # 应用审核输入
    APP_MODERATION_OUTPUT = 'app.moderation.output'  # 应用审核输出


# 定义基于API的扩展类
class APIBasedExtension(db.Model):
    """
    基于API的扩展类，用于定义和管理API扩展的信息。
    
    属性:
    - id: 扩展的唯一标识符，使用UUID生成。
    - tenant_id: 租户的唯一标识符，不可为空。
    - name: 扩展的名称，不可为空。
    - api_endpoint: API的端点地址，不可为空。
    - api_key: API的密钥，不可为空。
    - created_at: 创建时间，不可为空，默认为当前时间。
    """
    __tablename__ = 'api_based_extensions'  # 指定数据库表名
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='api_based_extension_pkey'),  # 指定主键约束
        db.Index('api_based_extension_tenant_idx', 'tenant_id'),  # 为tenant_id创建索引
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    tenant_id = db.Column(StringUUID, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    api_endpoint = db.Column(db.String(255), nullable=False)
    api_key = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
