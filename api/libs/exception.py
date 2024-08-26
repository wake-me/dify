from typing import Optional

from werkzeug.exceptions import HTTPException


class BaseHTTPException(HTTPException):
    error_code: str = "unknown"
    data: Optional[dict] = None

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
