from enum import Enum

from sqlalchemy.dialects.postgresql import UUID

from extensions.ext_database import db


class ProviderType(Enum):
    """
    提供者类型枚举，定义了两种提供者类型：自定义（CUSTOM）和系统（SYSTEM）。
    
    方法:
    - value_of: 根据值获取枚举成员
    """
    
    CUSTOM = 'custom'  # 自定义提供者类型
    SYSTEM = 'system'  # 系统提供者类型

    @staticmethod
    def value_of(value):
        """
        根据给定的值查找并返回相应的枚举成员。
        
        参数:
        - value: 要查找的枚举值
        
        返回值:
        - 找到的枚举成员
        
        异常:
        - ValueError: 如果没有找到与给定值匹配的枚举成员，则抛出异常
        """
        for member in ProviderType:
            if member.value == value:
                return member
        raise ValueError(f"No matching enum found for value '{value}'")  # 当找不到匹配的枚举值时抛出异常

class ProviderQuotaType(Enum):
    """
    供应商配额类型枚举，包括付费、免费和试用三种类型。
    """

    PAID = 'paid'
    """托管付费配额"""

    FREE = 'free'
    """第三方免费配额"""

    TRIAL = 'trial'
    """托管试用配额"""

    @staticmethod
    def value_of(value):
        """
        根据值获取枚举成员。
        
        参数:
        - value: 字符串类型，期望匹配的枚举值。
        
        返回:
        - Enum成员: 与给定值匹配的枚举成员。
        
        异常:
        - ValueError: 当找不到与给定值匹配的枚举成员时抛出。
        """
        for member in ProviderQuotaType:
            if member.value == value:
                return member
        raise ValueError(f"No matching enum found for value '{value}'")

class Provider(db.Model):
    """
    Provider模型，代表API提供者及其配置信息。
    """
    __tablename__ = 'providers'
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='provider_pkey'),
        db.Index('provider_tenant_id_provider_idx', 'tenant_id', 'provider_name'),
        db.UniqueConstraint('tenant_id', 'provider_name', 'provider_type', 'quota_type', name='unique_provider_name_type_quota')
    )

    # 数据库表和字段的定义
    id = db.Column(UUID, server_default=db.text('uuid_generate_v4()'))
    tenant_id = db.Column(UUID, nullable=False)
    provider_name = db.Column(db.String(40), nullable=False)
    provider_type = db.Column(db.String(40), nullable=False, server_default=db.text("'custom'::character varying"))
    encrypted_config = db.Column(db.Text, nullable=True)
    is_valid = db.Column(db.Boolean, nullable=False, server_default=db.text('false'))
    last_used = db.Column(db.DateTime, nullable=True)

    quota_type = db.Column(db.String(40), nullable=True, server_default=db.text("''::character varying"))
    quota_limit = db.Column(db.BigInteger, nullable=True)
    quota_used = db.Column(db.BigInteger, default=0)

    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))

    def __repr__(self):
        """
        返回对象的可读性好的字符串表示。
        
        返回:
        - 字符串: 表示Provider对象的字符串。
        """
        return f"<Provider(id={self.id}, tenant_id={self.tenant_id}, provider_name='{self.provider_name}', provider_type='{self.provider_type}')>"

    @property
    def token_is_set(self):
        """
        判断加密配置是否已设置，即判断token是否设置。
        
        返回:
        - 布尔值: 如果加密配置不为None，则返回True，表示token已设置。
        """
        return self.encrypted_config is not None

    @property
    def is_enabled(self):
        """
        判断提供者是否启用。
        
        返回:
        - 布尔值: 如果提供者启用，则返回True。
        """
        if self.provider_type == ProviderType.SYSTEM.value:
            return self.is_valid
        else:
            return self.is_valid and self.token_is_set


class ProviderModel(db.Model):
    """
    Provider模型，代表API提供者及其配置的信息。
    
    属性:
    id: 唯一标识符，使用UUID生成。
    tenant_id: 租户ID，不可为空。
    provider_name: 提供者名称，不可为空。
    model_name: 模型名称，不可为空。
    model_type: 模型类型，不可为空。
    encrypted_config: 加密的配置信息，可为空。
    is_valid: 标记模型是否有效，不可为空，默认为False。
    created_at: 记录创建时间，不可为空，默认为当前时间。
    updated_at: 记录更新时间，不可为空，默认为当前时间。
    
    表结构定义包括主键约束、索引和唯一性约束，以确保数据的完整性和一致性。
    """
    
    __tablename__ = 'provider_models'  # 指定数据库表名为provider_models
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='provider_model_pkey'),  # 主键约束
        db.Index('provider_model_tenant_id_provider_idx', 'tenant_id', 'provider_name'),  # 索引，加速查询
        db.UniqueConstraint('tenant_id', 'provider_name', 'model_name', 'model_type', name='unique_provider_model_name')  # 唯一性约束，保证四元组唯一
    )

    id = db.Column(UUID, server_default=db.text('uuid_generate_v4()'))  # UUID列，自动生成
    tenant_id = db.Column(UUID, nullable=False)  # 租户ID列
    provider_name = db.Column(db.String(40), nullable=False)  # 提供者名称列
    model_name = db.Column(db.String(255), nullable=False)  # 模型名称列
    model_type = db.Column(db.String(40), nullable=False)  # 模型类型列
    encrypted_config = db.Column(db.Text, nullable=True)  # 加密配置信息列
    is_valid = db.Column(db.Boolean, nullable=False, server_default=db.text('false'))  # 是否有效列
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))  # 创建时间列
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))  # 更新时间列

