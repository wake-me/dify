from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict

from core.model_runtime.entities.common_entities import I18nObject
from core.model_runtime.entities.model_entities import ModelType, ProviderModel
from core.model_runtime.entities.provider_entities import ProviderEntity


class ModelStatus(Enum):
    """
    模型状态枚举类。
    """
    ACTIVE = "active"
    NO_CONFIGURE = "no-configure"
    QUOTA_EXCEEDED = "quota-exceeded"
    NO_PERMISSION = "no-permission"
    DISABLED = "disabled"


class SimpleModelProviderEntity(BaseModel):
    """
    简单模型提供者实体类。
    用于表示模型提供者的简化的信息。
    """
    provider: str  # 提供者名称
    label: I18nObject  # 提供者标签，支持多语言
    icon_small: Optional[I18nObject] = None  # 小图标，支持多语言
    icon_large: Optional[I18nObject] = None  # 大图标，支持多语言
    supported_model_types: list[ModelType]  # 支持的模型类型列表

    def __init__(self, provider_entity: ProviderEntity) -> None:
        """
        初始化简单模型提供者实体。

        :param provider_entity: 模型提供者实体，包含提供者的详细信息。
        """
        super().__init__(
            provider=provider_entity.provider,
            label=provider_entity.label,
            icon_small=provider_entity.icon_small,
            icon_large=provider_entity.icon_large,
            supported_model_types=provider_entity.supported_model_types
        )


class ProviderModelWithStatusEntity(ProviderModel):
    """
    Model class for model response.
    """
    status: ModelStatus
    load_balancing_enabled: bool = False


class ModelWithProviderEntity(ProviderModelWithStatusEntity):
    """
    带提供者实体的模型类。
    用于表示一个具体模型及其相关的提供者信息。
    """
    provider: SimpleModelProviderEntity


class DefaultModelProviderEntity(BaseModel):
    """
    默认模型提供者实体类。
    用于描述默认模型提供者的详细信息。
    """
    provider: str  # 提供者名称
    label: I18nObject  # 提供者标签，支持多语言
    icon_small: Optional[I18nObject] = None  # 小图标，支持多语言
    icon_large: Optional[I18nObject] = None  # 大图标，支持多语言
    supported_model_types: list[ModelType]  # 支持的模型类型列表


class DefaultModelEntity(BaseModel):
    """
    默认模型实体类。
    用于表示一个具体模型及其默认提供者的详细信息。
    """
    model: str
    model_type: ModelType
    provider: DefaultModelProviderEntity

    # pydantic configs
    model_config = ConfigDict(protected_namespaces=())
