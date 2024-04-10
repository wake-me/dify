from libs.exception import BaseHTTPException


# 定义一系列的HTTP异常，用于处理应用程序在请求过程中可能出现的错误。

class AppUnavailableError(BaseHTTPException):
    """
    应用不可用错误。
    描述：应用不可用，请检查应用配置。
    错误码：400
    """
    error_code = 'app_unavailable'
    description = "App unavailable, please check your app configurations."
    code = 400


class NotCompletionAppError(BaseHTTPException):
    """
    未找到Completion应用错误。
    描述：请检查您的Completion应用模式是否与正确的API路由匹配。
    错误码：400
    """
    error_code = 'not_completion_app'
    description = "Please check if your Completion app mode matches the right API route."
    code = 400


class NotChatAppError(BaseHTTPException):
    """
    未找到聊天应用错误。
    描述：请检查您的聊天应用模式是否与正确的API路由匹配。
    错误码：400
    """
    error_code = 'not_chat_app'
    description = "Please check if your app mode matches the right API route."
    code = 400


class NotWorkflowAppError(BaseHTTPException):
    """
    一个用于表示非工作流应用错误的自定义HTTP异常类。
    
    属性:
    error_code (str): 错误代码，用于标识错误类型。
    description (str): 错误描述，提供关于错误的详细信息。
    code (int): HTTP状态码，表示异常的HTTP响应状态。
    """
    error_code = 'not_workflow_app'
    description = "Please check if your Workflow app mode matches the right API route."
    code = 400

class ConversationCompletedError(BaseHTTPException):
    """
    对话完成错误。
    描述：对话已经结束。请开始新的对话。
    错误码：400
    """
    error_code = 'conversation_completed'
    description = "The conversation has ended. Please start a new conversation."
    code = 400


class ProviderNotInitializeError(BaseHTTPException):
    """
    提供商未初始化错误。
    描述：未找到有效的模型提供商凭据。请转到设置 -> 模型提供商完成您的提供商凭据。
    错误码：400
    """
    error_code = 'provider_not_initialize'
    description = "No valid model provider credentials found. " \
                  "Please go to Settings -> Model Provider to complete your provider credentials."
    code = 400


class ProviderQuotaExceededError(BaseHTTPException):
    """
    提供商配额超出错误。
    描述：您的Dify Hosted OpenAI配额已经用尽。请转到设置 -> 模型提供商完成您自己的提供商凭据。
    错误码：400
    """
    error_code = 'provider_quota_exceeded'
    description = "Your quota for Dify Hosted OpenAI has been exhausted. " \
                  "Please go to Settings -> Model Provider to complete your own provider credentials."
    code = 400


class ProviderModelCurrentlyNotSupportError(BaseHTTPException):
    """
    提供商当前不支持模型错误。
    描述：Dify Hosted OpenAI试用目前不支持GPT-4模型。
    错误码：400
    """
    error_code = 'provider_model_currently_not_support'
    description = "Dify Hosted OpenAI trial currently not support the GPT-4 model."
    code = 400


class CompletionRequestError(BaseHTTPException):
    """
    Completion请求错误。
    描述：Completion请求失败。
    错误码：400
    """
    error_code = 'completion_request_error'
    description = "Completion request failed."
    code = 400


class AppMoreLikeThisDisabledError(BaseHTTPException):
    """
    应用“更多类似”功能禁用错误。
    描述：“更多类似”功能已禁用。请刷新页面。
    错误码：403
    """
    error_code = 'app_more_like_this_disabled'
    description = "The 'More like this' feature is disabled. Please refresh your page."
    code = 403


class AppSuggestedQuestionsAfterAnswerDisabledError(BaseHTTPException):
    """
    应用回答后建议问题功能禁用错误。
    描述：“回答后建议问题”功能已禁用。请刷新页面。
    错误码：403
    """
    error_code = 'app_suggested_questions_after_answer_disabled'
    description = "The 'Suggested Questions After Answer' feature is disabled. Please refresh your page."
    code = 403


class NoAudioUploadedError(BaseHTTPException):
    """
    未上传音频错误。
    描述：请上传您的音频。
    错误码：400
    """
    error_code = 'no_audio_uploaded'
    description = "Please upload your audio."
    code = 400


class AudioTooLargeError(BaseHTTPException):
    """
    音频过大错误。
    描述：音频大小超出限制。{message}
    错误码：413
    """
    error_code = 'audio_too_large'
    description = "Audio size exceeded. {message}"
    code = 413


class UnsupportedAudioTypeError(BaseHTTPException):
    """
    不支持的音频类型错误。
    描述：不允许的音频类型。
    错误码：415
    """
    error_code = 'unsupported_audio_type'
    description = "Audio type not allowed."
    code = 415


class ProviderNotSupportSpeechToTextError(BaseHTTPException):
    """
    提供商不支持文本转语音错误。
    描述：提供商不支持文本转语音。
    错误码：400
    """
    error_code = 'provider_not_support_speech_to_text'
    description = "Provider not support speech to text."
    code = 400


class NoFileUploadedError(BaseHTTPException):
    """
    未上传文件错误。
    描述：请上传您的文件。
    错误码：400
    """
    error_code = 'no_file_uploaded'
    description = "Please upload your file."
    code = 400


class TooManyFilesError(BaseHTTPException):
    """
    文件过多错误。
    描述：只允许上传一个文件。
    错误码：400
    """
    error_code = 'too_many_files'
    description = "Only one file is allowed."
    code = 400


class FileTooLargeError(BaseHTTPException):
    """
    文件过大错误。
    描述：文件大小超出限制。{message}
    错误码：413
    """
    error_code = 'file_too_large'
    description = "File size exceeded. {message}"
    code = 413


class UnsupportedFileTypeError(BaseHTTPException):
    """
    不支持的文件类型错误。
    描述：不允许的文件类型。
    错误码：415
    """
    error_code = 'unsupported_file_type'
    description = "File type not allowed."
    code = 415