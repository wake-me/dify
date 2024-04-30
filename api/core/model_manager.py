from collections.abc import Generator
from typing import IO, Optional, Union, cast

from core.entities.provider_configuration import ProviderModelBundle
from core.errors.error import ProviderTokenNotInitError
from core.model_runtime.callbacks.base_callback import Callback
from core.model_runtime.entities.llm_entities import LLMResult
from core.model_runtime.entities.message_entities import PromptMessage, PromptMessageTool
from core.model_runtime.entities.model_entities import ModelType
from core.model_runtime.entities.rerank_entities import RerankResult
from core.model_runtime.entities.text_embedding_entities import TextEmbeddingResult
from core.model_runtime.model_providers.__base.large_language_model import LargeLanguageModel
from core.model_runtime.model_providers.__base.moderation_model import ModerationModel
from core.model_runtime.model_providers.__base.rerank_model import RerankModel
from core.model_runtime.model_providers.__base.speech2text_model import Speech2TextModel
from core.model_runtime.model_providers.__base.text_embedding_model import TextEmbeddingModel
from core.model_runtime.model_providers.__base.tts_model import TTSModel
from core.provider_manager import ProviderManager


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

    def _fetch_credentials_from_bundle(self, provider_model_bundle: ProviderModelBundle, model: str) -> dict:
        """
        从提供者模型捆绑包中获取凭证信息。
        
        :param provider_model_bundle: 提供者模型捆绑包，包含模型的配置和类型信息。
        :param model: 模型名称，指定需要获取凭证的模型。
        :return: 返回一个字典，包含模型所需的凭证信息。
        """
        # 尝试从提供的模型捆绑包中获取当前模型的凭证信息
        credentials = provider_model_bundle.configuration.get_current_credentials(
            model_type=provider_model_bundle.model_type_instance.model_type,
            model=model
        )

        # 如果未能获取到凭证信息，则抛出异常
        if credentials is None:
            raise ProviderTokenNotInitError(f"Model {model} credentials is not initialized.")

        return credentials

    def invoke_llm(self, prompt_messages: list[PromptMessage], model_parameters: Optional[dict] = None,
                tools: Optional[list[PromptMessageTool]] = None, stop: Optional[list[str]] = None,
                stream: bool = True, user: Optional[str] = None, callbacks: list[Callback] = None) \
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
        # 调用模型实例的invoke方法，传入各种参数进行模型的调用
        return self.model_type_instance.invoke(
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
        # 调用模型为给定文本生成嵌入
        return self.model_type_instance.invoke(
            model=self.model,
            credentials=self.credentials,
            texts=texts,
            user=user
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
        # 调用模型实例的invoke方法进行重排计算
        return self.model_type_instance.invoke(
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
        return self.model_type_instance.invoke(
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
        # 调用模型实例的invoke方法，进行语音转文本
        return self.model_type_instance.invoke(
            model=self.model,
            credentials=self.credentials,
            file=file,
            user=user
        )

    def invoke_tts(self, content_text: str, tenant_id: str, voice: str, streaming: bool, user: Optional[str] = None) \
            -> str:
        """
        调用大型语言TTS（文本转语音）模型

        :param content_text: 需要翻译的文本内容
        :param tenant_id: 用户租户ID
        :param user: 唯一用户ID，可选
        :param voice: 模型音色
        :param streaming: 输出是否为流式
        :return: 给定音频文件的文本
        """
        # 检查模型类型实例是否为TTSModel类型
        if not isinstance(self.model_type_instance, TTSModel):
            raise Exception("Model type instance is not TTSModel")

        # 断言模型类型实例为TTSModel类型，用于后续函数调用
        self.model_type_instance = cast(TTSModel, self.model_type_instance)
        # 调用TTS模型，传入各种参数执行文本转语音
        return self.model_type_instance.invoke(
            model=self.model,
            credentials=self.credentials,
            content_text=content_text,
            user=user,
            tenant_id=tenant_id,
            voice=voice,
            streaming=streaming
        )

    def get_tts_voices(self, language: str) -> list:
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
        
        # 获取提供者模型包
        provider_model_bundle = self._provider_manager.get_provider_model_bundle(
            tenant_id=tenant_id,
            provider=provider,
            model_type=model_type
        )

        # 根据提供者模型包和模型名称创建模型实例
        return ModelInstance(provider_model_bundle, model)

    def get_default_model_instance(self, tenant_id: str, model_type: ModelType) -> ModelInstance:
        """
        获取默认模型实例。
        :param tenant_id: 租户ID。
        :param model_type: 模型类型。
        :return: 返回默认的模型实例。
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