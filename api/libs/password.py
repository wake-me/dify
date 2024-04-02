import base64
import binascii
import hashlib
import re

password_pattern = r"^(?=.*[a-zA-Z])(?=.*\d).{8,}$"

def valid_password(password):
    """
    验证密码是否符合规定格式。
    
    参数:
    - password: 待验证的密码字符串。
    
    返回值:
    - 如果密码符合规定格式，则返回该密码字符串。
    - 如果密码不符合规定格式，则抛出 ValueError 异常。
    """
    # 定义密码规则的正则表达式模式
    pattern = password_pattern
    # 检查密码是否匹配模式
    if re.match(pattern, password) is not None:
        return password

    raise ValueError('Not a valid password.')


def hash_password(password_str, salt_byte):
    """
    使用 pbkdf2_hmac 算法对密码进行哈希处理。
    
    参数:
    - password_str: 待哈希处理的密码字符串。
    - salt_byte: 盐值，用于加强哈希算法的随机性，为字节串。
    
    返回值:
    - 返回经过 pbkdf2_hmac 哈希算法处理后的密码的十六进制字符串表示。
    """
    dk = hashlib.pbkdf2_hmac('sha256', password_str.encode('utf-8'), salt_byte, 10000)
    return binascii.hexlify(dk)


def compare_password(password_str, password_hashed_base64, salt_base64):
    """
    对比输入的密码字符串和哈希后的密码，以验证密码是否正确。
    
    参数:
    - password_str: 用户输入的密码字符串。
    - password_hashed_base64: 哈希处理后的密码，以 base64 编码的字符串形式存储。
    - salt_base64: 盐值，以 base64 编码的字符串形式存储。
    
    返回值:
    - 如果输入的密码字符串经过哈希处理后与存储的哈希密码匹配，则返回 True，否则返回 False。
    """
    # 对比密码用于登录验证
    return hash_password(password_str, base64.b64decode(salt_base64)) == base64.b64decode(password_hashed_base64)