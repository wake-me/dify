from abc import abstractmethod
from typing import IO, Optional

from pydantic import ConfigDict

from core.model_runtime.entities.model_entities import ModelType
from core.model_runtime.model_providers.__base.ai_model import AIModel


class Text2ImageModel(AIModel):
    """
    文本转图像模型的类。
    """

    model_type: ModelType = ModelType.TEXT2IMG

    # pydantic configs
    model_config = ConfigDict(protected_namespaces=())

    def invoke(self, model: str, credentials: dict, prompt: str, 
               model_parameters: dict, user: Optional[str] = None) \
            -> list[IO[bytes]]:
        """
        调用文本转图像模型进行图像生成。

        :param model: 模型名称。
        :param credentials: 模型认证信息。
        :param prompt: 图像生成的提示文本。
        :param model_parameters: 模型参数。
        :param user: 唯一的用户ID。

        :return: 返回一个包含图像字节的列表。
        """
        try:
            return self._invoke(model, credentials, prompt, model_parameters, user)
        except Exception as e:
            # 将内部调用异常转换为统一的模型调用错误
            raise self._transform_invoke_error(e)

    @abstractmethod
    def _invoke(self, model: str, credentials: dict, prompt: str, 
                model_parameters: dict, user: Optional[str] = None) \
            -> list[IO[bytes]]:
        """
        实现文本转图像模型的具体调用逻辑。

        :param model: 模型名称。
        :param credentials: 模型认证信息。
        :param prompt: 图像生成的提示文本。
        :param model_parameters: 模型参数。
        :param user: 唯一的用户ID。

        :return: 返回一个包含图像字节的列表。
        """
        raise NotImplementedError