import base64

from extensions.ext_database import db
from libs import rsa
from models.account import Tenant


def obfuscated_token(token: str):
    """
    隐形化令牌函数，将令牌的中间部分用星号隐藏。
    
    参数:
    token: str - 需要被隐形化的令牌字符串。
    
    返回:
    str - 隐形化后的令牌字符串，只显示前后各三个字符，中间用星号代替。
    """
    return token[:6] + '*' * (len(token) - 8) + token[-2:]

def encrypt_token(tenant_id: str, token: str):
    """
    对令牌进行加密，使用RSA算法并结合租户的公钥。
    
    参数:
    tenant_id: str - 租户的唯一标识符。
    token: str - 需要被加密的令牌。
    
    返回:
    str - 加密后的令牌，使用base64编码表示。
    """
    tenant = db.session.query(Tenant).filter(Tenant.id == tenant_id).first()  # 根据租户ID查询租户信息
    encrypted_token = rsa.encrypt(token, tenant.encrypt_public_key)  # 使用RSA算法加密令牌
    return base64.b64encode(encrypted_token).decode()  # 对加密后的令牌进行base64编码

def decrypt_token(tenant_id: str, token: str):
    """
    对令牌进行解密，使用租户的私钥。
    
    参数:
    tenant_id: str - 租户的唯一标识符。
    token: str - 需要被解密的令牌，使用base64编码。
    
    返回:
    str - 解密后的令牌。
    """
    return rsa.decrypt(base64.b64decode(token), tenant_id)  # 使用租户的私钥解密令牌

def batch_decrypt_token(tenant_id: str, tokens: list[str]):
    """
    批量解密令牌，适用于处理大量令牌解密的场景。
    
    参数:
    tenant_id: str - 租户的唯一标识符。
    tokens: list[str] - 需要被解密的令牌列表，每个令牌使用base64编码。
    
    返回:
    list[str] - 解密后的令牌列表。
    """
    rsa_key, cipher_rsa = rsa.get_decrypt_decoding(tenant_id)  # 获取解密所需的密钥和加密算法

    return [rsa.decrypt_token_with_decoding(base64.b64decode(token), rsa_key, cipher_rsa) for token in tokens]  # 批量解密令牌

def get_decrypt_decoding(tenant_id: str):
    """
    获取解密所需的密钥和加密算法。
    
    参数:
    tenant_id: str - 租户的唯一标识符。
    
    返回:
    tuple - 包含解密密钥和加密算法的元组。
    """
    return rsa.get_decrypt_decoding(tenant_id)

def decrypt_token_with_decoding(token: str, rsa_key, cipher_rsa):
    """
    使用给定的密钥和加密算法解密令牌。
    
    参数:
    token: str - 需要被解密的令牌，使用base64编码。
    rsa_key: str - 解密所用的RSA密钥。
    cipher_rsa: str - 解密所用的加密算法。
    
    返回:
    str - 解密后的令牌。
    """
    return rsa.decrypt_token_with_decoding(base64.b64decode(token), rsa_key, cipher_rsa)  # 使用给定的密钥和算法解密令牌