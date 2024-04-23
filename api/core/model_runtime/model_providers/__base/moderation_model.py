import time
from abc import abstractmethod
from typing import Optional

from core.model_runtime.entities.model_entities import ModelType
from core.model_runtime.model_providers.__base.ai_model import AIModel


class ModerationModel(AIModel):
    """
    中介模型类，用于提供中介服务的模型。
    """
    model_type: ModelType = ModelType.MODERATION  # 指定模型类型为中介模型

    def invoke(self, model: str, credentials: dict,
               text: str, user: Optional[str] = None) \
            -> bool:
        """
        调用中介模型进行文本审核。

        :param model: 模型名称。
        :param credentials: 模型认证信息。
        :param text: 需要审核的文本。
        :param user: 用户的唯一标识符，可选。
        :return: 如果文本被判断为不安全，返回true；否则返回false。
        """
        self.started_at = time.perf_counter()  # 记录调用开始时间

        try:
            return self._invoke(model, credentials, text, user)  # 尝试调用具体实现方法
        except Exception as e:
            raise self._transform_invoke_error(e)  # 转换并抛出调用过程中的异常

    @abstractmethod
    def _invoke(self, model: str, credentials: dict,
                text: str, user: Optional[str] = None) \
            -> bool:
        """
        调用大型语言模型进行文本审核。

        :param model: 模型名称。
        :param credentials: 模型认证信息。
        :param text: 需要审核的文本。
        :param user: 用户的唯一标识符，可选。
        :return: 如果文本被判断为不安全，返回true；否则返回false。
        """
        raise NotImplementedError  # 该方法必须在子类中被实现
