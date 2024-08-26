import logging
import os
from collections.abc import Callable, Generator
from typing import IO, Optional, Union, cast

from core.entities.provider_configuration import ProviderConfiguration, ProviderModelBundle
from core.entities.provider_entities import ModelLoadBalancingConfiguration
from core.errors.error import ProviderTokenNotInitError
from core.model_runtime.callbacks.base_callback import Callback
from core.model_runtime.entities.llm_entities import LLMResult
from core.model_runtime.entities.message_entities import PromptMessage, PromptMessageTool
from core.model_runtime.entities.model_entities import ModelType
from core.model_runtime.entities.rerank_entities import RerankResult
from core.model_runtime.entities.text_embedding_entities import TextEmbeddingResult
from core.model_runtime.errors.invoke import InvokeAuthorizationError, InvokeConnectionError, InvokeRateLimitError
from core.model_runtime.model_providers.__base.large_language_model import LargeLanguageModel
from core.model_runtime.model_providers.__base.moderation_model import ModerationModel
from core.model_runtime.model_providers.__base.rerank_model import RerankModel
from core.model_runtime.model_providers.__base.speech2text_model import Speech2TextModel
from core.model_runtime.model_providers.__base.text_embedding_model import TextEmbeddingModel
from core.model_runtime.model_providers.__base.tts_model import TTSModel
from core.provider_manager import ProviderManager
from extensions.ext_redis import redis_client
from models.provider import ProviderType

logger = logging.getLogger(__name__)


