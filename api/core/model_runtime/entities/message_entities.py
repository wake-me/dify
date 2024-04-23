from abc import ABC
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class PromptMessageRole(Enum):
    """
    提示消息角色枚举类。
    """
    SYSTEM = "system"    # 系统发出的消息
    USER = "user"        # 用户发出的消息
    ASSISTANT = "assistant"    # 助手发出的消息
    TOOL = "tool"        # 工具发出的消息

    @classmethod
    def value_of(cls, value: str) -> 'PromptMessageRole':
        """
        根据给定的值获取相应的枚举成员。

        :param value: 枚举成员的值
        :return: 对应的枚举成员
        """
        for mode in cls:
            if mode.value == value:
                return mode
        # 如果给定的值不存在于枚举中，则抛出异常
        raise ValueError(f'invalid prompt message type value {value}')

class PromptMessageTool(BaseModel):
    """
    提示消息工具模型类。
    用于定义一个提示消息工具，包括工具的名称、描述和参数。
    
    属性:
    - name: 工具的名称，类型为str。
    - description: 工具的描述，类型为str。
    - parameters: 工具的参数，类型为dict。
    """
    name: str
    description: str
    parameters: dict

class PromptMessageFunction(BaseModel):
    """
    提示消息函数模型类。
    用于定义一个提示消息函数，包括函数的类型和函数对象。
    
    属性:
    - type: 函数的类型， 默认为'function'，类型为str。
    - function: 函数对象，类型为PromptMessageTool。
    """
    type: str = 'function'
    function: PromptMessageTool

class PromptMessageContentType(Enum):
    """
    提示消息内容类型的枚举类。
    定义了提示消息的内容类型，包括文本和图片。
    
    成员:
    - TEXT: 表示文本类型的提示消息。
    - IMAGE: 表示图片类型的提示消息。
    """
    TEXT = 'text'
    IMAGE = 'image'

class PromptMessageContent(BaseModel):
    """
    提示消息内容模型类。
    用于定义一个提示消息的内容，包括内容的类型和数据。
    
    属性:
    - type: 内容的类型，类型为PromptMessageContentType枚举。
    - data: 内容的数据，类型为str。
    """
    type: PromptMessageContentType
    data: str

class TextPromptMessageContent(PromptMessageContent):
    """
    文本提示消息内容的模型类。
    """
    type: PromptMessageContentType = PromptMessageContentType.TEXT

class ImagePromptMessageContent(PromptMessageContent):
    """
    图片提示消息内容的模型类。
    """
    class DETAIL(Enum):
        """
        图片详情枚举，定义图片的详细程度。
        """
        LOW = 'low'    # 低详细度
        HIGH = 'high'  # 高详细度

    type: PromptMessageContentType = PromptMessageContentType.IMAGE
    detail: DETAIL = DETAIL.LOW  # 默认为低详细度


class PromptMessage(ABC, BaseModel):
    """
    提示消息的模型类。
    """
    role: PromptMessageRole  # 消息角色
    content: Optional[str | list[PromptMessageContent]] = None  # 消息内容，可以是字符串或内容列表
    name: Optional[str] = None  # 消息名称

    def is_empty(self) -> bool:
        """
        检查提示消息是否为空。

        :return: 如果提示消息为空则返回True，否则返回False。
        """
        return not self.content


class UserPromptMessage(PromptMessage):
    """
    用户提示消息的模型类。
    """
    role: PromptMessageRole = PromptMessageRole.USER  # 默认角色为用户


class AssistantPromptMessage(PromptMessage):
    """
    助理提示消息的模型类。
    """
    class ToolCall(BaseModel):
        """
        助理提示消息中工具调用的模型类。
        """
        class ToolCallFunction(BaseModel):
            """
            助理提示消息中工具调用函数的模型类。
            """
            name: str  # 函数名称
            arguments: str  # 函数参数

        id: str  # 工具调用的唯一标识
        type: str  # 工具调用的类型
        function: ToolCallFunction  # 工具调用的函数信息

    role: PromptMessageRole = PromptMessageRole.ASSISTANT  # 消息角色，默认为助理
    tool_calls: list[ToolCall] = []  # 工具调用列表

    def is_empty(self) -> bool:
        """
        检查提示消息是否为空。

        :return: 如果提示消息为空则返回True，否则返回False。
        """
        if not super().is_empty() and not self.tool_calls:
            return False  # 如果基类提示消息不为空且工具调用列表为空，则消息不为空

        return True  # 否则消息为空

class SystemPromptMessage(PromptMessage):
    """
    系统提示消息的模型类。
    """
    role: PromptMessageRole = PromptMessageRole.SYSTEM  # 消息角色，默认为系统角色

class ToolPromptMessage(PromptMessage):
    """
    工具提示消息的模型类。
    """
    role: PromptMessageRole = PromptMessageRole.TOOL  # 消息角色，默认为工具角色
    tool_call_id: str  # 工具调用的ID

    def is_empty(self) -> bool:
        """
        检查提示消息是否为空。

        :return: 如果提示消息为空则返回True，否则返回False。
        """
        # 首先检查父类是否为空，然后检查tool_call_id是否为空
        if not super().is_empty() and not self.tool_call_id:
            return False

        return True
