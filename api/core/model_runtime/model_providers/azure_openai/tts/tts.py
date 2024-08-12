import concurrent.futures
import copy
from typing import Optional

from openai import AzureOpenAI

from core.model_runtime.entities.model_entities import AIModelEntity
from core.model_runtime.errors.invoke import InvokeBadRequestError
from core.model_runtime.errors.validate import CredentialsValidateFailedError
from core.model_runtime.model_providers.__base.tts_model import TTSModel
from core.model_runtime.model_providers.azure_openai._common import _CommonAzureOpenAI
from core.model_runtime.model_providers.azure_openai._constant import TTS_BASE_MODELS, AzureBaseModel


class AzureOpenAIText2SpeechModel(_CommonAzureOpenAI, TTSModel):
    """
    OpenAI文本转语音模型的模型类。
    """

    def _invoke(self, model: str, tenant_id: str, credentials: dict,
                content_text: str, voice: str, user: Optional[str] = None) -> any:
        """
        调用文本转语音模型。

        :param model: model name
        :param tenant_id: user tenant id
        :param credentials: model credentials
        :param content_text: text content to be translated
        :param voice: model timbre
        :param user: unique user id
        :return: text translated to audio file
        """
        if not voice or voice not in [d['value'] for d in self.get_tts_model_voices(model=model, credentials=credentials)]:
            voice = self._get_model_default_voice(model, credentials)

        return self._tts_invoke_streaming(model=model,
                                          credentials=credentials,
                                          content_text=content_text,
                                          voice=voice)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        验证给定的凭证是否可用于指定的文本转语音模型

        :param model: model name
        :param credentials: model credentials
        :return: text translated to audio file
        """
        try:
            self._tts_invoke_streaming(
                model=model,
                credentials=credentials,
                content_text='Hello Dify!',
                voice=self._get_model_default_voice(model, credentials),
            )
        except Exception as ex:
            # 如果在验证过程中遇到异常，则抛出凭证验证失败的错误
            raise CredentialsValidateFailedError(str(ex))

    def _tts_invoke_streaming(self, model: str,  credentials: dict, content_text: str,
                              voice: str) -> any:
        """
        _tts_invoke_streaming text2speech model
        :param model: model name
        :param credentials: model credentials
        :param content_text: text content to be translated
        :param voice: model timbre
        :return: text translated to audio file
        """
        try:
            # doc: https://platform.openai.com/docs/guides/text-to-speech
            credentials_kwargs = self._to_credential_kwargs(credentials)
            client = AzureOpenAI(**credentials_kwargs)
            # max font is 4096,there is 3500 limit for each request
            max_length = 3500
            if len(content_text) > max_length:
                sentences = self._split_text_into_sentences(content_text, max_length=max_length)
                executor = concurrent.futures.ThreadPoolExecutor(max_workers=min(3, len(sentences)))
                futures = [executor.submit(client.audio.speech.with_streaming_response.create, model=model,
                                           response_format="mp3",
                                           input=sentences[i], voice=voice) for i in range(len(sentences))]
                for index, future in enumerate(futures):
                    yield from future.result().__enter__().iter_bytes(1024)

            else:
                response = client.audio.speech.with_streaming_response.create(model=model, voice=voice,
                                                                              response_format="mp3",
                                                                              input=content_text.strip())

                yield from response.__enter__().iter_bytes(1024)
        except Exception as ex:
            # 处理调用过程中可能出现的错误
            raise InvokeBadRequestError(str(ex))

    def _process_sentence(self, sentence: str, model: str,
                        voice, credentials: dict):
        """
        使用指定的语音模型将文本转换为音频文件。

        :param model: 模型名称，指定使用的文本转语音模型。
        :param credentials: 模型认证信息，用于创建模型实例。
        :param voice: 模型音色，指定输出音频的声音特点。
        :param sentence: 需要转换为语音的文本内容。
        :return: 返回转换后的音频文件内容，如果转换成功则为bytes类型。
        """
        credentials_kwargs = self._to_credential_kwargs(credentials)
        # 创建Azure OpenAI客户端实例
        client = AzureOpenAI(**credentials_kwargs)
        # 调用API，使用指定模型、声音和文本创建音频
        response = client.audio.speech.create(model=model, voice=voice, input=sentence.strip())
        # 检查响应内容，如果是字节类型则返回
        if isinstance(response.read(), bytes):
            return response.read()

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
    def _get_ai_model_entity(base_model_name: str, model: str) -> AzureBaseModel | None:
        for ai_model_entity in TTS_BASE_MODELS:
            if ai_model_entity.base_model_name == base_model_name:
                # 找到匹配项，创建该实体的深拷贝
                ai_model_entity_copy = copy.deepcopy(ai_model_entity)
                # 更新拷贝的模型名称和标签
                ai_model_entity_copy.entity.model = model
                ai_model_entity_copy.entity.label.en_US = model
                ai_model_entity_copy.entity.label.zh_Hans = model
                # 返回更新后的实体拷贝
                return ai_model_entity_copy
        return None