class ModelInstance:
    """
    这是一个模型实例类，用于封装和管理特定模型的实例。
    """

    def __init__(self, provider_model_bundle: ProviderModelBundle, model: str) -> None:
        """
        初始化一个模型实例。

        :param provider_model_bundle: 提供者模型包，包含模型的配置和实例信息。
        :param model: 模型标识符，用于指定具体的模型。
        """
        # 将提供者模型包和模型标识符保存为实例变量
        self.provider_model_bundle = provider_model_bundle
        self.model = model
        # 从提供者模型包中提取提供商信息
        self.provider = provider_model_bundle.configuration.provider.provider
        # 从提供者模型包和模型中获取凭证信息
        self.credentials = self._fetch_credentials_from_bundle(provider_model_bundle, model)
        # 获取提供者模型包中的模型类型实例
        self.model_type_instance = self.provider_model_bundle.model_type_instance
        self.load_balancing_manager = self._get_load_balancing_manager(
            configuration=provider_model_bundle.configuration,
            model_type=provider_model_bundle.model_type_instance.model_type,
            model=model,
            credentials=self.credentials
        )

    def _fetch_credentials_from_bundle(self, provider_model_bundle: ProviderModelBundle, model: str) -> dict:
        """
        从提供者模型捆绑包中获取凭证信息。
        
        :param provider_model_bundle: 提供者模型捆绑包，包含模型的配置和类型信息。
        :param model: 模型名称，指定需要获取凭证的模型。
        :return: 返回一个字典，包含模型所需的凭证信息。
        """
        configuration = provider_model_bundle.configuration
        model_type = provider_model_bundle.model_type_instance.model_type
        credentials = configuration.get_current_credentials(
            model_type=model_type,
            model=model
        )

        # 如果未能获取到凭证信息，则抛出异常
        if credentials is None:
            raise ProviderTokenNotInitError(f"Model {model} credentials is not initialized.")

        return credentials

    def _get_load_balancing_manager(self, configuration: ProviderConfiguration,
                                    model_type: ModelType,
                                    model: str,
                                    credentials: dict) -> Optional["LBModelManager"]:
        """
        Get load balancing model credentials
        :param configuration: provider configuration
        :param model_type: model type
        :param model: model name
        :param credentials: model credentials
        :return:
        """
        if configuration.model_settings and configuration.using_provider_type == ProviderType.CUSTOM:
            current_model_setting = None
            # check if model is disabled by admin
            for model_setting in configuration.model_settings:
                if (model_setting.model_type == model_type
                        and model_setting.model == model):
                    current_model_setting = model_setting
                    break

            # check if load balancing is enabled
            if current_model_setting and current_model_setting.load_balancing_configs:
                # use load balancing proxy to choose credentials
                lb_model_manager = LBModelManager(
                    tenant_id=configuration.tenant_id,
                    provider=configuration.provider.provider,
                    model_type=model_type,
                    model=model,
                    load_balancing_configs=current_model_setting.load_balancing_configs,
                    managed_credentials=credentials if configuration.custom_configuration.provider else None
                )

                return lb_model_manager

        return None

    def invoke_llm(self, prompt_messages: list[PromptMessage], model_parameters: Optional[dict] = None,
                   tools: Optional[list[PromptMessageTool]] = None, stop: Optional[list[str]] = None,
                   stream: bool = True, user: Optional[str] = None, callbacks: Optional[list[Callback]] = None) \
            -> Union[LLMResult, Generator]:
        """
        调用大型语言模型

        :param prompt_messages: 提示信息列表
        :param model_parameters: 模型参数，可选
        :param tools: 用于工具调用的工具列表，可选
        :param stop: 停止词列表，可选
        :param stream: 是否流式响应，默认为True
        :param user: 唯一的用户ID，可选
        :param callbacks: 回调列表，可选
        :return: 全部响应或流式响应块生成器结果
        """
        # 检查模型类型实例是否为LargeLanguageModel
        if not isinstance(self.model_type_instance, LargeLanguageModel):
            raise Exception("Model type instance is not LargeLanguageModel")

        # 断言模型类型实例为LargeLanguageModel
        self.model_type_instance = cast(LargeLanguageModel, self.model_type_instance)
        return self._round_robin_invoke(
            function=self.model_type_instance.invoke,
            model=self.model,
            credentials=self.credentials,
            prompt_messages=prompt_messages,
            model_parameters=model_parameters,
            tools=tools,
            stop=stop,
            stream=stream,
            user=user,
            callbacks=callbacks
        )

    def get_llm_num_tokens(self, prompt_messages: list[PromptMessage],
                           tools: Optional[list[PromptMessageTool]] = None) -> int:
        """
        Get number of tokens for llm

        :param prompt_messages: prompt messages
        :param tools: tools for tool calling
        :return:
        """
        if not isinstance(self.model_type_instance, LargeLanguageModel):
            raise Exception("Model type instance is not LargeLanguageModel")

        self.model_type_instance = cast(LargeLanguageModel, self.model_type_instance)
        return self._round_robin_invoke(
            function=self.model_type_instance.get_num_tokens,
            model=self.model,
            credentials=self.credentials,
            prompt_messages=prompt_messages,
            tools=tools
        )

    def invoke_text_embedding(self, texts: list[str], user: Optional[str] = None) \
            -> TextEmbeddingResult:
        """
        调用大型语言模型以生成文本嵌入。

        此函数接收一个文本列表及一个可选的用户ID，然后使用指定的文本嵌入模型为给定文本生成嵌入。

        :param texts: 一系列字符串，每个字符串代表待嵌入的文本。
        :param user: 一个可选的字符串，表示唯一的用户ID。可用于跟踪或个性化需求。
        :return: 返回一个TextEmbeddingResult实例，其中包含了输入文本的嵌入结果。
        """
        # 验证模型类型实例是否为TextEmbeddingModel类型
        if not isinstance(self.model_type_instance, TextEmbeddingModel):
            raise Exception("Model type instance is not TextEmbeddingModel")

        # 将模型类型实例显式转换为TextEmbeddingModel，以确保安全访问
        self.model_type_instance = cast(TextEmbeddingModel, self.model_type_instance)
        return self._round_robin_invoke(
            function=self.model_type_instance.invoke,
            model=self.model,
            credentials=self.credentials,
            texts=texts,
            user=user
        )

    def get_text_embedding_num_tokens(self, texts: list[str]) -> int:
        """
        Get number of tokens for text embedding

        :param texts: texts to embed
        :return:
        """
        if not isinstance(self.model_type_instance, TextEmbeddingModel):
            raise Exception("Model type instance is not TextEmbeddingModel")

        self.model_type_instance = cast(TextEmbeddingModel, self.model_type_instance)
        return self._round_robin_invoke(
            function=self.model_type_instance.get_num_tokens,
            model=self.model,
            credentials=self.credentials,
            texts=texts
        )

    def invoke_rerank(self, query: str, docs: list[str], score_threshold: Optional[float] = None,
                      top_n: Optional[int] = None,
                      user: Optional[str] = None) \
            -> RerankResult:
        """
        调用重排模型进行重排。

        :param query: 搜索查询字符串
        :param docs: 需要进行重排的文档列表
        :param score_threshold: 分数阈值，用于筛选文档
        :param top_n: 重排后返回的文档数量
        :param user: 唯一的用户ID，可用于个性化重排
        :return: 重排结果对象
        """
        # 检查模型类型实例是否为RerankModel类型
        if not isinstance(self.model_type_instance, RerankModel):
            raise Exception("Model type instance is not RerankModel")

        # 断言模型类型实例为RerankModel类型，以满足类型检查
        self.model_type_instance = cast(RerankModel, self.model_type_instance)
        return self._round_robin_invoke(
            function=self.model_type_instance.invoke,
            model=self.model,
            credentials=self.credentials,
            query=query,
            docs=docs,
            score_threshold=score_threshold,
            top_n=top_n,
            user=user
        )

    def invoke_moderation(self, text: str, user: Optional[str] = None) \
            -> bool:
        """
        Invoke moderation model

        :param text: text to moderate
        :param user: unique user id
        :return: false if text is safe, true otherwise
        """
        if not isinstance(self.model_type_instance, ModerationModel):
            raise Exception("Model type instance is not ModerationModel")

        self.model_type_instance = cast(ModerationModel, self.model_type_instance)
        return self._round_robin_invoke(
            function=self.model_type_instance.invoke,
            model=self.model,
            credentials=self.credentials,
            text=text,
            user=user
        )

    def invoke_speech2text(self, file: IO[bytes], user: Optional[str] = None) \
            -> str:
        """
        调用大型语言模型进行语音转文本。

        :param file: 音频文件，预期为一个字节流。
        :param user: 唯一的用户ID，可选参数。
        :return: 给定音频文件的文本表示。
        """
        # 检查模型类型实例是否为Speech2TextModel
        if not isinstance(self.model_type_instance, Speech2TextModel):
            raise Exception("Model type instance is not Speech2TextModel")

        # 断言模型类型实例为Speech2TextModel，以便后续调用
        self.model_type_instance = cast(Speech2TextModel, self.model_type_instance)
        return self._round_robin_invoke(
            function=self.model_type_instance.invoke,
            model=self.model,
            credentials=self.credentials,
            file=file,
            user=user
        )

    def invoke_tts(self, content_text: str, tenant_id: str, voice: str, user: Optional[str] = None) \
            -> str:
        """
        调用大型语言TTS（文本转语音）模型

        :param content_text: text content to be translated
        :param tenant_id: user tenant id
        :param voice: model timbre
        :param user: unique user id
        :return: text for given audio file
        """
        if not isinstance(self.model_type_instance, TTSModel):
            raise Exception("Model type instance is not TTSModel")

        # 断言模型类型实例为TTSModel类型，用于后续函数调用
        self.model_type_instance = cast(TTSModel, self.model_type_instance)
        return self._round_robin_invoke(
            function=self.model_type_instance.invoke,
            model=self.model,
            credentials=self.credentials,
            content_text=content_text,
            user=user,
            tenant_id=tenant_id,
            voice=voice
        )

    def _round_robin_invoke(self, function: Callable, *args, **kwargs):
        """
        Round-robin invoke
        :param function: function to invoke
        :param args: function args
        :param kwargs: function kwargs
        :return:
        """
        if not self.load_balancing_manager:
            return function(*args, **kwargs)

        last_exception = None
        while True:
            lb_config = self.load_balancing_manager.fetch_next()
            if not lb_config:
                if not last_exception:
                    raise ProviderTokenNotInitError("Model credentials is not initialized.")
                else:
                    raise last_exception

            try:
                if 'credentials' in kwargs:
                    del kwargs['credentials']
                return function(*args, **kwargs, credentials=lb_config.credentials)
            except InvokeRateLimitError as e:
                # expire in 60 seconds
                self.load_balancing_manager.cooldown(lb_config, expire=60)
                last_exception = e
                continue
            except (InvokeAuthorizationError, InvokeConnectionError) as e:
                # expire in 10 seconds
                self.load_balancing_manager.cooldown(lb_config, expire=10)
                last_exception = e
                continue
            except Exception as e:
                raise e

    def get_tts_voices(self, language: Optional[str] = None) -> list:
        """
        调用大型语言TTS模型声音

        :param language: TTS语言
        :return: TTS模型声音列表
        """
        # 检查模型类型实例是否为TTSModel类型
        if not isinstance(self.model_type_instance, TTSModel):
            raise Exception("Model type instance is not TTSModel")

        # 断言模型类型实例为TTSModel类型，以便后续调用
        self.model_type_instance = cast(TTSModel, self.model_type_instance)
        # 获取指定语言的TTS模型声音列表
        return self.model_type_instance.get_tts_model_voices(
            model=self.model,
            credentials=self.credentials,
            language=language
        )


