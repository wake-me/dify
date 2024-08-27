from typing import Optional


class LLMError(Exception):
    """
    所有LLM异常的基类。
    """
    description: Optional[str] = None

    def __init__(self, description: Optional[str] = None) -> None:
        """
        初始化LLM错误实例。
        
        :param description: 错误描述，可选。
        """
        self.description = description


class LLMBadRequestError(LLMError):
    """
    当LLM返回错误请求时抛出。
    """
    description = "Bad Request"


class ProviderTokenNotInitError(Exception):
    """
    自定义异常，当提供者令牌未初始化时抛出。
    """
    description = "Provider Token Not Init"

    def __init__(self, *args, **kwargs):
        """
        初始化提供者令牌未初始化异常实例。
        
        :param args: 包含错误描述的参数列表。
        :param kwargs: 关键字参数。
        """
        self.description = args[0] if args else self.description


class QuotaExceededError(Exception):
    """
    自定义异常，当提供商的配额被超过时抛出。
    """
    description = "Quota Exceeded"


class AppInvokeQuotaExceededError(Exception):
    """
    Custom exception raised when the quota for an app has been exceeded.
    """
    description = "App Invoke Quota Exceeded"


class ModelCurrentlyNotSupportError(Exception):
    """
    自定义异常，当模型当前不支持时抛出。
    """
    description = "Model Currently Not Support"


class InvokeRateLimitError(Exception):
    """Raised when the Invoke returns rate limit error."""
    description = "Rate Limit Error"
