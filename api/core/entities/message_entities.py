import enum
from typing import Any

from pydantic import BaseModel


class PromptMessageFileType(enum.Enum):
    """
    消息文件类型的枚举，定义了消息文件的不同类型。

    Attributes:
        IMAGE (str): 图片类型的标识。
    """

    IMAGE = 'image'

    @staticmethod
    def value_of(value):
        """
        根据值获取枚举成员。

        Args:
            value (str): 枚举成员的值。

        Returns:
            PromptMessageFileType: 与给定值匹配的枚举成员。

        Raises:
            ValueError: 如果没有找到与给定值匹配的枚举成员时抛出。
        """
        for member in PromptMessageFileType:
            if member.value == value:
                return member
        raise ValueError(f"No matching enum found for value '{value}'")

class PromptMessageFile(BaseModel):
    """
    消息文件的基础模型类，定义了消息文件的基本结构。

    Attributes:
        type (PromptMessageFileType): 消息文件的类型。
        data (Any): 消息文件的数据。
    """

    type: PromptMessageFileType
    data: Any = None

class ImagePromptMessageFile(PromptMessageFile):
    """
    图片类型消息文件的模型类，继承自PromptMessageFile，添加了图片详情的枚举。

    Attributes:
        type (PromptMessageFileType): 消息文件的类型，固定为图片类型。
        detail (DETAIL): 图片的详情级别。
    """

    class DETAIL(enum.Enum):
        """
        图片详情级别的枚举，定义了图片的不同详情级别。

        Attributes:
            LOW (str): 低详情级别。
            HIGH (str): 高详情级别。
        """
        LOW = 'low'
        HIGH = 'high'

    type: PromptMessageFileType = PromptMessageFileType.IMAGE
    detail: DETAIL = DETAIL.LOW
