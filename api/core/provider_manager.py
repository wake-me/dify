import json
from collections import defaultdict
from json import JSONDecodeError
from typing import Optional

from sqlalchemy.exc import IntegrityError

from configs import dify_config
from core.entities.model_entities import DefaultModelEntity, DefaultModelProviderEntity
from core.entities.provider_configuration import ProviderConfiguration, ProviderConfigurations, ProviderModelBundle
from core.entities.provider_entities import (
    CustomConfiguration,
    CustomModelConfiguration,
    CustomProviderConfiguration,
    ModelLoadBalancingConfiguration,
    ModelSettings,
    QuotaConfiguration,
    SystemConfiguration,
)
from core.helper import encrypter
from core.helper.model_provider_cache import ProviderCredentialsCache, ProviderCredentialsCacheType
from core.helper.position_helper import is_filtered
from core.model_runtime.entities.model_entities import ModelType
from core.model_runtime.entities.provider_entities import CredentialFormSchema, FormType, ProviderEntity
from core.model_runtime.model_providers import model_provider_factory
from extensions import ext_hosting_provider
from extensions.ext_database import db
from extensions.ext_redis import redis_client
from models.provider import (
    LoadBalancingModelConfig,
    Provider,
    ProviderModel,
    ProviderModelSetting,
    ProviderQuotaType,
    ProviderType,
    TenantDefaultModel,
    TenantPreferredModelProvider,
)
from services.feature_service import FeatureService


