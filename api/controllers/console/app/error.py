from libs.exception import BaseHTTPException


class AppNotFoundError(BaseHTTPException):
    """
    应用未找到错误。当尝试访问一个不存在的应用时抛出。
    """
    error_code = 'app_not_found'
    description = "App not found."
    code = 404


class ProviderNotInitializeError(BaseHTTPException):
    """
    提供者未初始化错误。当没有找到有效的模型提供者凭证时抛出。
    """
    error_code = 'provider_not_initialize'
    description = "No valid model provider credentials found. " \
                  "Please go to Settings -> Model Provider to complete your provider credentials."
    code = 400


class ProviderQuotaExceededError(BaseHTTPException):
    """
    提供者配额超过错误。当对Dify Hosted Model Provider的配额已用尽时抛出。
    """
    error_code = 'provider_quota_exceeded'
    description = "Your quota for Dify Hosted Model Provider has been exhausted. " \
                  "Please go to Settings -> Model Provider to complete your own provider credentials."
    code = 400


class ProviderModelCurrentlyNotSupportError(BaseHTTPException):
    """
    提供者当前不支持的模型错误。当尝试使用Dify Hosted OpenAI试用版时不支持GPT-4模型时抛出。
    """
    error_code = 'model_currently_not_support'
    description = "Dify Hosted OpenAI trial currently not support the GPT-4 model."
    code = 400


class ConversationCompletedError(BaseHTTPException):
    """
    对话结束错误。当尝试在一个已经结束的对话中继续发送消息时抛出。
    """
    error_code = 'conversation_completed'
    description = "The conversation has ended. Please start a new conversation."
    code = 400


class AppUnavailableError(BaseHTTPException):
    """
    应用不可用错误。当应用配置出错或应用处于不可用状态时抛出。
    """
    error_code = 'app_unavailable'
    description = "App unavailable, please check your app configurations."
    code = 400


class CompletionRequestError(BaseHTTPException):
    """
    完成请求错误。当完成请求失败时抛出。
    """
    error_code = 'completion_request_error'
    description = "Completion request failed."
    code = 400


class AppMoreLikeThisDisabledError(BaseHTTPException):
    """
    '更多类似'功能禁用错误。当尝试使用已禁用的'更多类似'功能时抛出。
    """
    error_code = 'app_more_like_this_disabled'
    description = "The 'More like this' feature is disabled. Please refresh your page."
    code = 403


class NoAudioUploadedError(BaseHTTPException):
    """
    未上传音频错误。当尝试进行音频相关操作但未上传音频时抛出。
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
    不支持的音频类型错误。当上传了不允许的音频类型时抛出。
    """
    error_code = 'unsupported_audio_type'
    description = "Audio type not allowed."
    code = 415


class ProviderNotSupportSpeechToTextError(BaseHTTPException):
    """
    提供者不支持语音转文本错误。当尝试使用一个不支持语音转文本的提供者时抛出。
    """
    error_code = 'provider_not_support_speech_to_text'
    description = "Provider not support speech to text."
    code = 400


class NoFileUploadedError(BaseHTTPException):
    """
    未上传文件错误。当尝试进行文件相关操作但未上传文件时抛出。
    """
    error_code = 'no_file_uploaded'
    description = "Please upload your file."
    code = 400


class TooManyFilesError(BaseHTTPException):
    """
    文件过多错误。当上传的文件数量超过限制时抛出。
    """
    error_code = 'too_many_files'
    description = "Only one file is allowed."
    code = 400


class DraftWorkflowNotExist(BaseHTTPException):
    """
    一个用于表示草稿工作流不存在的HTTP异常类。
    
    继承自BaseHTTPException，用于在尝试访问或使用未初始化的草稿工作流时抛出。
    
    属性:
    - error_code (str): 异常的错误代码，用于标识异常类型。
    - description (str): 异常的描述信息，提供关于异常的简短说明。
    - code (int): 异常对应的HTTP状态码。
    """
    error_code = 'draft_workflow_not_exist'  # 错误代码，标识草稿工作流不存在的异常
    description = "Draft workflow need to be initialized."  # 异常描述，提示需要初始化草稿工作流
    code = 400  # 对应的HTTP状态码，此处为400 Bad Request
