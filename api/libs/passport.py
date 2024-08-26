import jwt
from werkzeug.exceptions import Unauthorized

from configs import dify_config


class PassportService:
    """
    PassportService 类用于处理护照服务相关的操作，包括发行和验证JWT token。
    """
    def __init__(self):
        self.sk = dify_config.SECRET_KEY

    def issue(self, payload):
        return jwt.encode(payload, self.sk, algorithm="HS256")

    def verify(self, token):
        """
        验证JWT token。

        参数:
        - token: 字符串类型，待验证的JWT token。

        返回值:
        - 验证成功后返回解码的token负载。
        
        异常:
        - 如果token签名无效、无法解码或已过期，则抛出Unauthorized异常。
        """
        try:
            return jwt.decode(token, self.sk, algorithms=["HS256"])
        except jwt.exceptions.InvalidSignatureError:
            raise Unauthorized("Invalid token signature.")
        except jwt.exceptions.DecodeError:
            raise Unauthorized("Invalid token.")
        except jwt.exceptions.ExpiredSignatureError:
            raise Unauthorized("Token has expired.")
