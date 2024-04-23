import time
from abc import abstractmethod
from typing import Optional

from core.model_runtime.entities.model_entities import ModelPropertyKey, ModelType
from core.model_runtime.entities.text_embedding_entities import TextEmbeddingResult
from core.model_runtime.model_providers.__base.ai_model import AIModel


class TextEmbeddingModel(AIModel):
    """
    文本嵌入模型的模型类。
    """
    model_type: ModelType = ModelType.TEXT_EMBEDDING

    def invoke(self, model: str, credentials: dict,
               texts: list[str], user: Optional[str] = None) \
            -> TextEmbeddingResult:
        """
        调用大型语言模型。

        :param model: 模型名称。
        :param credentials: 模型凭证。
        :param texts: 需要嵌入文本的列表。
        :param user: 唯一的用户ID，可选。
        :return: 嵌入结果。
        """
        self.started_at = time.perf_counter()

        try:
            return self._invoke(model, credentials, texts, user)
        except Exception as e:
            # 转换并抛出调用过程中的错误
            raise self._transform_invoke_error(e)

    @abstractmethod
    def _invoke(self, model: str, credentials: dict,
                texts: list[str], user: Optional[str] = None) \
            -> TextEmbeddingResult:
        """
        调用大型语言模型的抽象方法。

        :param model: 模型名称。
        :param credentials: 模型凭证。
        :param texts: 需要嵌入文本的列表。
        :param user: 唯一的用户ID，可选。
        :return: 嵌入结果。
        """
        raise NotImplementedError

    @abstractmethod
    def get_num_tokens(self, model: str, credentials: dict, texts: list[str]) -> int:
        """
        获取给定提示信息的令牌数量。

        :param model: 模型名称。
        :param credentials: 模型凭证。
        :param texts: 需要嵌入文本的列表。
        :return: 令牌数量。
        """
        raise NotImplementedError

    def _get_context_size(self, model: str, credentials: dict) -> int:
        """
        获取给定嵌入模型的上下文大小。

        :param model: 模型名称。
        :param credentials: 模型凭证。
        :return: 上下文大小。
        """
        model_schema = self.get_model_schema(model, credentials)

        # 从模型架构中获取上下文大小，默认为1000
        if model_schema and ModelPropertyKey.CONTEXT_SIZE in model_schema.model_properties:
            return model_schema.model_properties[ModelPropertyKey.CONTEXT_SIZE]

        return 1000

    def _get_max_chunks(self, model: str, credentials: dict) -> int:
        """
        获取给定嵌入模型的最大块数。

        :param model: 模型名称。
        :param credentials: 模型凭证。
        :return: 最大块数。
        """
        model_schema = self.get_model_schema(model, credentials)

        # 从模型架构中获取最大块数，默认为1
        if model_schema and ModelPropertyKey.MAX_CHUNKS in model_schema.model_properties:
            return model_schema.model_properties[ModelPropertyKey.MAX_CHUNKS]

        return 1