import io
from typing import Optional

from werkzeug.datastructures import FileStorage

from core.model_manager import ModelManager
from core.model_runtime.entities.model_entities import ModelType
from models.model import App, AppMode, AppModelConfig
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
    def transcript_asr(cls, app_model: App, file: FileStorage, end_user: Optional[str] = None):
        if app_model.mode in [AppMode.ADVANCED_CHAT.value, AppMode.WORKFLOW.value]:
            workflow = app_model.workflow
            if workflow is None:
                raise ValueError("Speech to text is not enabled")

            features_dict = workflow.features_dict
            if 'speech_to_text' not in features_dict or not features_dict['speech_to_text'].get('enabled'):
                raise ValueError("Speech to text is not enabled")
        else:
            app_model_config: AppModelConfig = app_model.app_model_config

            if not app_model_config.speech_to_text_dict['enabled']:
                raise ValueError("Speech to text is not enabled")

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
            tenant_id=app_model.tenant_id,
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
    def transcript_tts(cls, app_model: App, text: str, streaming: bool,
                       voice: Optional[str] = None, end_user: Optional[str] = None):
        if app_model.mode in [AppMode.ADVANCED_CHAT.value, AppMode.WORKFLOW.value]:
            workflow = app_model.workflow
            if workflow is None:
                raise ValueError("TTS is not enabled")

            features_dict = workflow.features_dict
            if 'text_to_speech' not in features_dict or not features_dict['text_to_speech'].get('enabled'):
                raise ValueError("TTS is not enabled")

            voice = features_dict['text_to_speech'].get('voice') if voice is None else voice
        else:
            text_to_speech_dict = app_model.app_model_config.text_to_speech_dict

            if not text_to_speech_dict.get('enabled'):
                raise ValueError("TTS is not enabled")

            voice = text_to_speech_dict.get('voice') if voice is None else voice

        model_manager = ModelManager()
        model_instance = model_manager.get_default_model_instance(
            tenant_id=app_model.tenant_id,
            model_type=ModelType.TTS
        )
        if model_instance is None:
            raise ProviderNotSupportTextToSpeechServiceError()

        # 使用模型进行文本转语音处理
        try:
            return model_instance.invoke_tts(
                content_text=text.strip(),
                user=end_user,
                streaming=streaming,
                tenant_id=app_model.tenant_id,
                voice=voice
            )
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