class TenantDefaultModel(db.Model):
    """
    租户默认模型类，用于表示租户的默认模型信息。
    
    属性:
    - id: 模型的唯一标识符，使用UUID生成。
    - tenant_id: 租户的唯一标识符，不可为空。
    - provider_name: 提供者名称，不可为空。
    - model_name: 模型名称，不可为空。
    - model_type: 模型类型，不可为空。
    - created_at: 记录创建时间，不可为空，默认为当前时间。
    - updated_at: 记录更新时间，不可为空，默认为当前时间。
    
    表结构信息:
    - 表名: tenant_default_models
    - 主键: id
    - 索引: 
        - tenant_default_model_tenant_id_provider_type_idx 使用(tenant_id, provider_name, model_type)作为索引
    """
    __tablename__ = 'tenant_default_models'  # 指定表名为tenant_default_models
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='tenant_default_model_pkey'),  # 定义主键约束
        db.Index('tenant_default_model_tenant_id_provider_type_idx', 'tenant_id', 'provider_name', 'model_type'),  # 定义复合索引
    )

    id = db.Column(UUID, server_default=db.text('uuid_generate_v4()'))  # UUID列，使用函数生成默认值
    tenant_id = db.Column(UUID, nullable=False)  # 租户ID列，不可为空
    provider_name = db.Column(db.String(40), nullable=False)  # 提供者名称列，不可为空，最大长度40
    model_name = db.Column(db.String(40), nullable=False)  # 模型名称列，不可为空，最大长度40
    model_type = db.Column(db.String(40), nullable=False)  # 模型类型列，不可为空，最大长度40
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))  # 记录创建时间，不可为空，默认为当前时间
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))  # 记录更新时间，不可为空，默认为当前时间


class TenantPreferredModelProvider(db.Model):
    """
    租户首选模型提供者类，用于定义租户偏好的模型提供者信息。
    
    属性:
    - id: 唯一标识符，使用UUID生成。
    - tenant_id: 租户ID，不可为空。
    - provider_name: 提供者名称，不可为空。
    - preferred_provider_type: 首选提供者类型，不可为空。
    - created_at: 记录创建时间，不可为空，默认为当前时间。
    - updated_at: 记录更新时间，不可为空，默认为当前时间。
    
    方法:
    - 无特殊方法，继承自db.Model，包含ORM常用方法。
    """
    
    __tablename__ = 'tenant_preferred_model_providers'  # 指定数据库表名为tenant_preferred_model_providers
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='tenant_preferred_model_provider_pkey'),  # 设置主键约束
        db.Index('tenant_preferred_model_provider_tenant_provider_idx', 'tenant_id', 'provider_name'),  # 创建索引
    )

    id = db.Column(UUID, server_default=db.text('uuid_generate_v4()'))  # 定义id列
    tenant_id = db.Column(UUID, nullable=False)  # 定义tenant_id列
    provider_name = db.Column(db.String(40), nullable=False)  # 定义provider_name列
    preferred_provider_type = db.Column(db.String(40), nullable=False)  # 定义preferred_provider_type列
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))  # 定义created_at列
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))  # 定义updated_at列

class ProviderOrder(db.Model):
    """
    供应商订单模型类，用于表示供应商的订单信息。

    属性:
    - id: 订单唯一标识符，使用UUID生成。
    - tenant_id: 租户的唯一标识符，不可为空。
    - provider_name: 供应商的名称，不可为空。
    - account_id: 供应商的账户标识符，不可为空。
    - payment_product_id: 支付产品标识符，例如：订单所含商品或服务的ID，不可为空。
    - payment_id: 支付的唯一标识符，可为空（未支付时）。
    - transaction_id: 交易的唯一标识符，可为空（未支付时）。
    - quantity: 订单数量，默认值为1，不可为空。
    - currency: 订单的货币单位，可为空。
    - total_amount: 订单总金额，可为空。
    - payment_status: 支付状态，不可为空，默认值为'wait_pay'。
    - paid_at: 支付完成的时间，可为空（未支付时）。
    - pay_failed_at: 支付失败的时间，可为空（未支付或支付成功时）。
    - refunded_at: 退款完成的时间，可为空（未退款时）。
    - created_at: 订单创建的时间，不可为空，默认为当前时间。
    - updated_at: 订单最后更新的时间，不可为空，默认为当前时间。
    """
    __tablename__ = 'provider_orders'  # 指定数据库表名为provider_orders
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='provider_order_pkey'),  # 指定id为表的主键
        db.Index('provider_order_tenant_provider_idx', 'tenant_id', 'provider_name'),  # 创建索引以提高查询效率
    )

    id = db.Column(UUID, server_default=db.text('uuid_generate_v4()'))  # 订单唯一标识符
    tenant_id = db.Column(UUID, nullable=False)  # 租户唯一标识符
    provider_name = db.Column(db.String(40), nullable=False)  # 供应商名称
    account_id = db.Column(UUID, nullable=False)  # 供应商账户标识符
    payment_product_id = db.Column(db.String(191), nullable=False)  # 支付产品标识符
    payment_id = db.Column(db.String(191))  # 支付标识符
    transaction_id = db.Column(db.String(191))  # 交易标识符
    quantity = db.Column(db.Integer, nullable=False, server_default=db.text('1'))  # 订单数量
    currency = db.Column(db.String(40))  # 货币单位
    total_amount = db.Column(db.Integer)  # 订单总金额
    payment_status = db.Column(db.String(40), nullable=False, server_default=db.text("'wait_pay'::character varying"))  # 支付状态
    paid_at = db.Column(db.DateTime)  # 支付完成时间
    pay_failed_at = db.Column(db.DateTime)  # 支付失败时间
    refunded_at = db.Column(db.DateTime)  # 退款完成时间
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))  # 订单创建时间
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))  # 订单最后更新时间
