import datetime
import json
import logging
from collections import defaultdict
from collections.abc import Iterator
from json import JSONDecodeError
from typing import Optional

from pydantic import BaseModel, ConfigDict

from constants import HIDDEN_VALUE
from core.entities.model_entities import ModelStatus, ModelWithProviderEntity, SimpleModelProviderEntity
from core.entities.provider_entities import (
    CustomConfiguration,
    ModelSettings,
    SystemConfiguration,
    SystemConfigurationStatus,
)
from core.helper import encrypter
from core.helper.model_provider_cache import ProviderCredentialsCache, ProviderCredentialsCacheType
from core.model_runtime.entities.model_entities import FetchFrom, ModelType
from core.model_runtime.entities.provider_entities import (
    ConfigurateMethod,
    CredentialFormSchema,
    FormType,
    ProviderEntity,
)
from core.model_runtime.model_providers import model_provider_factory
from core.model_runtime.model_providers.__base.ai_model import AIModel
from core.model_runtime.model_providers.__base.model_provider import ModelProvider
from extensions.ext_database import db
from models.provider import (
    LoadBalancingModelConfig,
    Provider,
    ProviderModel,
    ProviderModelSetting,
    ProviderType,
    TenantPreferredModelProvider,
)

logger = logging.getLogger(__name__)

# 用于存储原始提供商配置方法的字典
original_provider_configurate_methods = {}


