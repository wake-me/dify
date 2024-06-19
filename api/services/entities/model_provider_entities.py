from enum import Enum
from typing import Optional

from flask import current_app
from pydantic import BaseModel, ConfigDict

from core.entities.model_entities import ModelWithProviderEntity, ProviderModelWithStatusEntity
from core.entities.provider_entities import QuotaConfiguration
from core.model_runtime.entities.common_entities import I18nObject
from core.model_runtime.entities.model_entities import ModelType
from core.model_runtime.entities.provider_entities import (
    SimpleProviderEntity,
)
from models.provider import ProviderQuotaType


class CustomConfigurationStatus(Enum):
    """
    自定义配置状态的枚举类。
    """
    ACTIVE = 'active'  # 激活状态
    NO_CONFIGURE = 'no-configure'  # 未配置状态


class CustomConfigurationResponse(BaseModel):
    """
    供应商自定义配置响应的模型类。
    
    属性:
        status (CustomConfigurationStatus): 自定义配置的状态，使用CustomConfigurationStatus枚举。
    """
    status: CustomConfigurationStatus


class SystemConfigurationResponse(BaseModel):
    """
    供应商系统配置响应的模型类。
    
    属性:
        enabled (bool): 配置是否启用。
        current_quota_type (Optional[ProviderQuotaType]): 当前配额类型，为可选字段。
        quota_configurations (list[QuotaConfiguration]): 配额配置列表。
    """
    enabled: bool
    current_quota_type: Optional[ProviderQuotaType] = None
    quota_configurations: list[QuotaConfiguration] = []


class ProviderResponse(BaseModel):
    """
    Model class for provider response.
    """
    provider: str
    label: I18nObject
    description: Optional[I18nObject] = None
    icon_small: Optional[I18nObject] = None
    icon_large: Optional[I18nObject] = None
    background: Optional[str] = None
    help: Optional[ProviderHelpEntity] = None
    supported_model_types: list[ModelType]
    configurate_methods: list[ConfigurateMethod]
    provider_credential_schema: Optional[ProviderCredentialSchema] = None
    model_credential_schema: Optional[ModelCredentialSchema] = None
    preferred_provider_type: ProviderType
    custom_configuration: CustomConfigurationResponse
    system_configuration: SystemConfigurationResponse

    # pydantic configs
    model_config = ConfigDict(protected_namespaces=())

    def __init__(self, **data) -> None:
        super().__init__(**data)

        # 设置图标URL，基于供应商名称。
        url_prefix = (current_app.config.get("CONSOLE_API_URL")
                      + f"/console/api/workspaces/current/model-providers/{self.provider}")
        if self.icon_small is not None:
            self.icon_small = I18nObject(
                en_US=f"{url_prefix}/icon_small/en_US",
                zh_Hans=f"{url_prefix}/icon_small/zh_Hans"
            )

        if self.icon_large is not None:
            self.icon_large = I18nObject(
                en_US=f"{url_prefix}/icon_large/en_US",
                zh_Hans=f"{url_prefix}/icon_large/zh_Hans"
            )


class ProviderWithModelsResponse(BaseModel):
    """
    Model class for provider with models response.
    """
    provider: str
    label: I18nObject
    icon_small: Optional[I18nObject] = None
    icon_large: Optional[I18nObject] = None
    status: CustomConfigurationStatus
    models: list[ProviderModelWithStatusEntity]

    def __init__(self, **data) -> None:
        super().__init__(**data)

        # 设置图标URL，基于供应商名称。
        url_prefix = (current_app.config.get("CONSOLE_API_URL")
                      + f"/console/api/workspaces/current/model-providers/{self.provider}")
        if self.icon_small is not None:
            self.icon_small = I18nObject(
                en_US=f"{url_prefix}/icon_small/en_US",
                zh_Hans=f"{url_prefix}/icon_small/zh_Hans"
            )

        if self.icon_large is not None:
            self.icon_large = I18nObject(
                en_US=f"{url_prefix}/icon_large/en_US",
                zh_Hans=f"{url_prefix}/icon_large/zh_Hans"
            )


class SimpleProviderEntityResponse(SimpleProviderEntity):
    """
    简单提供者实体响应类。
    该类继承自SimpleProviderEntity，用于创建关于模型提供者的简单响应实体。
    """

    def __init__(self, **data) -> None:
        super().__init__(**data)  # 调用父类构造函数，初始化父类属性

        # 构建URL前缀，用于获取当前工作空间中模型提供者的图标
        url_prefix = (current_app.config.get("CONSOLE_API_URL")
                      + f"/console/api/workspaces/current/model-providers/{self.provider}")
        
        # 如果存在小图标地址，则将其设置为带有国际化路径的I18nObject
        if self.icon_small is not None:
            self.icon_small = I18nObject(
                en_US=f"{url_prefix}/icon_small/en_US",
                zh_Hans=f"{url_prefix}/icon_small/zh_Hans"
            )
            
        # 如果存在大图标地址，则将其设置为带有国际化路径的I18nObject
        if self.icon_large is not None:
            self.icon_large = I18nObject(
                en_US=f"{url_prefix}/icon_large/en_US",
                zh_Hans=f"{url_prefix}/icon_large/zh_Hans"
            )

class DefaultModelResponse(BaseModel):
    """
    默认模型实体类。
    
    属性:
        model (str): 模型名称。
        model_type (ModelType): 模型类型。
        provider (SimpleProviderEntityResponse): 提供者实体信息。
    """
    model: str
    model_type: ModelType
    provider: SimpleProviderEntityResponse

    # pydantic configs
    model_config = ConfigDict(protected_namespaces=())


class ModelWithProviderEntityResponse(ModelWithProviderEntity):
    """
    带提供者实体的模型类。
    
    属性:
        provider (SimpleProviderEntityResponse): 提供者实体信息。
        
    方法:
        __init__(self, model: ModelWithProviderEntity) -> None: 构造函数，初始化模型实例。
    """
    provider: SimpleProviderEntityResponse

    def __init__(self, model: ModelWithProviderEntity) -> None:
        super().__init__(**model.model_dump())
