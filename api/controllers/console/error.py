from libs.exception import BaseHTTPException


class AlreadySetupError(BaseHTTPException):
    """
    已经设置错误：当Dify已经成功安装时触发，提示用户刷新页面或返回仪表板首页。
    """
    error_code = 'already_setup'
    description = "Dify has been successfully installed. Please refresh the page or return to the dashboard homepage."
    code = 403


class NotSetupError(BaseHTTPException):
    """
    未设置错误：当Dify尚未初始化和安装时触发，提示用户先进行初始化和安装流程。
    """
    error_code = 'not_setup'
    description = "Dify has not been initialized and installed yet. " \
                  "Please proceed with the initialization and installation process first."
    code = 401

class NotInitValidateError(BaseHTTPException):
    """
    未初始化验证错误：当初始化验证尚未完成时触发，提示用户先进行初始化验证流程。
    """
    error_code = 'not_init_validated'
    description = "Init validation has not been completed yet. " \
                  "Please proceed with the init validation process first."
    code = 401

class InitValidateFailedError(BaseHTTPException):
    """
    初始化验证失败错误：当初始化验证失败时触发，提示用户检查密码并重试。
    """
    error_code = 'init_validate_failed'
    description = "Init validation failed. Please check the password and try again."
    code = 401

class AccountNotLinkTenantError(BaseHTTPException):
    """
    账户未关联租户错误：当账户未关联租户时触发，提示用户进行账户和租户的关联。
    """
    error_code = 'account_not_link_tenant'
    description = "Account not link tenant."
    code = 403


class AlreadyActivateError(BaseHTTPException):
    """
    已经激活错误：当认证令牌无效或账户已经激活时触发，提示用户重新检查。
    """
    error_code = 'already_activate'
    description = "Auth Token is invalid or account already activated, please check again."
    code = 403