class ProviderConfiguration(BaseModel):
    """
    提供者配置的模型类。
    该类用于表示云服务提供者的配置信息，包括租户ID、提供者实体、首选的提供者类型、使用的提供者类型、系统配置和自定义配置。
    """
    tenant_id: str
    provider: ProviderEntity
    preferred_provider_type: ProviderType
    using_provider_type: ProviderType
    system_configuration: SystemConfiguration
    custom_configuration: CustomConfiguration
    model_settings: list[ModelSettings]

    # pydantic configs
    model_config = ConfigDict(protected_namespaces=())

    def __init__(self, **data):
        """
        初始化提供者配置实例。
        :param **data: 关键字参数，用于初始化模型属性。
        在初始化过程中，会检查并记录提供商的原始配置方法，并根据条件动态调整提供商的配置方法列表。
        """
        super().__init__(**data)  # 调用父类构造函数

        # 如果该提供商的原始配置方法未被记录，则进行记录
        if self.provider.provider not in original_provider_configurate_methods:
            original_provider_configurate_methods[self.provider.provider] = []
            for configurate_method in self.provider.configurate_methods:  # 遍历提供商的配置方法
                original_provider_configurate_methods[self.provider.provider].append(configurate_method)

        # 在特定条件下，向提供商的配置方法列表中添加预定义模型配置方法
        if original_provider_configurate_methods[self.provider.provider] == [ConfigurateMethod.CUSTOMIZABLE_MODEL]:
            if (any(len(quota_configuration.restrict_models) > 0
                     for quota_configuration in self.system_configuration.quota_configurations)
                    and ConfigurateMethod.PREDEFINED_MODEL not in self.provider.configurate_methods):
                self.provider.configurate_methods.append(ConfigurateMethod.PREDEFINED_MODEL)

    def get_current_credentials(self, model_type: ModelType, model: str) -> Optional[dict]:
        """
        Get current credentials.

        :param model_type: model type
        :param model: model name
        :return:
        """
        if self.model_settings:
            # check if model is disabled by admin
            for model_setting in self.model_settings:
                if (model_setting.model_type == model_type
                        and model_setting.model == model):
                    if not model_setting.enabled:
                        raise ValueError(f'Model {model} is disabled.')

        if self.using_provider_type == ProviderType.SYSTEM:
            # 系统提供者类型的认证处理
            restrict_models = []
            # 根据当前配额类型筛选适用的配额配置，并提取限制模型列表
            for quota_configuration in self.system_configuration.quota_configurations:
                if self.system_configuration.current_quota_type != quota_configuration.quota_type:
                    continue

                restrict_models = quota_configuration.restrict_models

            # 复制系统配置的认证信息
            copy_credentials = self.system_configuration.credentials.copy()
            # 如果存在限制模型，进一步处理以添加基础模型名称
            if restrict_models:
                for restrict_model in restrict_models:
                    if (restrict_model.model_type == model_type
                            and restrict_model.model == model
                            and restrict_model.base_model_name):
                        copy_credentials['base_model_name'] = restrict_model.base_model_name

            return copy_credentials
        else:
            credentials = None
            if self.custom_configuration.models:
                # 在自定义配置的模型中查找匹配的模型认证信息
                for model_configuration in self.custom_configuration.models:
                    if model_configuration.model_type == model_type and model_configuration.model == model:
                        credentials = model_configuration.credentials
                        break

            # 如果存在自定义提供者，返回其认证信息
            if self.custom_configuration.provider:
                credentials = self.custom_configuration.provider.credentials

            return credentials

    def get_system_configuration_status(self) -> SystemConfigurationStatus:
        """
        获取系统配置的状态。
        
        :return: 返回系统配置的状态，如果是不支持的配置则返回UNSUPPORTED，如果配置有效则返回ACTIVE，
                如果配置的配额超出则返回QUOTA_EXCEEDED。
        """
        # 检查系统配置是否启用
        if self.system_configuration.enabled is False:
            return SystemConfigurationStatus.UNSUPPORTED

        # 获取当前配额类型和对应的配置
        current_quota_type = self.system_configuration.current_quota_type
        current_quota_configuration = next(
            (q for q in self.system_configuration.quota_configurations if q.quota_type == current_quota_type),
            None
        )

        # 根据当前配额配置的有效性返回相应的配置状态
        return SystemConfigurationStatus.ACTIVE if current_quota_configuration.is_valid else \
            SystemConfigurationStatus.QUOTA_EXCEEDED

    def is_custom_configuration_available(self) -> bool:
        """
        检查是否可用自定义配置。
        
        该函数不接受任何参数。
        
        :return: 返回一个布尔值，如果自定义配置可用，则为True；否则为False。
        """
        # 检查自定义配置中是否提供了provider或者至少有一个模型
        return (self.custom_configuration.provider is not None
                or len(self.custom_configuration.models) > 0)

    def get_custom_credentials(self, obfuscated: bool = False) -> Optional[dict]:
        """
        获取自定义凭证。

        :param obfuscated: 凭证中的秘密数据是否被模糊处理
        :type obfuscated: bool
        :return: 如果存在自定义配置提供者，则返回凭证；如果请求被模糊处理，则返回模糊处理后的凭证；否则返回None。
        :rtype: Optional[dict]
        """
        # 检查是否有自定义配置提供者
        if self.custom_configuration.provider is None:
            return None

        credentials = self.custom_configuration.provider.credentials
        if not obfuscated:
            # 直接返回凭证，未进行模糊处理
            return credentials

        # Obfuscate credentials
        return self.obfuscated_credentials(
            credentials=credentials,
            credential_form_schemas=self.provider.provider_credential_schema.credential_form_schemas
            if self.provider.provider_credential_schema else []
        )

    def custom_credentials_validate(self, credentials: dict) -> tuple[Provider, dict]:
        """
        验证自定义凭证。
        :param credentials: 提供者的凭证信息，类型为字典。
        :return: 返回一个元组，包含Provider实例和验证后的凭证字典。
        """
        # 查询数据库以获取提供者记录
        provider_record = db.session.query(Provider) \
            .filter(
            Provider.tenant_id == self.tenant_id,
            Provider.provider_name == self.provider.provider,
            Provider.provider_type == ProviderType.CUSTOM.value
        ).first()

        # Get provider credential secret variables
        provider_credential_secret_variables = self.extract_secret_variables(
            self.provider.provider_credential_schema.credential_form_schemas
            if self.provider.provider_credential_schema else []
        )

        if provider_record:
            try:
                # 修复原始数据
                if provider_record.encrypted_config:
                    if not provider_record.encrypted_config.startswith("{"):
                        original_credentials = {
                            "openai_api_key": provider_record.encrypted_config
                        }
                    else:
                        original_credentials = json.loads(provider_record.encrypted_config)
                else:
                    original_credentials = {}
            except JSONDecodeError:
                original_credentials = {}

            # 加密凭证信息
            for key, value in credentials.items():
                if key in provider_credential_secret_variables:
                    # if send [__HIDDEN__] in secret input, it will be same as original value
                    if value == HIDDEN_VALUE and key in original_credentials:
                        credentials[key] = encrypter.decrypt_token(self.tenant_id, original_credentials[key])

        # 验证并调整凭证信息
        credentials = model_provider_factory.provider_credentials_validate(
            provider=self.provider.provider,
            credentials=credentials
        )

        # 对凭证信息进行加密
        for key, value in credentials.items():
            if key in provider_credential_secret_variables:
                credentials[key] = encrypter.encrypt_token(self.tenant_id, value)

        return provider_record, credentials

    def add_or_update_custom_credentials(self, credentials: dict) -> None:
        """
        添加或更新自定义提供商的凭证。
        :param credentials: 包含提供商凭证信息的字典。
        :return: 无返回值。
        """
        # 验证自定义提供商配置
        provider_record, credentials = self.custom_credentials_validate(credentials)

        # 保存提供商记录
        # 注意：不要切换首选提供商，这允许用户首先使用配额
        if provider_record:
            # 更新现有提供商记录
            provider_record.encrypted_config = json.dumps(credentials)
            provider_record.is_valid = True
            provider_record.updated_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            db.session.commit()
        else:
            # 创建新的提供商记录
            provider_record = Provider(
                tenant_id=self.tenant_id,
                provider_name=self.provider.provider,
                provider_type=ProviderType.CUSTOM.value,
                encrypted_config=json.dumps(credentials),
                is_valid=True
            )
            db.session.add(provider_record)
            db.session.commit()

        # 清除提供商凭证缓存
        provider_model_credentials_cache = ProviderCredentialsCache(
            tenant_id=self.tenant_id,
            identity_id=provider_record.id,
            cache_type=ProviderCredentialsCacheType.PROVIDER
        )
        provider_model_credentials_cache.delete()

        # 切换到自定义提供商作为首选提供商
        self.switch_preferred_provider_type(ProviderType.CUSTOM)

    def delete_custom_credentials(self) -> None:
        """
        删除自定义提供商的凭证。
        :return: 无返回值
        """
        # 获取提供商
        provider_record = db.session.query(Provider) \
            .filter(
            Provider.tenant_id == self.tenant_id,
            Provider.provider_name == self.provider.provider,
            Provider.provider_type == ProviderType.CUSTOM.value
        ).first()

        # 如果存在该提供商记录，则删除
        if provider_record:
            # 切换回系统首选提供商类型
            self.switch_preferred_provider_type(ProviderType.SYSTEM)

            # 从数据库中删除提供商记录并提交更改
            db.session.delete(provider_record)
            db.session.commit()

            # 删除提供商模型的凭证缓存
            provider_model_credentials_cache = ProviderCredentialsCache(
                tenant_id=self.tenant_id,
                identity_id=provider_record.id,
                cache_type=ProviderCredentialsCacheType.PROVIDER
            )

            provider_model_credentials_cache.delete()

    def get_custom_model_credentials(self, model_type: ModelType, model: str, obfuscated: bool = False) \
            -> Optional[dict]:
        """
        获取自定义模型的凭证信息。

        :param model_type: 模型类型
        :param model: 模型名称
        :param obfuscated: 凭证数据是否被模糊处理
        :return: 如果找到对应模型的凭证信息，则返回凭证字典；否则返回None
        """
        # 检查自定义配置中是否存在模型配置
        if not self.custom_configuration.models:
            return None

        # 遍历模型配置，寻找匹配的模型类型和名称
        for model_configuration in self.custom_configuration.models:
            if model_configuration.model_type == model_type and model_configuration.model == model:
                credentials = model_configuration.credentials
                # 如果不需要模糊处理，直接返回凭证信息
                if not obfuscated:
                    return credentials

                # Obfuscate credentials
                return self.obfuscated_credentials(
                    credentials=credentials,
                    credential_form_schemas=self.provider.model_credential_schema.credential_form_schemas
                    if self.provider.model_credential_schema else []
                )

        # 如果未找到匹配的模型配置，返回None
        return None

    def custom_model_credentials_validate(self, model_type: ModelType, model: str, credentials: dict) \
            -> tuple[ProviderModel, dict]:
        """
        验证自定义模型的凭证信息。

        :param model_type: 模型类型
        :param model: 模型名称
        :param credentials: 模型凭证
        :return: 返回验证后的提供者模型记录和加密的凭证信息元组
        """
        # 获取提供者模型记录
        provider_model_record = db.session.query(ProviderModel) \
            .filter(
            ProviderModel.tenant_id == self.tenant_id,
            ProviderModel.provider_name == self.provider.provider,
            ProviderModel.model_name == model,
            ProviderModel.model_type == model_type.to_origin_model_type()
        ).first()

        # Get provider credential secret variables
        provider_credential_secret_variables = self.extract_secret_variables(
            self.provider.model_credential_schema.credential_form_schemas
            if self.provider.model_credential_schema else []
        )

        if provider_model_record:
            try:
                original_credentials = json.loads(
                    provider_model_record.encrypted_config) if provider_model_record.encrypted_config else {}
            except JSONDecodeError:
                original_credentials = {}

            # 解密凭证信息
            for key, value in credentials.items():
                if key in provider_credential_secret_variables:
                    # if send [__HIDDEN__] in secret input, it will be same as original value
                    if value == HIDDEN_VALUE and key in original_credentials:
                        credentials[key] = encrypter.decrypt_token(self.tenant_id, original_credentials[key])

        # 验证并更新凭证信息
        credentials = model_provider_factory.model_credentials_validate(
            provider=self.provider.provider,
            model_type=model_type,
            model=model,
            credentials=credentials
        )

        # 对敏感凭证信息进行加密
        for key, value in credentials.items():
            if key in provider_credential_secret_variables:
                credentials[key] = encrypter.encrypt_token(self.tenant_id, value)

        return provider_model_record, credentials

    def add_or_update_custom_model_credentials(self, model_type: ModelType, model: str, credentials: dict) -> None:
        """
        添加或更新自定义模型的凭证信息。

        :param model_type: 模型类型
        :param model: 模型名称
        :param credentials: 模型凭证信息
        :return: 无返回值
        """
        # 验证自定义模型的配置信息
        provider_model_record, credentials = self.custom_model_credentials_validate(model_type, model, credentials)

        # 保存提供者模型记录
        # 注意：不要切换首选提供者，这允许用户首先使用配额
        if provider_model_record:
            # 更新现有模型记录的凭证信息和有效性标志，并记录更新时间
            provider_model_record.encrypted_config = json.dumps(credentials)
            provider_model_record.is_valid = True
            provider_model_record.updated_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            db.session.commit()
        else:
            # 为新模型创建提供者模型记录，并保存凭证信息
            provider_model_record = ProviderModel(
                tenant_id=self.tenant_id,
                provider_name=self.provider.provider,
                model_name=model,
                model_type=model_type.to_origin_model_type(),
                encrypted_config=json.dumps(credentials),
                is_valid=True
            )
            db.session.add(provider_model_record)
            db.session.commit()

        # 创建或更新提供者模型凭证缓存记录，并随后删除该缓存记录
        provider_model_credentials_cache = ProviderCredentialsCache(
            tenant_id=self.tenant_id,
            identity_id=provider_model_record.id,
            cache_type=ProviderCredentialsCacheType.MODEL
        )

        provider_model_credentials_cache.delete()

    def delete_custom_model_credentials(self, model_type: ModelType, model: str) -> None:
        """
        删除自定义模型的凭证信息。
        :param model_type: 模型类型
        :param model: 模型名称
        :return: 无返回值
        """
        # 查询对应的提供者模型记录
        provider_model_record = db.session.query(ProviderModel) \
            .filter(
            ProviderModel.tenant_id == self.tenant_id,
            ProviderModel.provider_name == self.provider.provider,
            ProviderModel.model_name == model,
            ProviderModel.model_type == model_type.to_origin_model_type()
        ).first()

        # 如果找到提供者模型记录，则删除该记录及其凭证缓存
        if provider_model_record:
            db.session.delete(provider_model_record)
            db.session.commit()

            # 构建并删除提供者模型凭证缓存
            provider_model_credentials_cache = ProviderCredentialsCache(
                tenant_id=self.tenant_id,
                identity_id=provider_model_record.id,
                cache_type=ProviderCredentialsCacheType.MODEL
            )

            provider_model_credentials_cache.delete()

    def enable_model(self, model_type: ModelType, model: str) -> ProviderModelSetting:
        """
        Enable model.
        :param model_type: model type
        :param model: model name
        :return:
        """
        model_setting = db.session.query(ProviderModelSetting) \
            .filter(
            ProviderModelSetting.tenant_id == self.tenant_id,
            ProviderModelSetting.provider_name == self.provider.provider,
            ProviderModelSetting.model_type == model_type.to_origin_model_type(),
            ProviderModelSetting.model_name == model
        ).first()

        if model_setting:
            model_setting.enabled = True
            model_setting.updated_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            db.session.commit()
        else:
            model_setting = ProviderModelSetting(
                tenant_id=self.tenant_id,
                provider_name=self.provider.provider,
                model_type=model_type.to_origin_model_type(),
                model_name=model,
                enabled=True
            )
            db.session.add(model_setting)
            db.session.commit()

        return model_setting

    def disable_model(self, model_type: ModelType, model: str) -> ProviderModelSetting:
        """
        Disable model.
        :param model_type: model type
        :param model: model name
        :return:
        """
        model_setting = db.session.query(ProviderModelSetting) \
            .filter(
            ProviderModelSetting.tenant_id == self.tenant_id,
            ProviderModelSetting.provider_name == self.provider.provider,
            ProviderModelSetting.model_type == model_type.to_origin_model_type(),
            ProviderModelSetting.model_name == model
        ).first()

        if model_setting:
            model_setting.enabled = False
            model_setting.updated_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            db.session.commit()
        else:
            model_setting = ProviderModelSetting(
                tenant_id=self.tenant_id,
                provider_name=self.provider.provider,
                model_type=model_type.to_origin_model_type(),
                model_name=model,
                enabled=False
            )
            db.session.add(model_setting)
            db.session.commit()

        return model_setting

    def get_provider_model_setting(self, model_type: ModelType, model: str) -> Optional[ProviderModelSetting]:
        """
        Get provider model setting.
        :param model_type: model type
        :param model: model name
        :return:
        """
        return db.session.query(ProviderModelSetting) \
            .filter(
            ProviderModelSetting.tenant_id == self.tenant_id,
            ProviderModelSetting.provider_name == self.provider.provider,
            ProviderModelSetting.model_type == model_type.to_origin_model_type(),
            ProviderModelSetting.model_name == model
        ).first()

    def enable_model_load_balancing(self, model_type: ModelType, model: str) -> ProviderModelSetting:
        """
        Enable model load balancing.
        :param model_type: model type
        :param model: model name
        :return:
        """
        load_balancing_config_count = db.session.query(LoadBalancingModelConfig) \
            .filter(
            LoadBalancingModelConfig.tenant_id == self.tenant_id,
            LoadBalancingModelConfig.provider_name == self.provider.provider,
            LoadBalancingModelConfig.model_type == model_type.to_origin_model_type(),
            LoadBalancingModelConfig.model_name == model
        ).count()

        if load_balancing_config_count <= 1:
            raise ValueError('Model load balancing configuration must be more than 1.')

        model_setting = db.session.query(ProviderModelSetting) \
            .filter(
            ProviderModelSetting.tenant_id == self.tenant_id,
            ProviderModelSetting.provider_name == self.provider.provider,
            ProviderModelSetting.model_type == model_type.to_origin_model_type(),
            ProviderModelSetting.model_name == model
        ).first()

        if model_setting:
            model_setting.load_balancing_enabled = True
            model_setting.updated_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            db.session.commit()
        else:
            model_setting = ProviderModelSetting(
                tenant_id=self.tenant_id,
                provider_name=self.provider.provider,
                model_type=model_type.to_origin_model_type(),
                model_name=model,
                load_balancing_enabled=True
            )
            db.session.add(model_setting)
            db.session.commit()

        return model_setting

    def disable_model_load_balancing(self, model_type: ModelType, model: str) -> ProviderModelSetting:
        """
        Disable model load balancing.
        :param model_type: model type
        :param model: model name
        :return:
        """
        model_setting = db.session.query(ProviderModelSetting) \
            .filter(
            ProviderModelSetting.tenant_id == self.tenant_id,
            ProviderModelSetting.provider_name == self.provider.provider,
            ProviderModelSetting.model_type == model_type.to_origin_model_type(),
            ProviderModelSetting.model_name == model
        ).first()

        if model_setting:
            model_setting.load_balancing_enabled = False
            model_setting.updated_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            db.session.commit()
        else:
            model_setting = ProviderModelSetting(
                tenant_id=self.tenant_id,
                provider_name=self.provider.provider,
                model_type=model_type.to_origin_model_type(),
                model_name=model,
                load_balancing_enabled=False
            )
            db.session.add(model_setting)
            db.session.commit()

        return model_setting

    def get_provider_instance(self) -> ModelProvider:
        """
        Get provider instance.
        :return:
        """
        return model_provider_factory.get_provider_instance(self.provider.provider)

    def get_model_type_instance(self, model_type: ModelType) -> AIModel:
        """
        Get current model type instance.

        :param model_type: model type
        :return:
        """
        # Get provider instance
        provider_instance = self.get_provider_instance()

        # 根据模型类型获取LLM的模型实例
        return provider_instance.get_model_instance(model_type)

    def switch_preferred_provider_type(self, provider_type: ProviderType) -> None:
        """
        切换首选服务提供商类型。
        :param provider_type: 指定的服务提供商类型
        :return: 无返回值
        """
        # 如果指定的服务提供商类型与当前首选类型相同，则不进行任何操作
        if provider_type == self.preferred_provider_type:
            return

        # 如果指定为系统服务提供商，但系统配置未启用，则不进行任何操作
        if provider_type == ProviderType.SYSTEM and not self.system_configuration.enabled:
            return

        # 查询当前租户的首选模型服务提供商
        preferred_model_provider = db.session.query(TenantPreferredModelProvider) \
            .filter(
            TenantPreferredModelProvider.tenant_id == self.tenant_id,
            TenantPreferredModelProvider.provider_name == self.provider.provider
        ).first()

        # 如果已存在首选模型服务提供商，则更新其首选类型；否则，创建新的记录
        if preferred_model_provider:
            preferred_model_provider.preferred_provider_type = provider_type.value
        else:
            preferred_model_provider = TenantPreferredModelProvider(
                tenant_id=self.tenant_id,
                provider_name=self.provider.provider,
                preferred_provider_type=provider_type.value
            )
            db.session.add(preferred_model_provider)

        # 提交数据库会话，保存更改
        db.session.commit()

    def extract_secret_variables(self, credential_form_schemas: list[CredentialFormSchema]) -> list[str]:
        """
        Extract secret input form variables.

        :param credential_form_schemas:
        :return:
        """
        secret_input_form_variables = []  # 初始化存储秘密输入表单变量的列表
        for credential_form_schema in credential_form_schemas:
            # 如果表单类型为秘密输入，则将变量名添加到列表中
            if credential_form_schema.type == FormType.SECRET_INPUT:
                secret_input_form_variables.append(credential_form_schema.variable)

        return secret_input_form_variables

    def obfuscated_credentials(self, credentials: dict, credential_form_schemas: list[CredentialFormSchema]) -> dict:
        """
        对凭据进行混淆处理。

        :param credentials: 凭据字典，包含需要保护的敏感信息。
        :param credential_form_schemas: 凭据表单模式列表，用于定义哪些凭据字段是敏感的。
        :return: 混淆后的凭据字典，敏感信息被替换为混淆后的值。
        """
        # Get provider credential secret variables
        credential_secret_variables = self.extract_secret_variables(
            credential_form_schemas
        )

        # 复制原始凭据字典，然后对敏感凭据进行混淆
        copy_credentials = credentials.copy()
        for key, value in copy_credentials.items():
            if key in credential_secret_variables:
                # 对确定为敏感的凭证项进行混淆处理
                copy_credentials[key] = encrypter.obfuscated_token(value)

        return copy_credentials

    def get_provider_model(self, model_type: ModelType,
                        model: str,
                        only_active: bool = False) -> Optional[ModelWithProviderEntity]:
        """
        获取指定模型类型的提供者模型。
        
        :param model_type: 模型类型
        :param model: 模型名称
        :param only_active: 仅返回激活状态的模型
        :return: 如果找到匹配的模型，则返回 ModelWithProviderEntity 类型的对象；否则返回 None
        """
        # 获取所有指定模型类型的提供者模型
        provider_models = self.get_provider_models(model_type, only_active)

        # 遍历提供者模型列表，查找匹配的模型
        for provider_model in provider_models:
            if provider_model.model == model:
                return provider_model

        # 如果没有找到匹配的模型，返回 None
        return None

    def get_provider_models(self, model_type: Optional[ModelType] = None,
                            only_active: bool = False) -> list[ModelWithProviderEntity]:
        """
        获取提供者模型。
        :param model_type: 模型类型。如果提供，将仅获取该类型的模型。
        :param only_active: 仅获取活跃模型的标志。如果为True，则只返回状态为活跃的模型。
        :return: 返回一个排序后的模型列表，列表中的元素是带有提供者实体的模型。

        主要步骤包括：
        - 获取提供者实例。
        - 确定要查询的模型类型，如果没有指定模型类型，则获取提供者支持的所有模型类型。
        - 根据使用的提供者类型，调用相应的函数获取模型。
        - 如果需要，筛选出活跃的模型。
        - 最后，按模型类型值进行排序返回。
        """
        provider_instance = self.get_provider_instance()  # 获取提供者实例

        model_types = []
        if model_type:
            model_types.append(model_type)  # 如果指定了模型类型，只查询该类型
        else:
            # 如果没有指定模型类型，获取提供者支持的所有模型类型
            model_types = provider_instance.get_provider_schema().supported_model_types

        # Group model settings by model type and model
        model_setting_map = defaultdict(dict)
        for model_setting in self.model_settings:
            model_setting_map[model_setting.model_type][model_setting.model] = model_setting

        if self.using_provider_type == ProviderType.SYSTEM:
            provider_models = self._get_system_provider_models(
                model_types=model_types,
                provider_instance=provider_instance,
                model_setting_map=model_setting_map
            )
        else:
            provider_models = self._get_custom_provider_models(
                model_types=model_types,
                provider_instance=provider_instance,
                model_setting_map=model_setting_map
            )

        # 如果需要，筛选出活跃的模型
        if only_active:
            provider_models = [m for m in provider_models if m.status == ModelStatus.ACTIVE]

        # 对获取的模型按模型类型值进行排序
        return sorted(provider_models, key=lambda x: x.model_type.value)

    def _get_system_provider_models(self,
                                    model_types: list[ModelType],
                                    provider_instance: ModelProvider,
                                    model_setting_map: dict[ModelType, dict[str, ModelSettings]]) \
            -> list[ModelWithProviderEntity]:
        """
        获取系统提供者的模型信息。

        :param model_types: model types
        :param provider_instance: provider instance
        :param model_setting_map: model setting map
        :return:
        """
        provider_models = []
        # 遍历模型类型，获取每种类型下的模型信息
        for model_type in model_types:
            for m in provider_instance.models(model_type):
                status = ModelStatus.ACTIVE
                if m.model_type in model_setting_map and m.model in model_setting_map[m.model_type]:
                    model_setting = model_setting_map[m.model_type][m.model]
                    if model_setting.enabled is False:
                        status = ModelStatus.DISABLED

                provider_models.append(
                    ModelWithProviderEntity(
                        model=m.model,
                        label=m.label,
                        model_type=m.model_type,
                        features=m.features,
                        fetch_from=m.fetch_from,
                        model_properties=m.model_properties,
                        deprecated=m.deprecated,
                        provider=SimpleModelProviderEntity(self.provider),
                        status=status
                    )
                )

        # 初始化或更新提供者的配置方法列表
        if self.provider.provider not in original_provider_configurate_methods:
            original_provider_configurate_methods[self.provider.provider] = []
            for configurate_method in provider_instance.get_provider_schema().configurate_methods:
                original_provider_configurate_methods[self.provider.provider].append(configurate_method)

        # 判断是否应使用自定义模型配置
        should_use_custom_model = False
        if original_provider_configurate_methods[self.provider.provider] == [ConfigurateMethod.CUSTOMIZABLE_MODEL]:
            should_use_custom_model = True

        # 根据配额配置筛选模型
        for quota_configuration in self.system_configuration.quota_configurations:
            if self.system_configuration.current_quota_type != quota_configuration.quota_type:
                continue

            restrict_models = quota_configuration.restrict_models
            if len(restrict_models) == 0:
                break

            if should_use_custom_model:
                if original_provider_configurate_methods[self.provider.provider] == [
                    ConfigurateMethod.CUSTOMIZABLE_MODEL]:
                    # only customizable model
                    for restrict_model in restrict_models:
                        copy_credentials = self.system_configuration.credentials.copy()
                        if restrict_model.base_model_name:
                            copy_credentials['base_model_name'] = restrict_model.base_model_name

                        try:
                            custom_model_schema = (
                                provider_instance.get_model_instance(restrict_model.model_type)
                                .get_customizable_model_schema_from_credentials(
                                    restrict_model.model,
                                    copy_credentials
                                )
                            )
                        except Exception as ex:
                            logger.warning(f'获取自定义模型架构失败，{ex}')
                            continue

                        if not custom_model_schema:
                            continue

                        if custom_model_schema.model_type not in model_types:
                            continue

                        status = ModelStatus.ACTIVE
                        if (custom_model_schema.model_type in model_setting_map
                                and custom_model_schema.model in model_setting_map[custom_model_schema.model_type]):
                            model_setting = model_setting_map[custom_model_schema.model_type][custom_model_schema.model]
                            if model_setting.enabled is False:
                                status = ModelStatus.DISABLED

                        provider_models.append(
                            ModelWithProviderEntity(
                                model=custom_model_schema.model,
                                label=custom_model_schema.label,
                                model_type=custom_model_schema.model_type,
                                features=custom_model_schema.features,
                                fetch_from=FetchFrom.PREDEFINED_MODEL,
                                model_properties=custom_model_schema.model_properties,
                                deprecated=custom_model_schema.deprecated,
                                provider=SimpleModelProviderEntity(self.provider),
                                status=status
                            )
                        )

            # 如果模型名称不在受限模型列表中，将其状态设置为无权限
            restrict_model_names = [rm.model for rm in restrict_models]
            for m in provider_models:
                if m.model_type == ModelType.LLM and m.model not in restrict_model_names:
                    m.status = ModelStatus.NO_PERMISSION
                elif not quota_configuration.is_valid:
                    m.status = ModelStatus.QUOTA_EXCEEDED

        return provider_models

    def _get_custom_provider_models(self,
                                    model_types: list[ModelType],
                                    provider_instance: ModelProvider,
                                    model_setting_map: dict[ModelType, dict[str, ModelSettings]]) \
            -> list[ModelWithProviderEntity]:
        """
        获取自定义提供者模型。

        :param model_types: model types
        :param provider_instance: provider instance
        :param model_setting_map: model setting map
        :return:
        """
        provider_models = []

        # 根据自定义配置获取提供者凭证
        credentials = None
        if self.custom_configuration.provider:
            credentials = self.custom_configuration.provider.credentials

        # 遍历模型类型，获取支持的模型
        for model_type in model_types:
            if model_type not in self.provider.supported_model_types:
                continue

            models = provider_instance.models(model_type)
            for m in models:
                status = ModelStatus.ACTIVE if credentials else ModelStatus.NO_CONFIGURE
                load_balancing_enabled = False
                if m.model_type in model_setting_map and m.model in model_setting_map[m.model_type]:
                    model_setting = model_setting_map[m.model_type][m.model]
                    if model_setting.enabled is False:
                        status = ModelStatus.DISABLED

                    if len(model_setting.load_balancing_configs) > 1:
                        load_balancing_enabled = True

                provider_models.append(
                    ModelWithProviderEntity(
                        model=m.model,
                        label=m.label,
                        model_type=m.model_type,
                        features=m.features,
                        fetch_from=m.fetch_from,
                        model_properties=m.model_properties,
                        deprecated=m.deprecated,
                        provider=SimpleModelProviderEntity(self.provider),
                        status=status,
                        load_balancing_enabled=load_balancing_enabled
                    )
                )

        # 处理自定义模型配置
        for model_configuration in self.custom_configuration.models:
            if model_configuration.model_type not in model_types:
                continue

            try:
                # 尝试根据模型配置获取自定义模型的schema
                custom_model_schema = (
                    provider_instance.get_model_instance(model_configuration.model_type)
                    .get_customizable_model_schema_from_credentials(
                        model_configuration.model,
                        model_configuration.credentials
                    )
                )
            except Exception as ex:
                logger.warning(f'获取自定义模型schema失败，{ex}')
                continue

            if not custom_model_schema:
                continue

            status = ModelStatus.ACTIVE
            load_balancing_enabled = False
            if (custom_model_schema.model_type in model_setting_map
                    and custom_model_schema.model in model_setting_map[custom_model_schema.model_type]):
                model_setting = model_setting_map[custom_model_schema.model_type][custom_model_schema.model]
                if model_setting.enabled is False:
                    status = ModelStatus.DISABLED

                if len(model_setting.load_balancing_configs) > 1:
                    load_balancing_enabled = True

            provider_models.append(
                ModelWithProviderEntity(
                    model=custom_model_schema.model,
                    label=custom_model_schema.label,
                    model_type=custom_model_schema.model_type,
                    features=custom_model_schema.features,
                    fetch_from=custom_model_schema.fetch_from,
                    model_properties=custom_model_schema.model_properties,
                    deprecated=custom_model_schema.deprecated,
                    provider=SimpleModelProviderEntity(self.provider),
                    status=status,
                    load_balancing_enabled=load_balancing_enabled
                )
            )

        return provider_models


