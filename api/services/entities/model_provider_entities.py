from enum import Enum
from typing import Optional

from flask import current_app
from pydantic import BaseModel

from core.entities.model_entities import ModelStatus, ModelWithProviderEntity
from core.entities.provider_entities import QuotaConfiguration
from core.model_runtime.entities.common_entities import I18nObject
from core.model_runtime.entities.model_entities import ModelType, ProviderModel
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
    供应商响应模型类。
    该类描述了供应商返回响应的数据结构。
    属性:
    - provider: 供应商名称。
    - label: 本地化标签对象。
    - description: 可选的本地化描述对象，默认为None。
    - icon_small: 可选的小图标本地化对象，默认为None。
    - icon_large: 可选的大图标本地化对象，默认为None。
    - background: 可选的背景颜色，默认为None。
    - help: 可选的供应商帮助信息对象，默认为None。
    - supported_model_types: 支持的模型类型列表。
    - configurate_methods: 配置方法列表。
    - provider_credential_schema: 可选的供应商凭证模式对象，默认为None。
    - model_credential_schema: 可选的模型凭证模式对象，默认为None。
    - preferred_provider_type: 优选的供应商类型。
    - custom_configuration: 自定义配置响应对象。
    - system_configuration: 系统配置响应对象。
    """

    # 初始化函数，构造ProviderResponse实例。
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



class ModelResponse(ProviderModel):
    """
    模型响应模型类。
    该类描述了模型返回响应的数据结构。
    属性:
    - status: 模型状态。
    """
    status: ModelStatus


class ProviderWithModelsResponse(BaseModel):
    """
    包含模型的供应商响应模型类。
    该类描述了供应商及其模型返回响应的数据结构。
    属性:
    - provider: 供应商名称。
    - label: 本地化标签对象。
    - icon_small: 可选的小图标本地化对象，默认为None。
    - icon_large: 可选的大图标本地化对象，默认为None。
    - status: 自定义配置状态。
    - models: 模型响应对象列表。
    """

    # 初始化函数，构造ProviderWithModelsResponse实例。
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
        """
        初始化ModelWithProviderEntityResponse实例。
        
        参数:
            model (ModelWithProviderEntity): 包含模型和提供者信息的对象。
            
        返回值:
            None
        """
        super().__init__(**model.dict())  # 使用model对象的字典形式初始化当前对象