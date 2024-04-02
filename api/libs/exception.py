from typing import Optional

from werkzeug.exceptions import HTTPException


class BaseHTTPException(HTTPException):
    """
    基础HTTP异常类，用于定义通用的HTTP异常信息。
    
    Attributes:
        error_code (str): 异常的错误代码，默认为'unknown'。
        data (Optional[dict]): 异常相关的数据信息，默认为None。包含错误代码(code)、错误信息(message)和状态码(status)。
    """
    
    error_code: str = 'unknown'  # 错误代码
    data: Optional[dict] = None  # 异常相关的数据

    def __init__(self, description=None, response=None):
        """
        初始化基础HTTP异常实例。
        
        Args:
            description (Optional[str]): 异常描述信息，默认为None。
            response (Optional[HTTPResponse]): 相应的HTTP响应，默认为None。
        """
        super().__init__(description, response)  # 调用父类构造函数

        # 初始化data属性，包含错误代码、错误描述和状态码
        self.data = {
            "code": self.error_code,
            "message": self.description,
            "status": self.code,
        }