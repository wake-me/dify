import concurrent.futures
import copy
from functools import reduce
from io import BytesIO
from typing import Optional

from flask import Response, stream_with_context
from openai import AzureOpenAI
from pydub import AudioSegment

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
                content_text: str, voice: str, streaming: bool, user: Optional[str] = None) -> any:
        """
        调用文本转语音模型。

        :param model: 模型名称。
        :param tenant_id: 用户租户ID。
        :param credentials: 模型的凭证信息。
        :param content_text: 需要转换的文本内容。
        :param voice: 模型的音色。
        :param streaming: 输出是否为流式。
        :param user: 唯一的用户ID，可选。
        :return: 转换后的音频文件。
        """
        # 获取模型支持的音频类型
        audio_type = self._get_model_audio_type(model, credentials)
        # 检查并设置音色
        if not voice or voice not in [d['value'] for d in self.get_tts_model_voices(model=model, credentials=credentials)]:
            voice = self._get_model_default_voice(model, credentials)
        # 根据是否为流式处理返回不同的响应
        if streaming:
            # 返回流式音频响应
            return Response(stream_with_context(self._tts_invoke_streaming(model=model,
                                                                           credentials=credentials,
                                                                           content_text=content_text,
                                                                           tenant_id=tenant_id,
                                                                           voice=voice)),
                            status=200, mimetype=f'audio/{audio_type}')
        else:
            # 返回非流式音频
            return self._tts_invoke(model=model, credentials=credentials, content_text=content_text, voice=voice)

    def validate_credentials(self, model: str, credentials: dict, user: Optional[str] = None) -> None:
        """
        验证给定的凭证是否可用于指定的文本转语音模型

        :param model: 模型名称
        :param credentials: 模型所需的凭证信息
        :param user: 唯一的用户ID，可选参数，默认为None
        :return: 无返回值，但会在验证失败时抛出CredentialsValidateFailedError异常
        """
        try:
            # 尝试使用提供的模型、凭证和默认声音合成文本'Hello Dify!'，以验证凭证的有效性
            self._tts_invoke(
                model=model,
                credentials=credentials,
                content_text='Hello Dify!',
                voice=self._get_model_default_voice(model, credentials),
            )
        except Exception as ex:
            # 如果在验证过程中遇到异常，则抛出凭证验证失败的错误
            raise CredentialsValidateFailedError(str(ex))

    def _tts_invoke(self, model: str, credentials: dict, content_text: str, voice: str) -> Response:
        """
        调用文本转语音（TTS）模型

        :param model: 模型名称
        :param credentials: 模型所需的凭证信息
        :param content_text: 需要转换为语音的文本内容
        :param voice: 模型的音色
        :return: 转换后的音频文件响应对象
        """
        # 获取模型的音频类型、单词限制和最大工作线程数
        audio_type = self._get_model_audio_type(model, credentials)
        word_limit = self._get_model_word_limit(model, credentials)
        max_workers = self._get_model_workers_limit(model, credentials)
        
        try:
            # 将文本拆分为句子列表，以适应模型处理限制
            sentences = list(self._split_text_into_sentences(text=content_text, limit=word_limit))
            audio_bytes_list = list()
            
            # 使用线程池并行处理每个句子
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(self._process_sentence, sentence=sentence, model=model, voice=voice,
                                        credentials=credentials) for sentence in sentences]
                for future in futures:
                    try:
                        # 成功的结果将被添加到音频字节列表中
                        if future.result():
                            audio_bytes_list.append(future.result())
                    except Exception as ex:
                        # 处理任务执行中的错误
                        raise InvokeBadRequestError(str(ex))

            # 如果有音频片段，则将它们合并为一个音频文件
            if len(audio_bytes_list) > 0:
                audio_segments = [AudioSegment.from_file(BytesIO(audio_bytes), format=audio_type) for audio_bytes in
                                audio_bytes_list if audio_bytes]
                combined_segment = reduce(lambda x, y: x + y, audio_segments)
                buffer: BytesIO = BytesIO()
                # 将合并后的音频导出到内存缓冲区
                combined_segment.export(buffer, format=audio_type)
                buffer.seek(0)
                # 返回音频文件的HTTP响应
                return Response(buffer.read(), status=200, mimetype=f"audio/{audio_type}")
        except Exception as ex:
            # 处理调用过程中的任何异常
            raise InvokeBadRequestError(str(ex))

    # Todo: To improve the streaming function
    def _tts_invoke_streaming(self, model: str, tenant_id: str, credentials: dict, content_text: str,
                              voice: str) -> any:
        """
        调用文本转语音的流式处理函数

        :param model: 模型名称
        :param tenant_id: 用户租户ID
        :param credentials: 模型认证信息
        :param content_text: 需要转换为语音的文本内容
        :param voice: 模型的音色
        :return: 转换后的音频文件
        """
        # 将认证信息转换为模型实例所需的kwargs参数
        credentials_kwargs = self._to_credential_kwargs(credentials)
        # 检查并设置语音参数
        if not voice or voice not in self.get_tts_model_voices(model=model, credentials=credentials):
            voice = self._get_model_default_voice(model, credentials)
        # 获取模型的单词限制和音频类型
        word_limit = self._get_model_word_limit(model, credentials)
        audio_type = self._get_model_audio_type(model, credentials)
        # 根据文本内容生成文件名
        tts_file_id = self._get_file_name(content_text)
        # 设置音频文件路径
        file_path = f'generate_files/audio/{tenant_id}/{tts_file_id}.{audio_type}'
        try:
            # 初始化客户端
            client = AzureOpenAI(**credentials_kwargs)
            # 将文本根据单词限制分割为句子
            sentences = list(self._split_text_into_sentences(text=content_text, limit=word_limit))
            for sentence in sentences:
                # 创建语音并将其保存到文件
                response = client.audio.speech.create(model=model, voice=voice, input=sentence.strip())
                # storage.save(file_path, response.read()) 该行代码用于将响应的音频流保存到文件
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
        # 将认证信息转换为模型实例所需的参数
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
    def _get_ai_model_entity(base_model_name: str, model: str) -> AzureBaseModel:
        """
        根据基础模型名称和模型名称获取AI模型实体。
        
        参数:
        - base_model_name: str，基础模型的名称。
        - model: str，模型的名称。
        
        返回值:
        - AzureBaseModel，如果找到匹配的基础模型名称，则返回对应的AI模型实体的深拷贝，否则返回None。
        """
        # 遍历所有基础模型实体，查找匹配的基础模型名称
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

        # 如果没有找到匹配的基础模型名称，返回None
        return None