class ProviderConfigurations(BaseModel):
    """
    供应商配置模型类，用于管理供应商配置字典。
    """
    tenant_id: str  # 租户ID
    configurations: dict[str, ProviderConfiguration] = {}  # 供应商配置字典

    def __init__(self, tenant_id: str):
        """
        初始化供应商配置。

        :param tenant_id: 租户ID
        """
        super().__init__(tenant_id=tenant_id)

    def get_models(self,
                   provider: Optional[str] = None,
                   model_type: Optional[ModelType] = None,
                   only_active: bool = False) \
            -> list[ModelWithProviderEntity]:
        """
        获取可用模型列表。

        如果首选供应商类型为`system`：
          获取当前**系统模式**（如果供应商支持），如果所有系统模式不可用（无配额），则视为**自定义凭证模式**。
          如果自定义模式中没有配置模型，则视为未配置。
        system > custom > no_configure

        如果首选供应商类型为`custom`：
          如果配置了自定义凭证，则视为自定义模式。
          否则，获取当前**系统模式**（如果支持），
          如果所有系统模式不可用（无配额），则视为未配置。
        custom > system > no_configure

        如果实际模式为`system`，使用系统凭证获取模型，
          付费配额 > 供应商免费配额 > 系统免费配额
          包括预定义模型（排除GPT-4，状态标记为`no_permission`）。
        如果实际模式为`custom`，使用工作空间自定义凭证获取模型，
          包括预定义模型，自定义模型（手动附加）。
        如果实际模式为`no_configure`，仅从`模型运行时`返回预定义模型。
          （如果首选供应商类型为`custom`，则模型状态标记为`no_configure`，否则标记为`quota_exceeded`）
        状态标记为`active`的模型可用。

        :param provider: 供应商名称
        :param model_type: 模型类型
        :param only_active: 仅获取活跃模型
        :return: 模型列表
        """
        all_models = []
        for provider_configuration in self.values():
            # 过滤指定供应商的模型
            if provider and provider_configuration.provider.provider != provider:
                continue

            # 获取并扩展供应商的模型列表
            all_models.extend(provider_configuration.get_provider_models(model_type, only_active))

        return all_models

    def to_list(self) -> list[ProviderConfiguration]:
        """
        转换为列表形式。

        :return: 供应商配置列表
        """
        return list(self.values())

    def __getitem__(self, key):
        """
        通过键获取配置。

        :param key: 配置键
        :return: 配置项
        """
        return self.configurations[key]

    def __setitem__(self, key, value):
        """
        通过键设置配置。

        :param key: 配置键
        :param value: 配置值
        """
        self.configurations[key] = value

    def __iter__(self):
        """
        迭代配置项。

        :return: 迭代器
        """
        return iter(self.configurations)

    def values(self) -> Iterator[ProviderConfiguration]:
        """
        获取配置值迭代器。

        :return: 配置值迭代器
        """
        return self.configurations.values()

    def get(self, key, default=None):
        """
        通过键获取配置值，如果不存在则返回默认值。

        :param key: 配置键
        :param default: 默认值
        :return: 配置值或默认值
        """
        return self.configurations.get(key, default)


class ProviderModelBundle(BaseModel):
    """
    提供者模型捆绑类，用于封装与提供者相关的模型配置、实例和模型类型实例。

    属性:
        configuration (ProviderConfiguration): 提供者配置，包含提供者的具体配置信息。
        provider_instance (ModelProvider): 提供者实例，代表一个具体的模型提供者。
        model_type_instance (AIModel): 模型类型实例，代表一种人工智能模型类型。
    """

    configuration: ProviderConfiguration
    provider_instance: ModelProvider
    model_type_instance: AIModel

    # pydantic configs
    model_config = ConfigDict(arbitrary_types_allowed=True,
                              protected_namespaces=())
