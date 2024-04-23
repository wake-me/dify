from collections import OrderedDict
from typing import Any


class LRUCache:
    """
    实现一个最近最少使用（LRU）缓存机制的类。
    
    参数:
    - capacity: int，缓存的最大容量。
    
    方法:
    - get(key): 获取给定键的值。如果键不存在，返回None。
    - put(key, value): 将键值对存储到缓存中。如果键已存在，则更新其对应的值。当缓存容量被超过时，移除最近最少使用的项目。
    """
    def __init__(self, capacity: int):
        self.cache = OrderedDict()  # 使用有序字典存储缓存，确保访问顺序与插入顺序一致
        self.capacity = capacity

    def get(self, key: Any) -> Any:
        """
        获取给定键的值。
        
        参数:
        - key: Any，要获取值的键。
        
        返回:
        - Any，与键关联的值，如果键不存在则返回None。
        """
        if key not in self.cache:
            return None
        else:
            self.cache.move_to_end(key)  # 将键移动到有序字典的末尾，表示最近使用
            return self.cache[key]

    def put(self, key: Any, value: Any) -> None:
        """
        将键值对存储到缓存中。
        
        参数:
        - key: Any，要存储的键。
        - value: Any，要存储的值。
        """
        if key in self.cache:
            self.cache.move_to_end(key)  # 如果键已存在，则将其移动到末尾，表示最近使用
        self.cache[key] = value  # 存储键值对
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)  # 如果缓存容量超过限制，则移除最早插入的项目