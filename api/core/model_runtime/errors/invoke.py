from typing import Optional


class InvokeError(Exception):
    """
    LLM异常的基类。
    
    属性:
        description (Optional[str]): 异常的描述信息，可以为空。
    """
    
    description: Optional[str] = None  # 异常描述

    def __init__(self, description: Optional[str] = None) -> None:
        """
        初始化InvokeError实例。
        
        参数:
            description (Optional[str]): 异常的描述信息，可以为空。
        """
        self.description = description

    def __str__(self):
        """
        返回异常的字符串表示形式。
        
        返回:
            str: 异常的描述信息或类名。
        """
        return self.description or self.__class__.__name__

class InvokeConnectionError(InvokeError):
    """
    当Invoke返回连接错误时抛出。
    Attributes:
        description (str): 错误描述信息，此处为"Connection Error"。
    """
    description = "Connection Error"


class InvokeServerUnavailableError(InvokeError):
    """
    当Invoke返回服务器不可用错误时抛出。
    Attributes:
        description (str): 错误描述信息，此处为"Server Unavailable Error"。
    """
    description = "Server Unavailable Error"


class InvokeRateLimitError(InvokeError):
    """
    当Invoke返回速率限制错误时抛出。
    Attributes:
        description (str): 错误描述信息，此处为"Rate Limit Error"。
    """
    description = "Rate Limit Error"


class InvokeAuthorizationError(InvokeError):
    """
    当Invoke返回授权错误时抛出。
    Attributes:
        description (str): 错误描述信息，提示提供的模型凭证不正确，请检查后重试。
    """
    description = "Incorrect model credentials provided, please check and try again. "


class InvokeBadRequestError(InvokeError):
    """
    当Invoke返回错误的请求时抛出。
    Attributes:
        description (str): 错误描述信息，此处为"Bad Request Error"。
    """
    description = "Bad Request Error"