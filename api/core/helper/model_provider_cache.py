import json
from enum import Enum
from json import JSONDecodeError
from typing import Optional

from extensions.ext_redis import redis_client


class ProviderCredentialsCacheType(Enum):
    # 提供者凭证缓存类型枚举
    PROVIDER = "provider"  # 提供者级别缓存
    MODEL = "provider_model"  # 提供者模型级别缓存


class ProviderCredentialsCache:
    def __init__(self, tenant_id: str, identity_id: str, cache_type: ProviderCredentialsCacheType):
        """
        初始化提供者凭证缓存对象。

        :param tenant_id: 租户ID，字符串类型，用于标识缓存的租户。
        :param identity_id: 身份ID，字符串类型，用于标识缓存的身份。
        :param cache_type: 缓存类型，ProviderCredentialsCacheType枚举，指定是提供者级别还是提供者模型级别缓存。
        """
        self.cache_key = f"{cache_type.value}_credentials:tenant_id:{tenant_id}:id:{identity_id}"

    def get(self) -> Optional[dict]:
        """
        获取缓存的模型提供者凭证。

        :return: 如果缓存中存在凭证，则返回凭证字典；否则返回None。
        """
        cached_provider_credentials = redis_client.get(self.cache_key)
        if cached_provider_credentials:
            try:
                cached_provider_credentials = cached_provider_credentials.decode('utf-8')
                cached_provider_credentials = json.loads(cached_provider_credentials)
            except JSONDecodeError:
                return None  # 解码失败时返回None

            return cached_provider_credentials
        else:
            return None  # 未找到缓存时返回None

    def set(self, credentials: dict) -> None:
        """
        缓存模型提供者凭证。

        :param credentials: 提供者凭证，字典类型，需要被缓存的凭证信息。
        :return: 无返回值。
        """
        redis_client.setex(self.cache_key, 86400, json.dumps(credentials))

    def delete(self) -> None:
        """
        删除缓存的模型提供者凭证。

        :return: 无返回值。
        """
        redis_client.delete(self.cache_key)