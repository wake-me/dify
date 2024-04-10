from libs.exception import BaseHTTPException


class NotCompletionAppError(BaseHTTPException):
    """
    不是一个完成应用的错误
    
    属性:
        error_code (str): 错误代码，用于标识错误类型。
        description (str): 错误描述，提供关于错误的简短说明。
        code (int): HTTP状态码，表示错误的严重性和类型。
    """
    error_code = 'not_completion_app'
    description = "Not Completion App"
    code = 400


class NotChatAppError(BaseHTTPException):
    """
    不是一个聊天应用的错误
    
    属性:
        error_code (str): 错误代码，用于标识错误类型。
        description (str): 错误描述，提供关于错误的简短说明。
        code (int): HTTP状态码，表示错误的严重性和类型。
    """
    error_code = 'not_chat_app'
    description = "Not Chat App"
    code = 400


class AppSuggestedQuestionsAfterAnswerDisabledError(BaseHTTPException):
    """
    应用中回答后建议问题功能被禁用的错误
    
    属性:
        error_code (str): 错误代码，用于标识错误类型。
        description (str): 错误描述，提供关于错误的简短说明。
        code (int): HTTP状态码，表示错误的严重性和类型。
    """
    error_code = 'app_suggested_questions_after_answer_disabled'
    description = "Function Suggested questions after answer disabled."
    code = 403