from libs.exception import BaseHTTPException


class AppUnavailableError(BaseHTTPException):
    """
    应用不可用错误。当应用配置有误或不可用时抛出。
    """
    error_code = 'app_unavailable'
    description = "App unavailable, please check your app configurations."
    code = 400


class NotCompletionAppError(BaseHTTPException):
    """
    完成应用错误。当完成应用模式与正确的API路由不匹配时抛出。
    """
    error_code = 'not_completion_app'
    description = "Please check if your Completion app mode matches the right API route."
    code = 400


class NotChatAppError(BaseHTTPException):
    """
    聊天应用错误。当聊天应用模式与正确的API路由不匹配时抛出。
    """
    error_code = 'not_chat_app'
    description = "Please check if your app mode matches the right API route."
    code = 400


class NotWorkflowAppError(BaseHTTPException):
    error_code = 'not_workflow_app'
    description = "Please check if your app mode matches the right API route."
    code = 400


class ConversationCompletedError(BaseHTTPException):
    """
    对话已完成错误。当尝试在已完成的对话上操作时抛出。
    """
    error_code = 'conversation_completed'
    description = "The conversation has ended. Please start a new conversation."
    code = 400


class ProviderNotInitializeError(BaseHTTPException):
    """
    提供商未初始化错误。当未找到有效的模型提供商凭证时抛出。
    """
    error_code = 'provider_not_initialize'
    description = "No valid model provider credentials found. " \
                  "Please go to Settings -> Model Provider to complete your provider credentials."
    code = 400


class ProviderQuotaExceededError(BaseHTTPException):
    """
    提供商配额超限错误。当Dify Hosted OpenAI的配额已用尽时抛出。
    """
    error_code = 'provider_quota_exceeded'
    description = "Your quota for Dify Hosted OpenAI has been exhausted. " \
                  "Please go to Settings -> Model Provider to complete your own provider credentials."
    code = 400


class ProviderModelCurrentlyNotSupportError(BaseHTTPException):
    """
    提供商当前不支持的模型错误。当Dify Hosted OpenAI试用版当前不支持GPT-4模型时抛出。
    """
    error_code = 'provider_model_currently_not_support'
    description = "Dify Hosted OpenAI trial currently not support the GPT-4 model."
    code = 400


class CompletionRequestError(BaseHTTPException):
    """
    完成请求错误。当完成请求失败时抛出。
    """
    error_code = 'completion_request_error'
    description = "Completion request failed."
    code = 400


class NoAudioUploadedError(BaseHTTPException):
    """
    未上传音频错误。当尝试处理未上传的音频时抛出。
    """
    error_code = 'no_audio_uploaded'
    description = "Please upload your audio."
    code = 400


class AudioTooLargeError(BaseHTTPException):
    """
    音频过大错误。当上传的音频大小超过限制时抛出。
    """
    error_code = 'audio_too_large'
    description = "Audio size exceeded. {message}"
    code = 413


class UnsupportedAudioTypeError(BaseHTTPException):
    """
    不支持的音频类型错误。当上传不支持的音频类型时抛出。
    """
    error_code = 'unsupported_audio_type'
    description = "Audio type not allowed."
    code = 415


class ProviderNotSupportSpeechToTextError(BaseHTTPException):
    """
    提供商不支持语音转文本错误。当尝试使用不支持语音转文本的提供商时抛出。
    """
    error_code = 'provider_not_support_speech_to_text'
    description = "Provider not support speech to text."
    code = 400


class NoFileUploadedError(BaseHTTPException):
    """
    未上传文件错误。当尝试处理未上传的文件时抛出。
    """
    error_code = 'no_file_uploaded'
    description = "Please upload your file."
    code = 400


class TooManyFilesError(BaseHTTPException):
    """
    文件过多错误。当上传的文件超过限制时抛出。
    """
    error_code = 'too_many_files'
    description = "Only one file is allowed."
    code = 400


class FileTooLargeError(BaseHTTPException):
    """
    文件过大错误。当上传的文件大小超过限制时抛出。
    """
    error_code = 'file_too_large'
    description = "File size exceeded. {message}"
    code = 413


class UnsupportedFileTypeError(BaseHTTPException):
    """
    不支持的文件类型错误。当上传不支持的文件类型时抛出。
    """
    error_code = 'unsupported_file_type'
    description = "File type not allowed."
    code = 415