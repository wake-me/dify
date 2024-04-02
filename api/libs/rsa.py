import hashlib

from Crypto.Cipher import AES
from Crypto.PublicKey import RSA
from Crypto.Random import get_random_bytes

import libs.gmpy2_pkcs10aep_cipher as gmpy2_pkcs10aep_cipher
from extensions.ext_redis import redis_client
from extensions.ext_storage import storage


def generate_key_pair(tenant_id):
    """
    为指定的租户生成RSA密钥对，并存储私钥，返回公钥。
    
    参数:
    tenant_id : str
        租户的唯一标识符，用于为租户生成和存储私钥文件。
        
    返回:
    str
        生成的公钥，以PEM格式编码的字符串。
    """
    # 生成2048位的RSA私钥
    private_key = RSA.generate(2048)
    # 从私钥中提取公钥
    public_key = private_key.publickey()

    # 导出私钥和公钥为PEM格式
    pem_private = private_key.export_key()
    pem_public = public_key.export_key()

    # 拼接私钥文件的存储路径
    filepath = "privkeys/{tenant_id}".format(tenant_id=tenant_id) + "/private.pem"

    # 存储私钥到指定路径
    storage.save(filepath, pem_private)

    # 返回公钥，确保返回的是字符串格式
    return pem_public.decode()


prefix_hybrid = b"HYBRID:"


def encrypt(text, public_key):
    """
    使用混合加密方式对文本进行加密。
    
    参数:
    text: 需要加密的文本，字符串类型。
    public_key: 公钥，用于最终的RSA加密，可以是字符串或bytes类型。
    
    返回值:
    返回加密后的数据，为前缀加密数据的组合。
    """
    # 如果公钥是字符串，将其转换为bytes类型
    if isinstance(public_key, str):
        public_key = public_key.encode()

    # 生成随机的AES密钥
    aes_key = get_random_bytes(16)
    # 使用AES密钥初始化加密器
    cipher_aes = AES.new(aes_key, AES.MODE_EAX)

    # 使用AES加密文本并生成消息认证码
    ciphertext, tag = cipher_aes.encrypt_and_digest(text.encode())

    # 导入RSA公钥
    rsa_key = RSA.import_key(public_key)
    # 初始化RSA加密器
    cipher_rsa = gmpy2_pkcs10aep_cipher.new(rsa_key)

    # 使用RSA加密AES密钥
    enc_aes_key = cipher_rsa.encrypt(aes_key)

    # 组合加密后的数据，包括RSA加密的AES密钥、AES的nonce、消息认证码和加密文本
    encrypted_data = enc_aes_key + cipher_aes.nonce + tag + ciphertext

    # 添加前缀后返回加密数据
    return prefix_hybrid + encrypted_data


def get_decrypt_decoding(tenant_id):
    """
    获取解密密钥和解密器
    参数:
        tenant_id (str): 租户ID，用于构建私钥文件路径和缓存键
    返回:
        tuple: 包含RSA密钥对象和RSA加密器对象的元组
    抛出:
        PrivkeyNotFoundError: 如果私钥文件不存在，则抛出此异常
    """
    # 构建私钥文件路径
    filepath = "privkeys/{tenant_id}".format(tenant_id=tenant_id) + "/private.pem"

    # 构造缓存键，并尝试从Redis获取私钥
    cache_key = 'tenant_privkey:{hash}'.format(hash=hashlib.sha3_256(filepath.encode()).hexdigest())
    private_key = redis_client.get(cache_key)
    if not private_key:
        # 如果私钥不在缓存中，则从文件系统加载
        try:
            private_key = storage.load(filepath)
        except FileNotFoundError:
            # 如果文件系统中也找不到私钥，抛出异常
            raise PrivkeyNotFoundError("Private key not found, tenant_id: {tenant_id}".format(tenant_id=tenant_id))

        # 将加载的私钥存入Redis缓存，设置过期时间为120秒
        redis_client.setex(cache_key, 120, private_key)

    # 导入私钥为RSA密钥对象，并创建RSA加密器
    rsa_key = RSA.import_key(private_key)
    cipher_rsa = gmpy2_pkcs10aep_cipher.new(rsa_key)

    return rsa_key, cipher_rsa


def decrypt_token_with_decoding(encrypted_text, rsa_key, cipher_rsa):
    """
    使用RSA解密令牌文本。
    如果令牌文本以特定前缀开始，则采用Hybrid加密方式解密；否则，直接使用RSA解密。
    
    :param encrypted_text: 被加密的文本字符串。
    :param rsa_key: 用于解密的RSA密钥。
    :param cipher_rsa: 实现RSA加密解密操作的对象。
    :return: 解密后的文本字符串。
    """
    if encrypted_text.startswith(prefix_hybrid):  # 检查是否使用Hybrid加密方式
        encrypted_text = encrypted_text[len(prefix_hybrid):]  # 移除前缀

        # 分解加密后的文本，获取AES密钥、nonce、tag和密文
        enc_aes_key = encrypted_text[:rsa_key.size_in_bytes()]
        nonce = encrypted_text[rsa_key.size_in_bytes():rsa_key.size_in_bytes() + 16]
        tag = encrypted_text[rsa_key.size_in_bytes() + 16:rsa_key.size_in_bytes() + 32]
        ciphertext = encrypted_text[rsa_key.size_in_bytes() + 32:]

        # 使用RSA解密AES密钥
        aes_key = cipher_rsa.decrypt(enc_aes_key)

        # 使用AES解密密文，并验证完整性
        cipher_aes = AES.new(aes_key, AES.MODE_EAX, nonce=nonce)
        decrypted_text = cipher_aes.decrypt_and_verify(ciphertext, tag)
    else:
        # 直接使用RSA解密
        decrypted_text = cipher_rsa.decrypt(encrypted_text)

    # 将解密后的字节字符串转换为普通字符串并返回
    return decrypted_text.decode()


def decrypt(encrypted_text, tenant_id):
    """
    解密给定的加密文本。
    
    参数:
    encrypted_text: str - 需要解密的文本。
    tenant_id: str - 租户标识，用于获取对应的解密密钥。
    
    返回:
    解密后的文本。
    """
    # 根据租户ID获取解密所需的RSA密钥和解码器
    rsa_key, cipher_rsa = get_decrypt_decoding(tenant_id)

    # 使用获取的RSA密钥和解码器解密文本
    return decrypt_token_with_decoding(encrypted_text, rsa_key, cipher_rsa)


class PrivkeyNotFoundError(Exception):
    pass