class ProviderManager:
    """
    ProviderManager 是一个管理模型提供者类，包括托管和自定义模型提供者。
    """

    def __init__(self) -> None:
        """
        初始化 ProviderManager，设置默认值。
        """
        self.decoding_rsa_key = None
        self.decoding_cipher_rsa = None

    def get_configurations(self, tenant_id: str) -> ProviderConfigurations:
        """
        获取模型提供者的配置信息。

        构建每个提供者的 ProviderConfiguration 对象，包括：
        1. 提供者的基本信息。
        2. 托管配置信息，如：
          (1) 是否启用（支持）托管类型，如果启用，则存在以下信息：
          (2) 托管类型提供商配置列表（包括配额类型、配额限制、当前剩余配额等）。
          (3) 当前使用的托管类型（是否有配额）：付费配额 > 提供者免费配额 > 托管试用配额
          (4) 托管提供商的统一凭证。
        3. 自定义配置信息，如：
          (1) 是否启用（支持）自定义类型，如果启用，则存在以下信息：
          (2) 自定义提供商配置（包括凭证）。
          (3) 自定义提供商模型配置列表（包括凭证）。
        4. 托管/自定义优先级提供商类型。
        提供的方法：
        - 获取当前配置（包括凭证）
        - 获取托管配置的可用性和状态：活动可用、配额超出、不支持托管
        - 获取自定义配置的可用性
          自定义提供商可用条件：
          (1) 自定义提供商凭证可用
          (2) 至少有一个自定义模型凭证可用
        - 验证、更新和删除自定义提供商配置
        - 验证、更新和删除自定义提供商模型配置
        - 获取可用模型列表（可选提供者过滤，模型类型过滤）
          将自定义提供商模型追加到列表中
        - 获取提供商实例
        - 切换选择优先级

        :param tenant_id: 工作空间的唯一标识。
        :return: 包含所有提供商配置的 ProviderConfigurations 对象。
        """
        # 获取工作空间的所有提供商记录
        provider_name_to_provider_records_dict = self._get_all_providers(tenant_id)

        # 如果不存在，初始化试用提供商记录
        provider_name_to_provider_records_dict = self._init_trial_provider_records(
            tenant_id,
            provider_name_to_provider_records_dict
        )

        # 获取工作空间的所有提供商模型记录
        provider_name_to_provider_model_records_dict = self._get_all_provider_models(tenant_id)

        # 获取所有提供商实体
        provider_entities = model_provider_factory.get_providers()

        # 获取工作空间的所有首选模型提供商类型
        provider_name_to_preferred_model_provider_records_dict = self._get_all_preferred_model_providers(tenant_id)

        # Get All provider model settings
        provider_name_to_provider_model_settings_dict = self._get_all_provider_model_settings(tenant_id)

        # Get All load balancing configs
        provider_name_to_provider_load_balancing_model_configs_dict \
            = self._get_all_provider_load_balancing_configs(tenant_id)

        provider_configurations = ProviderConfigurations(
            tenant_id=tenant_id
        )

        # 为每个提供商构建 ProviderConfiguration 对象
        for provider_entity in provider_entities:

            # handle include, exclude
            if is_filtered(
                    include_set=dify_config.POSITION_PROVIDER_INCLUDES_SET,
                    exclude_set=dify_config.POSITION_PROVIDER_EXCLUDES_SET,
                    data=provider_entity,
                    name_func=lambda x: x.provider,
            ):
                continue

            provider_name = provider_entity.provider
            provider_records = provider_name_to_provider_records_dict.get(provider_entity.provider, [])
            provider_model_records = provider_name_to_provider_model_records_dict.get(provider_entity.provider, [])

            # 转换为自定义配置
            custom_configuration = self._to_custom_configuration(
                tenant_id,
                provider_entity,
                provider_records,
                provider_model_records
            )

            # 转换为系统配置
            system_configuration = self._to_system_configuration(
                tenant_id,
                provider_entity,
                provider_records
            )

            # 获取首选提供商类型
            preferred_provider_type_record = provider_name_to_preferred_model_provider_records_dict.get(provider_name)

            if preferred_provider_type_record:
                preferred_provider_type = ProviderType.value_of(preferred_provider_type_record.preferred_provider_type)
            elif custom_configuration.provider or custom_configuration.models:
                preferred_provider_type = ProviderType.CUSTOM
            elif system_configuration.enabled:
                preferred_provider_type = ProviderType.SYSTEM
            else:
                preferred_provider_type = ProviderType.CUSTOM

            using_provider_type = preferred_provider_type
            has_valid_quota = any(quota_conf.is_valid for quota_conf in system_configuration.quota_configurations)

            if preferred_provider_type == ProviderType.SYSTEM:
                if not system_configuration.enabled or not has_valid_quota:
                    using_provider_type = ProviderType.CUSTOM

            else:
                # 如果没有完全配置自定义提供商，回退到系统提供商
                if not custom_configuration.provider and not custom_configuration.models:
                    if system_configuration.enabled and has_valid_quota:
                        using_provider_type = ProviderType.SYSTEM

            # Get provider load balancing configs
            provider_model_settings = provider_name_to_provider_model_settings_dict.get(provider_name)

            # Get provider load balancing configs
            provider_load_balancing_configs \
                = provider_name_to_provider_load_balancing_model_configs_dict.get(provider_name)

            # Convert to model settings
            model_settings = self._to_model_settings(
                provider_entity=provider_entity,
                provider_model_settings=provider_model_settings,
                load_balancing_model_configs=provider_load_balancing_configs
            )

            provider_configuration = ProviderConfiguration(
                tenant_id=tenant_id,
                provider=provider_entity,
                preferred_provider_type=preferred_provider_type,
                using_provider_type=using_provider_type,
                system_configuration=system_configuration,
                custom_configuration=custom_configuration,
                model_settings=model_settings
            )

            provider_configurations[provider_name] = provider_configuration

        # 返回封装的对象
        return provider_configurations

    def get_provider_model_bundle(self, tenant_id: str, provider: str, model_type: ModelType) -> ProviderModelBundle:
        """
        获取供应商模型捆绑包。
        :param tenant_id: 工作空间id
        :param provider: 供应商名称
        :param model_type: 模型类型
        :return: 返回一个包含供应商配置、供应商实例和模型类型实例的ProviderModelBundle对象
        """
        # 获取租户的配置信息
        provider_configurations = self.get_configurations(tenant_id)

        # 获取指定供应商的配置
        provider_configuration = provider_configurations.get(provider)
        if not provider_configuration:
            raise ValueError(f"Provider {provider} does not exist.")

        # 创建供应商实例
        provider_instance = provider_configuration.get_provider_instance()
        # 创建模型类型实例
        model_type_instance = provider_instance.get_model_instance(model_type)

        # 返回供应商模型捆绑包
        return ProviderModelBundle(
            configuration=provider_configuration,
            provider_instance=provider_instance,
            model_type_instance=model_type_instance
        )

    def get_default_model(self, tenant_id: str, model_type: ModelType) -> Optional[DefaultModelEntity]:
        """
        获取默认模型。

        :param tenant_id: 工作空间ID
        :param model_type: 模型类型
        :return: 返回默认模型实体，如果不存在则返回None
        """
        # 查询对应的TenantDefaultModel记录
        default_model = db.session.query(TenantDefaultModel) \
            .filter(
            TenantDefaultModel.tenant_id == tenant_id,
            TenantDefaultModel.model_type == model_type.to_origin_model_type()
        ).first()

        # 如果不存在，则从get_configurations获取可用的提供者模型，并更新TenantDefaultModel记录
        if not default_model:
            # 获取提供者配置
            provider_configurations = self.get_configurations(tenant_id)

            # 从提供者配置中获取可用模型
            available_models = provider_configurations.get_models(
                model_type=model_type,
                only_active=True
            )

            if available_models:
                available_model = next((model for model in available_models if model.model == "gpt-4"),
                                       available_models[0])

                default_model = TenantDefaultModel(
                    tenant_id=tenant_id,
                    model_type=model_type.to_origin_model_type(),
                    provider_name=available_model.provider.provider,
                    model_name=available_model.model
                )
                db.session.add(default_model)
                db.session.commit()

        # 如果没有找到默认模型，返回None
        if not default_model:
            return None

        # 获取提供者实例和提供者方案
        provider_instance = model_provider_factory.get_provider_instance(default_model.provider_name)
        provider_schema = provider_instance.get_provider_schema()

        # 构建并返回默认模型实体
        return DefaultModelEntity(
            model=default_model.model_name,
            model_type=model_type,
            provider=DefaultModelProviderEntity(
                provider=provider_schema.provider,
                label=provider_schema.label,
                icon_small=provider_schema.icon_small,
                icon_large=provider_schema.icon_large,
                supported_model_types=provider_schema.supported_model_types
            )
        )

    def get_first_provider_first_model(self, tenant_id: str, model_type: ModelType) -> tuple[str, str]:
        """
        Get names of first model and its provider

        :param tenant_id: workspace id
        :param model_type: model type
        :return: provider name, model name
        """
        provider_configurations = self.get_configurations(tenant_id)

        # get available models from provider_configurations
        all_models = provider_configurations.get_models(
            model_type=model_type,
            only_active=False
        )

        return all_models[0].provider.provider, all_models[0].model

    def update_default_model_record(self, tenant_id: str, model_type: ModelType, provider: str, model: str) \
            -> TenantDefaultModel:
        """
        更新默认模型记录。

        :param tenant_id: 工作空间ID
        :param model_type: 模型类型
        :param provider: 提供者名称
        :param model: 模型名称
        :return: 返回更新或创建的默认模型记录
        """
        # 获取配置信息
        provider_configurations = self.get_configurations(tenant_id)
        # 检查提供者是否存在
        if provider not in provider_configurations:
            raise ValueError(f"Provider {provider} does not exist.")

        # 从提供者配置中获取可用模型
        available_models = provider_configurations.get_models(
            model_type=model_type,
            only_active=True
        )
        # 检查模型是否存在于可用模型中
        model_names = [model.model for model in available_models]
        if model not in model_names:
            raise ValueError(f"Model {model} does not exist.")

        # 从数据库查询当前的默认模型设置
        default_model = db.session.query(TenantDefaultModel) \
            .filter(
            TenantDefaultModel.tenant_id == tenant_id,
            TenantDefaultModel.model_type == model_type.to_origin_model_type()
        ).first()

        # 如果默认模型已存在，则更新；否则，创建新的默认模型记录
        if default_model:
            # 更新默认模型信息
            default_model.provider_name = provider
            default_model.model_name = model
            db.session.commit()
        else:
            # 创建新的默认模型记录
            default_model = TenantDefaultModel(
                tenant_id=tenant_id,
                model_type=model_type.value,
                provider_name=provider,
                model_name=model,
            )
            db.session.add(default_model)
            db.session.commit()

        return default_model

    def _get_all_providers(self, tenant_id: str) -> dict[str, list[Provider]]:
        """
        获取工作空间的所有有效提供者记录。

        该函数根据给定的工作空间ID（tenant_id）查询数据库中的所有提供者，
        并过滤掉无效的提供者。然后，它将提供者按名称分组，返回一个字典，
        其中每个键是提供者名称，值是具有该名称的Provider对象列表。

        :param tenant_id: 工作空间的唯一标识符，用于筛选返回的提供者，确保仅包含与指定工作空间关联的提供者。
        :return: 一个字典，其中每个键是提供者名称，值是与该名称关联的Provider对象列表。
                这使得可以通过名称快速访问所有提供者。
        """
        # 根据指定的tenant_id查询数据库，获取所有有效且关联的提供者。
        providers = db.session.query(Provider) \
            .filter(
            Provider.tenant_id == tenant_id,
            Provider.is_valid == True
        ).all()

        # 初始化一个字典，用于按提供者名称进行分组。
        provider_name_to_provider_records_dict = defaultdict(list)
        # 遍历查询到的提供者，将它们按名称分组到字典中。
        for provider in providers:
            provider_name_to_provider_records_dict[provider.provider_name].append(provider)

        # 返回填充后的字典，允许通过名称轻松访问提供者。
        return provider_name_to_provider_records_dict

    def _get_all_provider_models(self, tenant_id: str) -> dict[str, list[ProviderModel]]:
        """
        获取指定工作区下的所有供应商模型记录。

        此函数负责从数据库中查询并收集与给定工作区ID（tenant_id）相关的所有有效供应商模型数据。
        它将这些数据整理成一个字典，其中键是供应商名称，值是属于该供应商的模型列表。

        :param tenant_id: 工作区的唯一标识符，用于定位要查询的数据。
        :return: 一个字典，结构为供应商名称到该供应商相关模型列表的映射。
        """
        # 查询数据库，筛选条件为租户ID匹配且模型有效
        provider_models = db.session.query(ProviderModel) \
            .filter(
                ProviderModel.tenant_id == tenant_id,
                ProviderModel.is_valid == True
            ).all()

        # 初始化一个默认字典，用于存储按供应商名称分组的模型记录
        provider_name_to_model_records_dict = defaultdict(list)

        # 遍历查询结果，按供应商名称归类模型记录
        for provider_model in provider_models:
            provider_name_to_model_records_dict[provider_model.provider_name].append(provider_model)

        # 返回分组后的供应商模型字典
        return provider_name_to_model_records_dict

    def _get_all_preferred_model_providers(self, tenant_id: str) -> dict[str, TenantPreferredModelProvider]:
        """
        获取工作空间的所有首选提供者类型。

        :param tenant_id: workspace id
        :return:
        """
        # 从数据库会话中查询指定租户ID的所有首选模型提供者类型记录
        preferred_provider_types = db.session.query(TenantPreferredModelProvider) \
            .filter(
            TenantPreferredModelProvider.tenant_id == tenant_id
        ).all()

        # 将查询结果转换为字典格式，方便后续使用
        provider_name_to_preferred_provider_type_records_dict = {
            preferred_provider_type.provider_name: preferred_provider_type
            for preferred_provider_type in preferred_provider_types
        }

        return provider_name_to_preferred_provider_type_records_dict

    def _get_all_provider_model_settings(self, tenant_id: str) -> dict[str, list[ProviderModelSetting]]:
        """
        Get All provider model settings of the workspace.

        :param tenant_id: workspace id
        :return:
        """
        provider_model_settings = db.session.query(ProviderModelSetting) \
            .filter(
            ProviderModelSetting.tenant_id == tenant_id
        ).all()

        provider_name_to_provider_model_settings_dict = defaultdict(list)
        for provider_model_setting in provider_model_settings:
            (provider_name_to_provider_model_settings_dict[provider_model_setting.provider_name]
             .append(provider_model_setting))

        return provider_name_to_provider_model_settings_dict

    def _get_all_provider_load_balancing_configs(self, tenant_id: str) -> dict[str, list[LoadBalancingModelConfig]]:
        """
        Get All provider load balancing configs of the workspace.

        :param tenant_id: workspace id
        :return:
        """
        cache_key = f"tenant:{tenant_id}:model_load_balancing_enabled"
        cache_result = redis_client.get(cache_key)
        if cache_result is None:
            model_load_balancing_enabled = FeatureService.get_features(tenant_id).model_load_balancing_enabled
            redis_client.setex(cache_key, 120, str(model_load_balancing_enabled))
        else:
            cache_result = cache_result.decode('utf-8')
            model_load_balancing_enabled = cache_result == 'True'

        if not model_load_balancing_enabled:
            return {}

        provider_load_balancing_configs = db.session.query(LoadBalancingModelConfig) \
            .filter(
            LoadBalancingModelConfig.tenant_id == tenant_id
        ).all()

        provider_name_to_provider_load_balancing_model_configs_dict = defaultdict(list)
        for provider_load_balancing_config in provider_load_balancing_configs:
            (provider_name_to_provider_load_balancing_model_configs_dict[provider_load_balancing_config.provider_name]
             .append(provider_load_balancing_config))

        return provider_name_to_provider_load_balancing_model_configs_dict

    def _init_trial_provider_records(self, tenant_id: str,
                                     provider_name_to_provider_records_dict: dict[str, list]) -> dict[str, list]:
        """
        Initialize trial provider records if not exists.

        :param tenant_id: workspace id
        :param provider_name_to_provider_records_dict: provider name to provider records dict
        :return:
        """
        # Get hosting configuration
        hosting_configuration = ext_hosting_provider.hosting_configuration

        # 遍历托管配置中的提供商，初始化试用提供商记录
        for provider_name, configuration in hosting_configuration.provider_map.items():
            if not configuration.enabled:
                continue  # 跳过未启用的提供商

            provider_records = provider_name_to_provider_records_dict.get(provider_name)
            if not provider_records:
                provider_records = []

            provider_quota_to_provider_record_dict = {}
            for provider_record in provider_records:
                if provider_record.provider_type != ProviderType.SYSTEM.value:
                    continue  # 忽略非系统类型的提供商记录

                # 将符合条件的提供商记录映射到其配额类型
                provider_quota_to_provider_record_dict[ProviderQuotaType.value_of(provider_record.quota_type)] \
                    = provider_record

            # 初始化试用配额的提供商记录
            for quota in configuration.quotas:
                if quota.quota_type == ProviderQuotaType.TRIAL:
                    # 如果当前提供商不存在试用配额记录，则进行初始化
                    if ProviderQuotaType.TRIAL not in provider_quota_to_provider_record_dict:
                        try:
                            # 尝试创建新的试用提供商记录并添加到数据库
                            provider_record = Provider(
                                tenant_id=tenant_id,
                                provider_name=provider_name,
                                provider_type=ProviderType.SYSTEM.value,
                                quota_type=ProviderQuotaType.TRIAL.value,
                                quota_limit=quota.quota_limit,
                                quota_used=0,
                                is_valid=True
                            )
                            db.session.add(provider_record)
                            db.session.commit()
                        except IntegrityError:
                            # 在插入时遇到唯一性约束异常，则尝试从数据库获取已存在的记录进行更新
                            db.session.rollback()
                            provider_record = db.session.query(Provider) \
                                .filter(
                                Provider.tenant_id == tenant_id,
                                Provider.provider_name == provider_name,
                                Provider.provider_type == ProviderType.SYSTEM.value,
                                Provider.quota_type == ProviderQuotaType.TRIAL.value
                            ).first()

                            # 如果找到存在的记录且其状态无效，则将其状态更新为有效
                            if provider_record and not provider_record.is_valid:
                                provider_record.is_valid = True
                                db.session.commit()

                        # 将新初始化的或已存在的试用提供商记录添加到字典中
                        provider_name_to_provider_records_dict[provider_name].append(provider_record)

        return provider_name_to_provider_records_dict

    def _to_custom_configuration(self,
                                tenant_id: str,
                                provider_entity: ProviderEntity,
                                provider_records: list[Provider],
                                provider_model_records: list[ProviderModel]) -> CustomConfiguration:
        """
        将相关信息转换为自定义配置。

        :param tenant_id: 工作空间ID
        :param provider_entity: 供应商实体
        :param provider_records: 供应商记录列表
        :param provider_model_records: 供应商模型记录列表
        :return: 自定义配置对象
        """
        # 提取供应商凭证的密钥变量
        provider_credential_secret_variables = self._extract_secret_variables(
            provider_entity.provider_credential_schema.credential_form_schemas
            if provider_entity.provider_credential_schema else []
        )

        # 获取自定义供应商记录
        custom_provider_record = None
        for provider_record in provider_records:
            if provider_record.provider_type == ProviderType.SYSTEM.value:
                continue

            if not provider_record.encrypted_config:
                continue

            custom_provider_record = provider_record

        # 获取自定义供应商凭证配置
        custom_provider_configuration = None
        if custom_provider_record:
            provider_credentials_cache = ProviderCredentialsCache(
                tenant_id=tenant_id,
                identity_id=custom_provider_record.id,
                cache_type=ProviderCredentialsCacheType.PROVIDER
            )

            # 获取缓存的供应商凭证
            cached_provider_credentials = provider_credentials_cache.get()

            if not cached_provider_credentials:
                try:
                    # fix origin data
                    if (custom_provider_record.encrypted_config
                            and not custom_provider_record.encrypted_config.startswith("{")):
                        provider_credentials = {
                            "openai_api_key": custom_provider_record.encrypted_config
                        }
                    else:
                        provider_credentials = json.loads(custom_provider_record.encrypted_config)
                except JSONDecodeError:
                    provider_credentials = {}

                # 解密凭证信息
                if self.decoding_rsa_key is None or self.decoding_cipher_rsa is None:
                    self.decoding_rsa_key, self.decoding_cipher_rsa = encrypter.get_decrypt_decoding(tenant_id)

                for variable in provider_credential_secret_variables:
                    if variable in provider_credentials:
                        try:
                            provider_credentials[variable] = encrypter.decrypt_token_with_decoding(
                                provider_credentials.get(variable),
                                self.decoding_rsa_key,
                                self.decoding_cipher_rsa
                            )
                        except ValueError:
                            pass

                # 缓存供应商凭证
                provider_credentials_cache.set(
                    credentials=provider_credentials
                )
            else:
                provider_credentials = cached_provider_credentials

            custom_provider_configuration = CustomProviderConfiguration(
                credentials=provider_credentials
            )

        # 提取模型凭证的密钥变量
        model_credential_secret_variables = self._extract_secret_variables(
            provider_entity.model_credential_schema.credential_form_schemas
            if provider_entity.model_credential_schema else []
        )

        # 获取自定义模型凭证配置
        custom_model_configurations = []
        for provider_model_record in provider_model_records:
            if not provider_model_record.encrypted_config:
                continue

            provider_model_credentials_cache = ProviderCredentialsCache(
                tenant_id=tenant_id,
                identity_id=provider_model_record.id,
                cache_type=ProviderCredentialsCacheType.MODEL
            )

            # 获取缓存的模型凭证
            cached_provider_model_credentials = provider_model_credentials_cache.get()

            if not cached_provider_model_credentials:
                # 解析模型凭证
                try:
                    provider_model_credentials = json.loads(provider_model_record.encrypted_config)
                except JSONDecodeError:
                    continue

                # 解密凭证信息
                if self.decoding_rsa_key is None or self.decoding_cipher_rsa is None:
                    self.decoding_rsa_key, self.decoding_cipher_rsa = encrypter.get_decrypt_decoding(tenant_id)

                for variable in model_credential_secret_variables:
                    if variable in provider_model_credentials:
                        try:
                            provider_model_credentials[variable] = encrypter.decrypt_token_with_decoding(
                                provider_model_credentials.get(variable),
                                self.decoding_rsa_key,
                                self.decoding_cipher_rsa
                            )
                        except ValueError:
                            pass

                # 缓存模型凭证
                provider_model_credentials_cache.set(
                    credentials=provider_model_credentials
                )
            else:
                provider_model_credentials = cached_provider_model_credentials

            custom_model_configurations.append(
                CustomModelConfiguration(
                    model=provider_model_record.model_name,
                    model_type=ModelType.value_of(provider_model_record.model_type),
                    credentials=provider_model_credentials
                )
            )

        return CustomConfiguration(
            provider=custom_provider_configuration,
            models=custom_model_configurations
        )

    def _to_system_configuration(self,
                                tenant_id: str,
                                provider_entity: ProviderEntity,
                                provider_records: list[Provider]) -> SystemConfiguration:
        """
        将给定的参数转换为系统配置。

        :param tenant_id: 工作空间ID
        :param provider_entity: 提供者实体
        :param provider_records: 提供者记录列表
        :return: 系统配置对象
        """
        # 获取托管配置
        hosting_configuration = ext_hosting_provider.hosting_configuration

        # 检查提供者是否在托管配置中，以及是否启用
        if provider_entity.provider not in hosting_configuration.provider_map \
                or not hosting_configuration.provider_map.get(provider_entity.provider).enabled:
            return SystemConfiguration(
                enabled=False
            )

        provider_hosting_configuration = hosting_configuration.provider_map.get(provider_entity.provider)

        # Convert provider_records to dict
        quota_type_to_provider_records_dict = {}
        for provider_record in provider_records:
            if provider_record.provider_type != ProviderType.SYSTEM.value:
                continue

            quota_type_to_provider_records_dict[ProviderQuotaType.value_of(provider_record.quota_type)] \
                = provider_record

        quota_configurations = []
        for provider_quota in provider_hosting_configuration.quotas:
            # 根据配额类型获取相应的提供者记录
            if provider_quota.quota_type not in quota_type_to_provider_records_dict:
                if provider_quota.quota_type == ProviderQuotaType.FREE:
                    quota_configuration = QuotaConfiguration(
                        quota_type=provider_quota.quota_type,
                        quota_unit=provider_hosting_configuration.quota_unit,
                        quota_used=0,
                        quota_limit=0,
                        is_valid=False,
                        restrict_models=provider_quota.restrict_models
                    )
                else:
                    continue
            else:
                provider_record = quota_type_to_provider_records_dict[provider_quota.quota_type]

                quota_configuration = QuotaConfiguration(
                    quota_type=provider_quota.quota_type,
                    quota_unit=provider_hosting_configuration.quota_unit,
                    quota_used=provider_record.quota_used,
                    quota_limit=provider_record.quota_limit,
                    is_valid=provider_record.quota_limit > provider_record.quota_used or provider_record.quota_limit == -1,
                    restrict_models=provider_quota.restrict_models
                )

            quota_configurations.append(quota_configuration)

        # 若无配额配置，则返回禁用状态的系统配置
        if len(quota_configurations) == 0:
            return SystemConfiguration(
                enabled=False
            )

        # 选择当前使用的配额类型
        current_quota_type = self._choice_current_using_quota_type(quota_configurations)

        # 获取当前使用的凭证
        current_using_credentials = provider_hosting_configuration.credentials
        if current_quota_type == ProviderQuotaType.FREE:
            provider_record = quota_type_to_provider_records_dict.get(current_quota_type)

            if provider_record:
                provider_credentials_cache = ProviderCredentialsCache(
                    tenant_id=tenant_id,
                    identity_id=provider_record.id,
                    cache_type=ProviderCredentialsCacheType.PROVIDER
                )

                # 尝试从缓存获取提供者凭证
                cached_provider_credentials = provider_credentials_cache.get()

                if not cached_provider_credentials:
                    try:
                        provider_credentials = json.loads(provider_record.encrypted_config)
                    except JSONDecodeError:
                        provider_credentials = {}

                    # 解密凭证中的密文变量
                    provider_credential_secret_variables = self._extract_secret_variables(
                        provider_entity.provider_credential_schema.credential_form_schemas
                        if provider_entity.provider_credential_schema else []
                    )

                    # 获取解密RSA密钥和密码，用于解密凭证
                    if self.decoding_rsa_key is None or self.decoding_cipher_rsa is None:
                        self.decoding_rsa_key, self.decoding_cipher_rsa = encrypter.get_decrypt_decoding(tenant_id)

                    for variable in provider_credential_secret_variables:
                        if variable in provider_credentials:
                            try:
                                provider_credentials[variable] = encrypter.decrypt_token_with_decoding(
                                    provider_credentials.get(variable),
                                    self.decoding_rsa_key,
                                    self.decoding_cipher_rsa
                                )
                            except ValueError:
                                pass

                    current_using_credentials = provider_credentials

                    # 缓存提供者凭证
                    provider_credentials_cache.set(
                        credentials=current_using_credentials
                    )
                else:
                    current_using_credentials = cached_provider_credentials
            else:
                current_using_credentials = {}
                quota_configurations = []

        # 构建并返回系统配置对象
        return SystemConfiguration(
            enabled=True,
            current_quota_type=current_quota_type,
            quota_configurations=quota_configurations,
            credentials=current_using_credentials
        )

    def _choice_current_using_quota_type(self, quota_configurations: list[QuotaConfiguration]) -> ProviderQuotaType:
        """
        选择当前使用的配额类型，优先级顺序为：付费配额 > 提供商免费配额 > 试用配额。
        如果根据排序仍有对应配额类型可用，

        :param quota_configurations: 配额配置列表，每个配置包含配额类型和相关信息
        :return: 返回选中的配额类型
        """
        # 将配额配置列表转换为字典，以配额类型为键
        quota_type_to_quota_configuration_dict = {
            quota_configuration.quota_type: quota_configuration
            for quota_configuration in quota_configurations
        }

        last_quota_configuration = None
        # 按照优先级顺序检查每种配额类型的可用性
        for quota_type in [ProviderQuotaType.PAID, ProviderQuotaType.FREE, ProviderQuotaType.TRIAL]:
            if quota_type in quota_type_to_quota_configuration_dict:
                last_quota_configuration = quota_type_to_quota_configuration_dict[quota_type]
                # 如果配额配置有效，返回当前配额类型
                if last_quota_configuration.is_valid:
                    return quota_type

        # 如果最后有一个有效的配额配置，返回其配额类型
        if last_quota_configuration:
            return last_quota_configuration.quota_type

        # 如果没有可用的配额类型，抛出异常
        raise ValueError('No quota type available')

    def _extract_secret_variables(self, credential_form_schemas: list[CredentialFormSchema]) -> list[str]:
        """
        提取保密输入表单变量。

        从给定的凭据表单模式列表中，找出保密输入类型的变量。

        :param credential_form_schemas: 一个CredentialFormSchema对象列表，每个对象代表一个表单模式，
                                        可能包含保密输入字段。
        :return: 一个字符串列表，包含所有保密输入表单变量。
        """
        # 初始化一个空列表，用于存储保密输入表单变量。
        secret_input_form_variables = []

        # 遍历凭据表单模式列表。
        for credential_form_schema in credential_form_schemas:
            # 如果表单模式类型为SECRET_INPUT，将其变量添加到列表中。
            if credential_form_schema.type == FormType.SECRET_INPUT:
                secret_input_form_variables.append(credential_form_schema.variable)

        # 返回保密输入表单变量列表。
        return secret_input_form_variables

    def _to_model_settings(self, provider_entity: ProviderEntity,
                           provider_model_settings: Optional[list[ProviderModelSetting]] = None,
                           load_balancing_model_configs: Optional[list[LoadBalancingModelConfig]] = None) \
            -> list[ModelSettings]:
        """
        Convert to model settings.
        :param provider_entity: provider entity
        :param provider_model_settings: provider model settings include enabled, load balancing enabled
        :param load_balancing_model_configs: load balancing model configs
        :return:
        """
        # Get provider model credential secret variables
        model_credential_secret_variables = self._extract_secret_variables(
            provider_entity.model_credential_schema.credential_form_schemas
            if provider_entity.model_credential_schema else []
        )

        model_settings = []
        if not provider_model_settings:
            return model_settings

        for provider_model_setting in provider_model_settings:
            load_balancing_configs = []
            if provider_model_setting.load_balancing_enabled and load_balancing_model_configs:
                for load_balancing_model_config in load_balancing_model_configs:
                    if (load_balancing_model_config.model_name == provider_model_setting.model_name
                            and load_balancing_model_config.model_type == provider_model_setting.model_type):
                        if not load_balancing_model_config.enabled:
                            continue

                        if not load_balancing_model_config.encrypted_config:
                            if load_balancing_model_config.name == "__inherit__":
                                load_balancing_configs.append(ModelLoadBalancingConfiguration(
                                    id=load_balancing_model_config.id,
                                    name=load_balancing_model_config.name,
                                    credentials={}
                                ))
                            continue

                        provider_model_credentials_cache = ProviderCredentialsCache(
                            tenant_id=load_balancing_model_config.tenant_id,
                            identity_id=load_balancing_model_config.id,
                            cache_type=ProviderCredentialsCacheType.LOAD_BALANCING_MODEL
                        )

                        # Get cached provider model credentials
                        cached_provider_model_credentials = provider_model_credentials_cache.get()

                        if not cached_provider_model_credentials:
                            try:
                                provider_model_credentials = json.loads(load_balancing_model_config.encrypted_config)
                            except JSONDecodeError:
                                continue

                            # Get decoding rsa key and cipher for decrypting credentials
                            if self.decoding_rsa_key is None or self.decoding_cipher_rsa is None:
                                self.decoding_rsa_key, self.decoding_cipher_rsa = encrypter.get_decrypt_decoding(
                                    load_balancing_model_config.tenant_id)

                            for variable in model_credential_secret_variables:
                                if variable in provider_model_credentials:
                                    try:
                                        provider_model_credentials[variable] = encrypter.decrypt_token_with_decoding(
                                            provider_model_credentials.get(variable),
                                            self.decoding_rsa_key,
                                            self.decoding_cipher_rsa
                                        )
                                    except ValueError:
                                        pass

                            # cache provider model credentials
                            provider_model_credentials_cache.set(
                                credentials=provider_model_credentials
                            )
                        else:
                            provider_model_credentials = cached_provider_model_credentials

                        load_balancing_configs.append(ModelLoadBalancingConfiguration(
                            id=load_balancing_model_config.id,
                            name=load_balancing_model_config.name,
                            credentials=provider_model_credentials
                        ))

            model_settings.append(
                ModelSettings(
                    model=provider_model_setting.model_name,
                    model_type=ModelType.value_of(provider_model_setting.model_type),
                    enabled=provider_model_setting.enabled,
                    load_balancing_configs=load_balancing_configs if len(load_balancing_configs) > 1 else []
                )
            )

        return model_settings