class ModelManager:
    def __init__(self) -> None:
        # 初始化ProviderManager
        self._provider_manager = ProviderManager()

    def get_model_instance(self, tenant_id: str, provider: str, model_type: ModelType, model: str) -> ModelInstance:
        """
        获取模型实例。
        :param tenant_id: 租户ID。
        :param provider: 提供者名称。
        :param model_type: 模型类型。
        :param model: 模型名称。
        :return: 返回指定的模型实例。
        """
        # 如果提供者为空，则获取默认模型实例
        if not provider:
            return self.get_default_model_instance(tenant_id, model_type)

        provider_model_bundle = self._provider_manager.get_provider_model_bundle(
            tenant_id=tenant_id,
            provider=provider,
            model_type=model_type
        )

        # 根据提供者模型包和模型名称创建模型实例
        return ModelInstance(provider_model_bundle, model)

    def get_default_provider_model_name(self, tenant_id: str, model_type: ModelType) -> tuple[str, str]:
        """
        Return first provider and the first model in the provider
        :param tenant_id: tenant id
        :param model_type: model type
        :return: provider name, model name
        """
        return self._provider_manager.get_first_provider_first_model(tenant_id, model_type)

    def get_default_model_instance(self, tenant_id: str, model_type: ModelType) -> ModelInstance:
        """
        Get default model instance
        :param tenant_id: tenant id
        :param model_type: model type
        :return:
        """
        # 获取默认模型实体
        default_model_entity = self._provider_manager.get_default_model(
            tenant_id=tenant_id,
            model_type=model_type
        )

        # 如果默认模型实体不存在，则抛出异常
        if not default_model_entity:
            raise ProviderTokenNotInitError(f"Default model not found for {model_type}")

        # 根据默认模型实体的信息获取模型实例
        return self.get_model_instance(
            tenant_id=tenant_id,
            provider=default_model_entity.provider.provider,
            model_type=model_type,
            model=default_model_entity.model
        )


