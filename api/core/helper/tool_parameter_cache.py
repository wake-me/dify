import json
from enum import Enum
from json import JSONDecodeError
from typing import Optional

from extensions.ext_redis import redis_client


class ToolParameterCacheType(Enum):
    # 工具参数缓存类型枚举
    PARAMETER = "tool_parameter"

class ToolParameterCache:
    def __init__(self, 
                 tenant_id: str,  # 租户ID
                 provider: str,  # 提供者名称
                 tool_name: str,  # 工具名称
                 cache_type: ToolParameterCacheType  # 缓存类型
        ):
        """
        初始化工具参数缓存对象。

        :param tenant_id: 租户ID，字符串类型。
        :param provider: 提供者名称，字符串类型。
        :param tool_name: 工具名称，字符串类型。
        :param cache_type: 工具参数缓存类型，ToolParameterCacheType枚举类型。
        """
        self.cache_key = f"{cache_type.value}_secret:tenant_id:{tenant_id}:provider:{provider}:tool_name:{tool_name}"

    def get(self) -> Optional[dict]:
        """
        获取缓存的模型提供者凭证。

        :return: 如果缓存中存在，则返回凭证字典；否则返回None。
        """
        cached_tool_parameter = redis_client.get(self.cache_key)
        if cached_tool_parameter:
            try:
                cached_tool_parameter = cached_tool_parameter.decode('utf-8')
                cached_tool_parameter = json.loads(cached_tool_parameter)
            except JSONDecodeError:
                return None  # 解码失败时返回None

            return cached_tool_parameter
        else:
            return None  # 未找到缓存时返回None

    def set(self, parameters: dict) -> None:
        """
        缓存模型提供者凭证。

        :param parameters: 提供者凭证，字典类型。
        :return: 无返回值。
        """
        redis_client.setex(self.cache_key, 86400, json.dumps(parameters))

    def delete(self) -> None:
        """
        删除缓存的模型提供者凭证。

        :return: 无返回值。
        """
        redis_client.delete(self.cache_key)