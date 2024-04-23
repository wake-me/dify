import time
from abc import abstractmethod
from typing import Optional

from core.model_runtime.entities.model_entities import ModelType
from core.model_runtime.entities.rerank_entities import RerankResult
from core.model_runtime.model_providers.__base.ai_model import AIModel


class RerankModel(AIModel):
    """
    重排模型的基类。
    """

    model_type: ModelType = ModelType.RERANK

    def invoke(self, model: str, credentials: dict,
               query: str, docs: list[str], score_threshold: Optional[float] = None, top_n: Optional[int] = None,
               user: Optional[str] = None) \
            -> RerankResult:
        """
        调用重排模型进行文档重排。

        :param model: 模型名称。
        :param credentials: 模型认证信息。
        :param query: 搜索查询字符串。
        :param docs: 需要进行重排的文档列表。
        :param score_threshold: 分数阈值，用于筛选文档。
        :param top_n: 选取排序后前n个文档。
        :param user: 唯一的用户ID。
        :return: 重排结果。
        """
        self.started_at = time.perf_counter()  # 记录开始时间

        try:
            return self._invoke(model, credentials, query, docs, score_threshold, top_n, user)
        except Exception as e:
            # 将捕获到的异常转换为统一的模型调用错误格式抛出
            raise self._transform_invoke_error(e)

    @abstractmethod
    def _invoke(self, model: str, credentials: dict,
                query: str, docs: list[str], score_threshold: Optional[float] = None, top_n: Optional[int] = None,
                user: Optional[str] = None) \
            -> RerankResult:
        """
        执行重排模型的具体逻辑。

        :param model: 模型名称。
        :param credentials: 模型认证信息。
        :param query: 搜索查询字符串。
        :param docs: 需要进行重排的文档列表。
        :param score_threshold: 分数阈值，用于筛选文档。
        :param top_n: 选取排序后前n个文档。
        :param user: 唯一的用户ID。
        :return: 重排结果。
        """
        raise NotImplementedError  # 该方法必须在子类中实现