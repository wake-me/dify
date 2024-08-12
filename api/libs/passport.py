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
        """
        发行JWT token。

        参数:
        - payload: 字典类型，包含需要编码进token的数据。

        返回值:
        - 编码后的JWT token字符串。
        """
        return jwt.encode(payload, self.sk, algorithm='HS256')

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
            # 尝试解码token
            return jwt.decode(token, self.sk, algorithms=['HS256'])
        except jwt.exceptions.InvalidSignatureError:
            # 如果签名无效，抛出Unauthorized异常
            raise Unauthorized('Invalid token signature.')
        except jwt.exceptions.DecodeError:
            # 如果token无法解码，抛出Unauthorized异常
            raise Unauthorized('Invalid token.')
        except jwt.exceptions.ExpiredSignatureError:
            # 如果token已过期，抛出Unauthorized异常
            raise Unauthorized('Token has expired.')