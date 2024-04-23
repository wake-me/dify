from enum import Enum
from typing import Optional

from pydantic import BaseModel

from core.model_runtime.entities.model_entities import ModelType
from models.provider import ProviderQuotaType


class QuotaUnit(Enum):
    # 定义配额单位枚举类
    TIMES = 'times'  # 次数
    TOKENS = 'tokens'  # 令牌
    CREDITS = 'credits'  # 积分


class SystemConfigurationStatus(Enum):
    """
    系统配置状态枚举类。
    """
    ACTIVE = 'active'  # 激活状态
    QUOTA_EXCEEDED = 'quota-exceeded'  # 配额超出
    UNSUPPORTED = 'unsupported'  # 不支持


class RestrictModel(BaseModel):
    # 限制模型的类定义，用于定义模型的使用限制
    model: str  # 模型名称
    base_model_name: Optional[str] = None  # 基础模型名称，可选
    model_type: ModelType  # 模型类型


class QuotaConfiguration(BaseModel):
    """
    提供者配额配置的模型类。
    """
    quota_type: ProviderQuotaType  # 配额类型
    quota_unit: QuotaUnit  # 配额单位
    quota_limit: int  # 配额限制
    quota_used: int  # 配额已使用量
    is_valid: bool  # 配额是否有效
    restrict_models: list[RestrictModel] = []  # 模型使用限制列表


class SystemConfiguration(BaseModel):
    """
    提供者系统配置的模型类。
    """
    enabled: bool  # 是否启用
    current_quota_type: Optional[ProviderQuotaType] = None  # 当前配额类型，可选
    quota_configurations: list[QuotaConfiguration] = []  # 配额配置列表
    credentials: Optional[dict] = None  # 凭据信息，可选


class CustomProviderConfiguration(BaseModel):
    """
    提供者自定义配置的模型类。
    """
    credentials: dict  # 凭据信息


class CustomModelConfiguration(BaseModel):
    """
    提供者自定义模型配置的模型类。
    """
    model: str  # 模型名称
    model_type: ModelType  # 模型类型
    credentials: dict  # 凭据信息


class CustomConfiguration(BaseModel):
    """
    提供者自定义配置的模型类。
    """
    provider: Optional[CustomProviderConfiguration] = None  # 提供者配置，可选
    models: list[CustomModelConfiguration] = []  # 模型配置列表