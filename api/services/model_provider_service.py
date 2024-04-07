import logging
import mimetypes
import os
from typing import Optional, cast

import requests
from flask import current_app

from core.entities.model_entities import ModelStatus
from core.model_runtime.entities.model_entities import ModelType, ParameterRule
from core.model_runtime.model_providers import model_provider_factory
from core.model_runtime.model_providers.__base.large_language_model import LargeLanguageModel
from core.provider_manager import ProviderManager
from models.provider import ProviderType
from services.entities.model_provider_entities import (
    CustomConfigurationResponse,
    CustomConfigurationStatus,
    DefaultModelResponse,
    ModelResponse,
    ModelWithProviderEntityResponse,
    ProviderResponse,
    ProviderWithModelsResponse,
    SimpleProviderEntityResponse,
    SystemConfigurationResponse,
)

logger = logging.getLogger(__name__)


class ModelProviderService:
    """
    Model Provider Service
    """
    def __init__(self) -> None:
        # 初始化ProviderManager对象，用于管理提供者
        self.provider_manager = ProviderManager()

    def get_provider_list(self, tenant_id: str, model_type: Optional[str] = None) -> list[ProviderResponse]:
        """
        获取提供者列表。

        :param tenant_id: 工作空间ID
        :param model_type: 模型类型
        :return: 提供者响应列表
        """
        # 获取当前工作空间的所有提供者配置
        provider_configurations = self.provider_manager.get_configurations(tenant_id)

        provider_responses = []
        for provider_configuration in provider_configurations.values():
            # 如果指定了模型类型，则筛选支持该类型模型的提供者
            if model_type:
                model_type_entity = ModelType.value_of(model_type)
                if model_type_entity not in provider_configuration.provider.supported_model_types:
                    continue

            # 构建提供者响应对象
            provider_response = ProviderResponse(
                provider=provider_configuration.provider.provider,
                label=provider_configuration.provider.label,
                description=provider_configuration.provider.description,
                icon_small=provider_configuration.provider.icon_small,
                icon_large=provider_configuration.provider.icon_large,
                background=provider_configuration.provider.background,
                help=provider_configuration.provider.help,
                supported_model_types=provider_configuration.provider.supported_model_types,
                configurate_methods=provider_configuration.provider.configurate_methods,
                provider_credential_schema=provider_configuration.provider.provider_credential_schema,
                model_credential_schema=provider_configuration.provider.model_credential_schema,
                preferred_provider_type=provider_configuration.preferred_provider_type,
                custom_configuration=CustomConfigurationResponse(
                    status=CustomConfigurationStatus.ACTIVE
                    if provider_configuration.is_custom_configuration_available()
                    else CustomConfigurationStatus.NO_CONFIGURE
                ),
                system_configuration=SystemConfigurationResponse(
                    enabled=provider_configuration.system_configuration.enabled,
                    current_quota_type=provider_configuration.system_configuration.current_quota_type,
                    quota_configurations=provider_configuration.system_configuration.quota_configurations
                )
            )

            provider_responses.append(provider_response)

        return provider_responses

    def get_models_by_provider(self, tenant_id: str, provider: str) -> list[ModelWithProviderEntityResponse]:
        """
        获取指定提供商的模型列表。
        仅为模型提供者页面服务，支持传入单个提供商来查询支持的模型列表。

        :param tenant_id: 租户ID，用于标识特定租户的工作空间。
        :param provider: 提供商名称，指定要查询模型的提供商。
        :return: 返回一个ModelWithProviderEntityResponse类型的列表，包含指定提供商的所有模型。

        """
        # 获取当前工作空间的所有提供商配置
        provider_configurations = self.provider_manager.get_configurations(tenant_id)

        # 根据指定提供商获取可用模型，并转换为ModelWithProviderEntityResponse类型列表
        return [ModelWithProviderEntityResponse(model) for model in provider_configurations.get_models(
            provider=provider
        )]

    def get_provider_credentials(self, tenant_id: str, provider: str) -> dict:
        """
        获取给定提供商的凭证信息。

        :param tenant_id: 租户ID，用于标识特定的工作空间。
        :param provider: 提供商名称，指定要获取凭证的云服务提供商。
        :return: 返回一个包含提供商自定义凭证信息的字典。
        """
        # 获取当前工作空间的所有提供商配置
        provider_configurations = self.provider_manager.get_configurations(tenant_id)

        # 获取指定提供商的配置
        provider_configuration = provider_configurations.get(provider)
        if not provider_configuration:
            # 如果指定提供商不存在，则抛出异常
            raise ValueError(f"Provider {provider} does not exist.")

        # 从工作空间中获取提供商的自定义凭证信息，并返回
        return provider_configuration.get_custom_credentials(obfuscated=True)

    def provider_credentials_validate(self, tenant_id: str, provider: str, credentials: dict) -> None:
        """
        验证供应商凭证的有效性。

        :param tenant_id: 租户ID，用于标识当前工作空间。
        :param provider: 供应商名称，需要验证凭证的供应商。
        :param credentials: 凭证字典，包含用于验证的凭证信息。
        :return: 无返回值。
        """
        # 获取当前工作空间的所有供应商配置
        provider_configurations = self.provider_manager.get_configurations(tenant_id)

        # 获取指定供应商的配置
        provider_configuration = provider_configurations.get(provider)
        if not provider_configuration:
            raise ValueError(f"Provider {provider} does not exist.")

        # 对供应商凭证进行验证
        provider_configuration.custom_credentials_validate(credentials)

    def save_provider_credentials(self, tenant_id: str, provider: str, credentials: dict) -> None:
        """
        保存自定义提供者配置。

        :param tenant_id: 工作空间ID
        :param provider: 提供者名称
        :param credentials: 提供者凭证
        :return: 无
        """
        # 获取当前工作空间的所有提供者配置
        provider_configurations = self.provider_manager.get_configurations(tenant_id)

        # 获取指定提供者的配置
        provider_configuration = provider_configurations.get(provider)
        if not provider_configuration:
            raise ValueError(f"Provider {provider} does not exist.")

        # 添加或更新自定义提供者凭证
        provider_configuration.add_or_update_custom_credentials(credentials)

    def remove_provider_credentials(self, tenant_id: str, provider: str) -> None:
        """
        移除指定工作空间中的自定义提供商配置。

        :param tenant_id: 工作空间ID
        :param provider: 提供商名称
        :return: 无返回值
        """
        # 获取当前工作空间的所有提供商配置
        provider_configurations = self.provider_manager.get_configurations(tenant_id)

        # 获取指定提供商的配置
        provider_configuration = provider_configurations.get(provider)
        if not provider_configuration:
            raise ValueError(f"Provider {provider} does not exist.")

        # 移除自定义提供商凭据。
        provider_configuration.delete_custom_credentials()

    def get_model_credentials(self, tenant_id: str, provider: str, model_type: str, model: str) -> dict:
        """
        获取模型的认证信息。

        :param tenant_id: 工作空间ID
        :param provider: 提供者名称
        :param model_type: 模型类型
        :param model: 模型名称
        :return: 返回模型的认证信息字典
        """
        # 获取当前工作空间的所有提供者配置
        provider_configurations = self.provider_manager.get_configurations(tenant_id)

        # 获取指定提供者的配置
        provider_configuration = provider_configurations.get(provider)
        if not provider_configuration:
            raise ValueError(f"Provider {provider} does not exist.")

        # 如果存在，从ProviderModel中获取模型的自定义认证信息
        return provider_configuration.get_custom_model_credentials(
            model_type=ModelType.value_of(model_type),
            model=model,
            obfuscated=True
        )

    def model_credentials_validate(self, tenant_id: str, provider: str, model_type: str, model: str,
                                credentials: dict) -> None:
        """
        验证模型的凭证信息。

        :param tenant_id: 工作空间ID
        :param provider: 提供者名称
        :param model_type: 模型类型
        :param model: 模型名称
        :param credentials: 模型的凭证信息
        :return: 无返回值
        """
        # 获取当前工作空间的所有提供者配置
        provider_configurations = self.provider_manager.get_configurations(tenant_id)

        # 获取指定提供者的配置
        provider_configuration = provider_configurations.get(provider)
        if not provider_configuration:
            raise ValueError(f"Provider {provider} does not exist.")

        # 验证模型凭证信息的有效性
        provider_configuration.custom_model_credentials_validate(
            model_type=ModelType.value_of(model_type),
            model=model,
            credentials=credentials
        )

    def save_model_credentials(self, tenant_id: str, provider: str, model_type: str, model: str,
                            credentials: dict) -> None:
        """
        保存模型凭证信息。

        :param tenant_id: 工作空间ID
        :param provider: 提供者名称
        :param model_type: 模型类型
        :param model: 模型名称
        :param credentials: 模型凭证信息
        :return: 无返回值
        """
        # 获取当前工作空间的所有提供者配置
        provider_configurations = self.provider_manager.get_configurations(tenant_id)

        # 获取指定提供者的配置
        provider_configuration = provider_configurations.get(provider)
        if not provider_configuration:
            raise ValueError(f"Provider {provider} does not exist.")

        # 添加或更新自定义模型凭证信息
        provider_configuration.add_or_update_custom_model_credentials(
            model_type=ModelType.value_of(model_type),
            model=model,
            credentials=credentials
        )

    def remove_model_credentials(self, tenant_id: str, provider: str, model_type: str, model: str) -> None:
        """
        移除模型凭证。

        :param tenant_id: 工作空间ID
        :param provider: 提供者名称
        :param model_type: 模型类型
        :param model: 模型名称
        :return: 无返回值
        """
        # 获取当前工作空间的所有提供者配置
        provider_configurations = self.provider_manager.get_configurations(tenant_id)

        # 获取提供者配置
        provider_configuration = provider_configurations.get(provider)
        if not provider_configuration:
            raise ValueError(f"提供者 {provider} 不存在。")

        # 移除自定义模型凭证
        provider_configuration.delete_custom_model_credentials(
            model_type=ModelType.value_of(model_type),
            model=model
        )

    def get_models_by_model_type(self, tenant_id: str, model_type: str) -> list[ProviderWithModelsResponse]:
        """
        根据模型类型获取模型。

        :param tenant_id: 工作空间ID
        :param model_type: 模型类型
        :return: ProviderWithModelsResponse列表，包含每个提供商及其可用模型的信息
        """
        # 获取当前工作空间的所有提供商配置
        provider_configurations = self.provider_manager.get_configurations(tenant_id)

        # 获取提供商可用模型
        models = provider_configurations.get_models(
            model_type=ModelType.value_of(model_type)
        )

        # 按提供商对模型进行分组
        provider_models = {}
        for model in models:
            if model.provider.provider not in provider_models:
                provider_models[model.provider.provider] = []

            if model.deprecated:
                continue

            provider_models[model.provider.provider].append(model)

        # 将模型信息转换为ProviderWithModelsResponse列表
        providers_with_models: list[ProviderWithModelsResponse] = []
        for provider, models in provider_models.items():
            if not models:
                continue

            first_model = models[0]

            # 检查是否有活跃状态的模型
            has_active_models = any([model.status == ModelStatus.ACTIVE for model in models])

            providers_with_models.append(
                ProviderWithModelsResponse(
                    provider=provider,
                    label=first_model.provider.label,
                    icon_small=first_model.provider.icon_small,
                    icon_large=first_model.provider.icon_large,
                    status=CustomConfigurationStatus.ACTIVE
                    if has_active_models else CustomConfigurationStatus.NO_CONFIGURE,
                    models=[ModelResponse(
                        model=model.model,
                        label=model.label,
                        model_type=model.model_type,
                        features=model.features,
                        fetch_from=model.fetch_from,
                        model_properties=model.model_properties,
                        status=model.status
                    ) for model in models]
                )
            )

        return providers_with_models

    def get_model_parameter_rules(self, tenant_id: str, provider: str, model: str) -> list[ParameterRule]:
        """
        获取模型参数规则。
        仅支持LLM（大型语言模型）。

        :param tenant_id: 工作空间ID
        :param provider: 提供者名称
        :param model: 模型名称
        :return: 参数规则列表
        """
        # 获取当前工作空间的所有提供者配置
        provider_configurations = self.provider_manager.get_configurations(tenant_id)

        # 获取指定提供者的配置
        provider_configuration = provider_configurations.get(provider)
        if not provider_configuration:
            raise ValueError(f"提供者 {provider} 不存在。")

        # 获取LLM类型的模型实例
        model_type_instance = provider_configuration.get_model_type_instance(ModelType.LLM)
        model_type_instance = cast(LargeLanguageModel, model_type_instance)

        # 获取认证信息
        credentials = provider_configuration.get_current_credentials(
            model_type=ModelType.LLM,
            model=model
        )

        if not credentials:
            return []

        # 调用模型实例的get_parameter_rules方法获取模型参数规则
        return model_type_instance.get_parameter_rules(
            model=model,
            credentials=credentials
        )

    def get_default_model_of_model_type(self, tenant_id: str, model_type: str) -> Optional[DefaultModelResponse]:
        """
        获取指定模型类型的默认模型。

        :param tenant_id: 工作空间ID
        :param model_type: 模型类型
        :return: 返回一个包含默认模型信息的响应对象，如果没有找到对应的默认模型则返回None
        """
        # 将字符串类型的模型类型转换为枚举类型
        model_type_enum = ModelType.value_of(model_type)
        # 通过管理器获取指定工作空间ID和模型类型的默认模型
        result = self.provider_manager.get_default_model(
            tenant_id=tenant_id,
            model_type=model_type_enum
        )

        # 如果获取结果不为空，构造并返回一个详细的默认模型响应对象，否则返回None
        return DefaultModelResponse(
            model=result.model,
            model_type=result.model_type,
            provider=SimpleProviderEntityResponse(
                provider=result.provider.provider,
                label=result.provider.label,
                icon_small=result.provider.icon_small,
                icon_large=result.provider.icon_large,
                supported_model_types=result.provider.supported_model_types
            )
        ) if result else None

    def update_default_model_of_model_type(self, tenant_id: str, model_type: str, provider: str, model: str) -> None:
        """
        更新指定模型类型的默认模型记录。

        :param tenant_id: 工作空间ID
        :param model_type: 模型类型
        :param provider: 提供者名称
        :param model: 模型名称
        :return: 无返回值
        """
        # 将字符串形式的模型类型转换为枚举类型
        model_type_enum = ModelType.value_of(model_type)
        # 调用provider_manager更新默认模型记录
        self.provider_manager.update_default_model_record(
            tenant_id=tenant_id,
            model_type=model_type_enum,
            provider=provider,
            model=model
        )

    def get_model_provider_icon(self, provider: str, icon_type: str, lang: str) -> tuple[Optional[bytes], Optional[str]]:
        """
        获取模型提供者的图标。

        :param provider: 提供者名称
        :param icon_type: 图标类型（icon_small 或 icon_large）
        :param lang: 语言（zh_Hans 或 en_US）
        :return: 返回图标的二进制数据和MIME类型，如果图标不存在则返回None

        此方法根据提供的模型提供者名称、图标类型和语言，来获取对应图标的二进制数据及其MIME类型。
        """

        # 通过工厂方法获取提供者实例，并获取其架构信息
        provider_instance = model_provider_factory.get_provider_instance(provider)
        provider_schema = provider_instance.get_provider_schema()

        # 根据图标类型确定具体的图标文件名
        if icon_type.lower() == 'icon_small':
            # 如果提供者没有小图标，则抛出异常
            if not provider_schema.icon_small:
                raise ValueError(f"Provider {provider} does not have small icon.")

            # 根据语言选择对应的图标文件名
            if lang.lower() == 'zh_hans':
                file_name = provider_schema.icon_small.zh_Hans
            else:
                file_name = provider_schema.icon_small.en_US
        else:
            # 如果提供者没有大图标，则抛出异常
            if not provider_schema.icon_large:
                raise ValueError(f"Provider {provider} does not have large icon.")

            # 根据语言选择对应的图标文件名
            if lang.lower() == 'zh_hans':
                file_name = provider_schema.icon_large.zh_Hans
            else:
                file_name = provider_schema.icon_large.en_US

        # 计算图标文件的完整路径
        root_path = current_app.root_path
        provider_instance_path = os.path.dirname(os.path.join(root_path, provider_instance.__class__.__module__.replace('.', '/')))
        file_path = os.path.join(provider_instance_path, "_assets")
        file_path = os.path.join(file_path, file_name)

        # 如果文件不存在，则返回None
        if not os.path.exists(file_path):
            return None, None

        # 获取文件的MIME类型
        mimetype, _ = mimetypes.guess_type(file_path)
        mimetype = mimetype or 'application/octet-stream'

        # 从文件中读取二进制数据
        with open(file_path, 'rb') as f:
            byte_data = f.read()
            return byte_data, mimetype

    def switch_preferred_provider(self, tenant_id: str, provider: str, preferred_provider_type: str) -> None:
        """
        切换首选服务提供商。

        :param tenant_id: 工作空间ID
        :param provider: 服务提供商名称
        :param preferred_provider_type: 首选服务提供商类型
        :return: 无返回值
        """
        # 获取当前工作空间的所有服务提供商配置
        provider_configurations = self.provider_manager.get_configurations(tenant_id)

        # 将preferred_provider_type转换为ProviderType枚举类型
        preferred_provider_type_enum = ProviderType.value_of(preferred_provider_type)

        # 获取服务提供商配置
        provider_configuration = provider_configurations.get(provider)
        if not provider_configuration:
            raise ValueError(f"服务提供商 {provider} 不存在。")

        # 切换首选服务提供商类型
        provider_configuration.switch_preferred_provider_type(preferred_provider_type_enum)

    def free_quota_submit(self, tenant_id: str, provider: str):
        """
        提交免费配额申请

        参数:
        tenant_id (str): 工作空间ID，用于标识申请的租户
        provider (str): 服务提供商名称，指定申请的服务提供商

        返回:
        dict: 根据申请结果返回不同类型的字典。如果申请成功且无需重定向，返回包含'type'和'result'键的结果；
            如果申请成功但需要重定向，返回包含'type'和'redirect_url'键的结果。

        异常:
        ValueError: 当API请求失败或返回非成功代码时抛出
        """
        # 从环境变量获取API密钥和基础URL
        api_key = os.environ.get("FREE_QUOTA_APPLY_API_KEY")
        api_base_url = os.environ.get("FREE_QUOTA_APPLY_BASE_URL")
        api_url = api_base_url + '/api/v1/providers/apply'

        # 构建请求头部，包含认证信息和内容类型
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {api_key}"
        }
        # 向免费配额申请API发送POST请求
        response = requests.post(api_url, headers=headers, json={'workspace_id': tenant_id, 'provider_name': provider})
        if not response.ok:
            # 如果请求失败，记录错误日志并抛出ValueError
            logger.error(f"Request FREE QUOTA APPLY SERVER Error: {response.status_code} ")
            raise ValueError(f"Error: {response.status_code} ")

        # 检查API响应结果
        if response.json()["code"] != 'success':
            # 如果API返回非成功代码，抛出ValueError
            raise ValueError(
                f"error: {response.json()['message']}"
            )

        rst = response.json()

        # 根据返回类型处理结果
        if rst['type'] == 'redirect':
            # 如果需要重定向，返回重定向URL
            return {
                'type': rst['type'],
                'redirect_url': rst['redirect_url']
            }
        else:
            # 如果无需重定向，返回成功结果
            return {
                'type': rst['type'],
                'result': 'success'
            }

    def free_quota_qualification_verify(self, tenant_id: str, provider: str, token: Optional[str]):
        """
        验证租户是否有资格获取免费配额。
        
        参数:
        tenant_id (str): 租户ID。
        provider (str): 服务提供商名称。
        token (Optional[str]): 用于身份验证的令牌，可选。

        返回:
        dict: 包含验证结果的字典。如果租户有资格，'flag'键值为True；否则为False，并提供原因。
        """
        # 从环境变量获取API密钥和基础URL
        api_key = os.environ.get("FREE_QUOTA_APPLY_API_KEY")
        api_base_url = os.environ.get("FREE_QUOTA_APPLY_BASE_URL")
        api_url = api_base_url + '/api/v1/providers/qualification-verify'

        # 准备请求头，包含认证信息
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {api_key}"
        }
        # 准备请求体，包含租户ID、提供商名称和可选的令牌
        json_data = {'workspace_id': tenant_id, 'provider_name': provider}
        if token:
            json_data['token'] = token
        
        # 发起POST请求
        response = requests.post(api_url, headers=headers,
                                json=json_data)
        # 请求失败时，记录日志并抛出异常
        if not response.ok:
            logger.error(f"Request FREE QUOTA APPLY SERVER Error: {response.status_code} ")
            raise ValueError(f"Error: {response.status_code} ")

        # 解析响应
        rst = response.json()
        # 响应码非'success'时，抛出异常
        if rst["code"] != 'success':
            raise ValueError(
                f"error: {rst['message']}"
            )

        # 处理合格或不合格的结果
        data = rst['data']
        if data['qualified'] is True:
            return {
                'result': 'success',
                'provider_name': provider,
                'flag': True
            }
        else:
            return {
                'result': 'success',
                'provider_name': provider,
                'flag': False,
                'reason': data['reason']
            }
