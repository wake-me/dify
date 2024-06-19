import os
from abc import abstractmethod
from typing import IO, Optional

from pydantic import ConfigDict

from core.model_runtime.entities.model_entities import ModelType
from core.model_runtime.model_providers.__base.ai_model import AIModel


class Speech2TextModel(AIModel):
    """
    用于语音转文本模型的模型类。
    """

    model_type: ModelType = ModelType.SPEECH2TEXT  # 指定模型类型为语音转文本

    # pydantic configs
    model_config = ConfigDict(protected_namespaces=())

    def invoke(self, model: str, credentials: dict,
               file: IO[bytes], user: Optional[str] = None) \
            -> str:
        """
        调用大型语言模型进行语音转文本。

        :param model: 模型名称。
        :param credentials: 模型认证信息。
        :param file: 音频文件。
        :param user: 唯一的用户ID。
        :return: 给定音频文件对应的文本。
        """
        try:
            return self._invoke(model, credentials, file, user)
        except Exception as e:
            # 将内部调用异常转换为统一的错误处理
            raise self._transform_invoke_error(e)

    @abstractmethod
    def _invoke(self, model: str, credentials: dict,
                file: IO[bytes], user: Optional[str] = None) \
            -> str:
        """
        实现大型语言模型的调用逻辑。

        :param model: 模型名称。
        :param credentials: 模型认证信息。
        :param file: 音频文件。
        :param user: 唯一的用户ID。
        :return: 给定音频文件对应的文本。
        """
        raise NotImplementedError  # 要求子类必须实现此方法

    def _get_demo_file_path(self) -> str:
        """
        获取给定模型的演示文件路径。

        :return: 演示文件的路径。
        """
        # 获取当前文件所在目录
        current_dir = os.path.dirname(os.path.abspath(__file__))

        # 构造音频文件路径
        return os.path.join(current_dir, 'audio.mp3')