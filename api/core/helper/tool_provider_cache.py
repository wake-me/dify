import json
from enum import Enum
from json import JSONDecodeError
from typing import Optional

from extensions.ext_redis import redis_client


class ToolProviderCredentialsCacheType(Enum):
    # 工具提供商凭证缓存类型
    PROVIDER = "tool_provider"

class ToolProviderCredentialsCache:
    def __init__(self, tenant_id: str, identity_id: str, cache_type: ToolProviderCredentialsCacheType):
        """
        初始化工具提供商凭证缓存对象。

        :param tenant_id: 租户ID，字符串类型。
        :param identity_id: 身份ID，字符串类型。
        :param cache_type: 缓存类型，ToolProviderCredentialsCacheType枚举。
        """
        self.cache_key = f"{cache_type.value}_credentials:tenant_id:{tenant_id}:id:{identity_id}"

    def get(self) -> Optional[dict]:
        """
        获取缓存的模型提供商凭证。

        :return: 如果存在，返回凭证字典；否则返回None。
        """
        cached_provider_credentials = redis_client.get(self.cache_key)
        if cached_provider_credentials:
            try:
                cached_provider_credentials = cached_provider_credentials.decode('utf-8')
                cached_provider_credentials = json.loads(cached_provider_credentials)
            except JSONDecodeError:
                return None  # 解析失败时返回None

            return cached_provider_credentials
        else:
            return None  # 未找到缓存时返回None

    def set(self, credentials: dict) -> None:
        """
        缓存模型提供商凭证。

        :param credentials: 提供商凭证，字典类型。
        """
        redis_client.setex(self.cache_key, 86400, json.dumps(credentials))

    def delete(self) -> None:
        """
        删除缓存的模型提供商凭证。

        :return: 无返回值。
        """
        redis_client.delete(self.cache_key)