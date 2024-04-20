from typing import cast

from core.app.app_config.entities import EasyUIBasedAppConfig
from core.app.entities.app_invoke_entities import ModelConfigWithCredentialsEntity
from core.entities.model_entities import ModelStatus
from core.errors.error import ModelCurrentlyNotSupportError, ProviderTokenNotInitError, QuotaExceededError
from core.model_runtime.entities.model_entities import ModelType
from core.model_runtime.model_providers.__base.large_language_model import LargeLanguageModel
from core.provider_manager import ProviderManager


class ModelConfigConverter:
    @classmethod
    def convert(cls, app_config: EasyUIBasedAppConfig,
                skip_check: bool = False) \
            -> ModelConfigWithCredentialsEntity:
        """
        将应用模型配置字典转换为实体。
        :param app_config: 应用配置
        :param skip_check: 是否跳过检查
        :raises ProviderTokenNotInitError: 提供者令牌未初始化错误
        :return: 应用编排配置实体
        """
        # 获取应用的模型配置
        model_config = app_config.model

        # 初始化提供者管理器，并获取对应模型的提供者模型捆绑包
        provider_manager = ProviderManager()
        provider_model_bundle = provider_manager.get_provider_model_bundle(
            tenant_id=app_config.tenant_id,
            provider=model_config.provider,
            model_type=ModelType.LLM
        )

        # 解析提供者和模型名称
        provider_name = provider_model_bundle.configuration.provider.provider
        model_name = model_config.model

        # 获取模型类型实例，并断言为大型语言模型类型
        model_type_instance = provider_model_bundle.model_type_instance
        model_type_instance = cast(LargeLanguageModel, model_type_instance)

        # 检查模型凭证
        model_credentials = provider_model_bundle.configuration.get_current_credentials(
            model_type=ModelType.LLM,
            model=model_config.model
        )

        # 如果模型凭证未初始化且未跳过检查，则抛出异常
        if model_credentials is None:
            if not skip_check:
                raise ProviderTokenNotInitError(f"Model {model_name} credentials is not initialized.")
            else:
                model_credentials = {}

        # 如果未跳过检查，则进一步检查模型配置和状态
        if not skip_check:
            # 检查模型是否存在
            provider_model = provider_model_bundle.configuration.get_provider_model(
                model=model_config.model,
                model_type=ModelType.LLM
            )

            if provider_model is None:
                model_name = model_config.model
                raise ValueError(f"Model {model_name} not exist.")

            # 根据模型状态抛出相应的异常
            if provider_model.status == ModelStatus.NO_CONFIGURE:
                raise ProviderTokenNotInitError(f"Model {model_name} credentials is not initialized.")
            elif provider_model.status == ModelStatus.NO_PERMISSION:
                raise ModelCurrentlyNotSupportError(f"Dify Hosted OpenAI {model_name} currently not support.")
            elif provider_model.status == ModelStatus.QUOTA_EXCEEDED:
                raise QuotaExceededError(f"Model provider {provider_name} quota exceeded.")

        # 处理模型配置，如完成参数中的'stop'项
        completion_params = model_config.parameters
        stop = []
        if 'stop' in completion_params:
            stop = completion_params['stop']
            del completion_params['stop']

        # 获取模型模式
        model_mode = model_config.mode
        if not model_mode:
            # 如果模型模式未指定，则从模型类型实例中获取
            mode_enum = model_type_instance.get_model_mode(
                model=model_config.model,
                credentials=model_credentials
            )

            model_mode = mode_enum.value

        # 获取模型的架构
        model_schema = model_type_instance.get_model_schema(
            model_config.model,
            model_credentials
        )

        # 如果未跳过检查且模型架构不存在，则抛出异常
        if not skip_check and not model_schema:
            raise ValueError(f"Model {model_name} not exist.")

        # 构造并返回模型配置实体
        return ModelConfigWithCredentialsEntity(
            provider=model_config.provider,
            model=model_config.model,
            model_schema=model_schema,
            mode=model_mode,
            provider_model_bundle=provider_model_bundle,
            credentials=model_credentials,
            parameters=completion_params,
            stop=stop,
        )
