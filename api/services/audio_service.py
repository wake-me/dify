import io
from typing import Optional

from werkzeug.datastructures import FileStorage

from core.model_manager import ModelManager
from core.model_runtime.entities.model_entities import ModelType
from services.errors.audio import (
    AudioTooLargeServiceError,
    NoAudioUploadedServiceError,
    ProviderNotSupportSpeechToTextServiceError,
    ProviderNotSupportTextToSpeechServiceError,
    UnsupportedAudioTypeServiceError,
)

FILE_SIZE = 30  # 文件大小限制，单位为MB
FILE_SIZE_LIMIT = FILE_SIZE * 1024 * 1024  # 文件大小的上限，转换为字节
ALLOWED_EXTENSIONS = ['mp3', 'mp4', 'mpeg', 'mpga', 'm4a', 'wav', 'webm', 'amr']  # 允许的音频文件扩展名列表


class AudioService:
    """
    音频服务类，提供ASR（语音转文本）和TTS（文本转语音）的功能接口。
    """

    @classmethod
    def transcript_asr(cls, tenant_id: str, file: FileStorage, end_user: Optional[str] = None):
        """
        语音转文本服务接口。

        :param tenant_id: 租户ID，用于识别不同的租户。
        :param file: 包含音频数据的FileStorage对象。
        :param end_user: 可选，最终用户标识。
        :return: 包含转换后文本的字典。
        :raises NoAudioUploadedServiceError: 未上传音频时抛出。
        :raises UnsupportedAudioTypeServiceError: 音频类型不受支持时抛出。
        :raises AudioTooLargeServiceError: 音频文件大小超过限制时抛出。
        :raises ProviderNotSupportSpeechToTextServiceError: 供应商不支持语音转文本服务时抛出。
        """
        # 检查是否上传了音频文件
        if file is None:
            raise NoAudioUploadedServiceError()

        # 检查音频文件类型是否支持
        extension = file.mimetype
        if extension not in [f'audio/{ext}' for ext in ALLOWED_EXTENSIONS]:
            raise UnsupportedAudioTypeServiceError()

        # 读取音频文件内容并检查大小
        file_content = file.read()
        file_size = len(file_content)

        # 如果文件大小超过限制，则抛出异常
        if file_size > FILE_SIZE_LIMIT:
            message = f"Audio size larger than {FILE_SIZE} mb"
            raise AudioTooLargeServiceError(message)

        # 获取语音转文本模型实例
        model_manager = ModelManager()
        model_instance = model_manager.get_default_model_instance(
            tenant_id=tenant_id,
            model_type=ModelType.SPEECH2TEXT
        )
        if model_instance is None:
            raise ProviderNotSupportSpeechToTextServiceError()

        # 准备音频数据供模型处理
        buffer = io.BytesIO(file_content)
        buffer.name = 'temp.mp3'

        # 使用模型进行语音转文本处理
        return {"text": model_instance.invoke_speech2text(file=buffer, user=end_user)}

    @classmethod
    def transcript_tts(cls, tenant_id: str, text: str, voice: str, streaming: bool, end_user: Optional[str] = None):
        """
        文本转语音服务接口。

        :param tenant_id: 租户ID。
        :param text: 需要转换为语音的文本。
        :param voice: 语音合成的音色。
        :param streaming: 是否采用流式转换。
        :param end_user: 可选，最终用户标识。
        :return: 转换后的音频数据。
        :raises ProviderNotSupportTextToSpeechServiceError: 供应商不支持文本转语音服务时抛出。
        """
        # 获取文本转语音模型实例
        model_manager = ModelManager()
        model_instance = model_manager.get_default_model_instance(
            tenant_id=tenant_id,
            model_type=ModelType.TTS
        )
        if model_instance is None:
            raise ProviderNotSupportTextToSpeechServiceError()

        # 使用模型进行文本转语音处理
        try:
            return model_instance.invoke_tts(content_text=text.strip(), user=end_user, streaming=streaming, tenant_id=tenant_id, voice=voice)
        except Exception as e:
            raise e

    @classmethod
    def transcript_tts_voices(cls, tenant_id: str, language: str):
        """
        获取文本转语音服务支持的音色列表。

        :param tenant_id: 租户ID。
        :param language: 语言代码，用于指定需要获取哪种语言的音色列表。
        :return: 支持的音色列表。
        :raises ProviderNotSupportTextToSpeechServiceError: 供应商不支持文本转语音服务时抛出。
        """
        # 获取文本转语音模型实例
        model_manager = ModelManager()
        model_instance = model_manager.get_default_model_instance(
            tenant_id=tenant_id,
            model_type=ModelType.TTS
        )
        if model_instance is None:
            raise ProviderNotSupportTextToSpeechServiceError()

        # 获取支持的音色列表
        try:
            return model_instance.get_tts_voices(language)
        except Exception as e:
            raise e