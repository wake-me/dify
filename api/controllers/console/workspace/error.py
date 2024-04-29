from libs.exception import BaseHTTPException

# 定义了一系列与用户账户操作相关的HTTP异常类，用于处理不同的错误情况

class RepeatPasswordNotMatchError(BaseHTTPException):
    """
    新密码和重复密码不匹配异常类。
    
    继承自BaseHTTPException，用于在新密码和重复密码不匹配时抛出。
    """
    error_code = 'repeat_password_not_match'  # 错误代码
    description = "New password and repeat password does not match."  # 错误描述
    code = 400  # HTTP状态码

class CurrentPasswordIncorrectError(BaseHTTPException):
    """
    当前密码不正确异常类。
    
    继承自BaseHTTPException，用于在当前密码不正确时抛出。
    """
    error_code = 'current_password_incorrect'  # 错误代码
    description = "Current password is incorrect."  # 错误描述
    code = 400  # HTTP状态码

class ProviderRequestFailedError(BaseHTTPException):
    """
    提供商请求失败异常类。
    
    继承自BaseHTTPException，用于在向提供商发起的请求失败时抛出。
    """
    error_code = 'provider_request_failed'  # 错误代码
    description = None  # 错误描述为空
    code = 400  # HTTP状态码

class InvalidInvitationCodeError(BaseHTTPException):
    """
    邀请码无效异常类。
    
    继承自BaseHTTPException，用于在提供的邀请码无效时抛出。
    """
    error_code = 'invalid_invitation_code'  # 错误代码
    description = "Invalid invitation code."  # 错误描述
    code = 400  # HTTP状态码

class AccountAlreadyInitedError(BaseHTTPException):
    """
    账户已初始化异常类。
    
    继承自BaseHTTPException，用于在账户已经初始化的情况下抛出。
    """
    error_code = 'account_already_inited'  # 错误代码
    description = "The account has been initialized. Please refresh the page."  # 错误描述
    code = 400  # HTTP状态码

class AccountNotInitializedError(BaseHTTPException):
    """
    账户未初始化异常类。
    
    继承自BaseHTTPException，用于在账户尚未初始化的情况下抛出。
    """
    error_code = 'account_not_initialized'  # 错误代码
    description = "The account has not been initialized yet. Please proceed with the initialization process first."  # 错误描述
    code = 400  # HTTP状态码