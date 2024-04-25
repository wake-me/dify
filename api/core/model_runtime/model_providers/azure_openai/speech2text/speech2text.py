import copy
from typing import IO, Optional

from openai import AzureOpenAI

from core.model_runtime.entities.model_entities import AIModelEntity
from core.model_runtime.errors.validate import CredentialsValidateFailedError
from core.model_runtime.model_providers.__base.speech2text_model import Speech2TextModel
from core.model_runtime.model_providers.azure_openai._common import _CommonAzureOpenAI
from core.model_runtime.model_providers.azure_openai._constant import SPEECH2TEXT_BASE_MODELS, AzureBaseModel


class AzureOpenAISpeech2TextModel(_CommonAzureOpenAI, Speech2TextModel):
    """
    OpenAI语音转文本模型的模型类。
    """

    def _invoke(self, model: str, credentials: dict,
                file: IO[bytes], user: Optional[str] = None) \
            -> str:
        """
        调用语音转文本模型。

        :param model: 模型名称
        :param credentials: 模型凭证
        :param file: 音频文件
        :param user: 唯一用户ID，可选
        :return: 给定音频文件对应的文本
        """
        # 通过语音转文本接口调用模型
        return self._speech2text_invoke(model, credentials, file)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        验证模型凭证的有效性。

        :param model: 模型名称
        :param credentials: 模型凭证
        :return: 无返回值
        """
        # 尝试使用提供的模型和凭证进行语音转文本的调用以验证凭证有效性
        try:
            # 获取示例音频文件路径
            audio_file_path = self._get_demo_file_path()

            # 打开音频文件并使用模型进行识别，以验证凭证
            with open(audio_file_path, 'rb') as audio_file:
                self._speech2text_invoke(model, credentials, audio_file)
        except Exception as ex:
            # 如果调用失败，抛出凭证验证失败的异常
            raise CredentialsValidateFailedError(str(ex))
    def _speech2text_invoke(self, model: str, credentials: dict, file: IO[bytes]) -> str:
        """
        调用语音转文本模型

        :param model: 模型名称
        :param credentials: 模型认证信息
        :param file: 音频文件
        :return: 给定音频文件的文本
        """
        # 将认证信息转换为模型实例的kwargs参数
        credentials_kwargs = self._to_credential_kwargs(credentials)

        # 初始化模型客户端
        client = AzureOpenAI(**credentials_kwargs)

        # 发起音频转文本的请求
        response = client.audio.transcriptions.create(model=model, file=file)

        # 返回转换后的文本
        return response.text

    def get_customizable_model_schema(self, model: str, credentials: dict) -> Optional[AIModelEntity]:
        """
        获取可定制模型的架构。

        参数:
        model (str): 模型名称。
        credentials (dict): 凭证信息，需要包含基础模型名称。

        返回:
        Optional[AIModelEntity]: 如果找到对应模型，返回 AIModelEntity 实例；否则返回 None。
        """
        # 根据提供的凭证信息获取 AI 模型实体
        ai_model_entity = self._get_ai_model_entity(credentials['base_model_name'], model)
        return ai_model_entity.entity


    @staticmethod
    def _get_ai_model_entity(base_model_name: str, model: str) -> AzureBaseModel:
        """
        根据基础模型名称和模型名称获取AI模型实体。
        
        参数:
        - base_model_name: str，基础模型的名称。
        - model: str，模型的名称。
        
        返回值:
        - AzureBaseModel，如果找到匹配的基础模型名称，则返回对应的AI模型实体的深拷贝，否则返回None。
        """
        # 遍历预定义的语音转文本基础模型列表
        for ai_model_entity in SPEECH2TEXT_BASE_MODELS:
            # 如果找到匹配的基础模型名称
            if ai_model_entity.base_model_name == base_model_name:
                # 创建该模型实体的深拷贝
                ai_model_entity_copy = copy.deepcopy(ai_model_entity)
                # 更新模型和标签信息
                ai_model_entity_copy.entity.model = model
                ai_model_entity_copy.entity.label.en_US = model
                ai_model_entity_copy.entity.label.zh_Hans = model
                # 返回更新后的模型实体深拷贝
                return ai_model_entity_copy

        # 如果没有找到匹配的基础模型名称，返回None
        return None