class LBModelManager:
    def __init__(self, tenant_id: str,
                 provider: str,
                 model_type: ModelType,
                 model: str,
                 load_balancing_configs: list[ModelLoadBalancingConfiguration],
                 managed_credentials: Optional[dict] = None) -> None:
        """
        Load balancing model manager
        :param tenant_id: tenant_id
        :param provider: provider
        :param model_type: model_type
        :param model: model name
        :param load_balancing_configs: all load balancing configurations
        :param managed_credentials: credentials if load balancing configuration name is __inherit__
        """
        self._tenant_id = tenant_id
        self._provider = provider
        self._model_type = model_type
        self._model = model
        self._load_balancing_configs = load_balancing_configs

        for load_balancing_config in self._load_balancing_configs[:]:  # Iterate over a shallow copy of the list
            if load_balancing_config.name == "__inherit__":
                if not managed_credentials:
                    # remove __inherit__ if managed credentials is not provided
                    self._load_balancing_configs.remove(load_balancing_config)
                else:
                    load_balancing_config.credentials = managed_credentials

    def fetch_next(self) -> Optional[ModelLoadBalancingConfiguration]:
        """
        Get next model load balancing config
        Strategy: Round Robin
        :return:
        """
        cache_key = "model_lb_index:{}:{}:{}:{}".format(
            self._tenant_id,
            self._provider,
            self._model_type.value,
            self._model
        )

        cooldown_load_balancing_configs = []
        max_index = len(self._load_balancing_configs)

        while True:
            current_index = redis_client.incr(cache_key)
            current_index = cast(int, current_index)
            if current_index >= 10000000:
                current_index = 1
                redis_client.set(cache_key, current_index)

            redis_client.expire(cache_key, 3600)
            if current_index > max_index:
                current_index = current_index % max_index

            real_index = current_index - 1
            if real_index > max_index:
                real_index = 0

            config = self._load_balancing_configs[real_index]

            if self.in_cooldown(config):
                cooldown_load_balancing_configs.append(config)
                if len(cooldown_load_balancing_configs) >= len(self._load_balancing_configs):
                    # all configs are in cooldown
                    return None

                continue

            if bool(os.environ.get("DEBUG", 'False').lower() == 'true'):
                logger.info(f"Model LB\nid: {config.id}\nname:{config.name}\n"
                            f"tenant_id: {self._tenant_id}\nprovider: {self._provider}\n"
                            f"model_type: {self._model_type.value}\nmodel: {self._model}")

            return config

        return None

    def cooldown(self, config: ModelLoadBalancingConfiguration, expire: int = 60) -> None:
        """
        Cooldown model load balancing config
        :param config: model load balancing config
        :param expire: cooldown time
        :return:
        """
        cooldown_cache_key = "model_lb_index:cooldown:{}:{}:{}:{}:{}".format(
            self._tenant_id,
            self._provider,
            self._model_type.value,
            self._model,
            config.id
        )

        redis_client.setex(cooldown_cache_key, expire, 'true')

    def in_cooldown(self, config: ModelLoadBalancingConfiguration) -> bool:
        """
        Check if model load balancing config is in cooldown
        :param config: model load balancing config
        :return:
        """
        cooldown_cache_key = "model_lb_index:cooldown:{}:{}:{}:{}:{}".format(
            self._tenant_id,
            self._provider,
            self._model_type.value,
            self._model,
            config.id
        )

        res = redis_client.exists(cooldown_cache_key)
        res = cast(bool, res)
        return res

    @classmethod
    def get_config_in_cooldown_and_ttl(cls, tenant_id: str,
                                       provider: str,
                                       model_type: ModelType,
                                       model: str,
                                       config_id: str) -> tuple[bool, int]:
        """
        Get model load balancing config is in cooldown and ttl
        :param tenant_id: workspace id
        :param provider: provider name
        :param model_type: model type
        :param model: model name
        :param config_id: model load balancing config id
        :return:
        """
        cooldown_cache_key = "model_lb_index:cooldown:{}:{}:{}:{}:{}".format(
            tenant_id,
            provider,
            model_type.value,
            model,
            config_id
        )

        ttl = redis_client.ttl(cooldown_cache_key)
        if ttl == -2:
            return False, 0

        ttl = cast(int, ttl)
        return True, ttl
