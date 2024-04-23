from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel

from core.model_runtime.entities.message_entities import AssistantPromptMessage, PromptMessage
from core.model_runtime.entities.model_entities import ModelUsage, PriceInfo


class LLMMode(Enum):
    """
    大语言模型模式的枚举类。
    """

    COMPLETION = "completion"  # 提供完成或生成文本的模式
    CHAT = "chat"  # 提供聊天或对话的模式

    @classmethod
    def value_of(cls, value: str) -> 'LLMMode':
        """
        根据给定的值获取对应的模式。

        :param value: 模式的值，字符串类型。
        :return: 对应的模式枚举实例。
        """
        for mode in cls:
            if mode.value == value:  # 查找并返回与给定值匹配的模式
                return mode
        raise ValueError(f'invalid mode value {value}')


class LLMUsage(ModelUsage):
    """
    LLMUsage 类用于定义 llm（可能指 Large Language Model）的使用情况。
    继承自 ModelUsage 类。
    """
    
    # 定义类属性，包括提示令牌数、提示单位价格、提示价格单位、提示价格、完成令牌数、完成单位价格、完成价格单位、完成价格、总令牌数、总价格、货币单位和延迟。
    prompt_tokens: int
    prompt_unit_price: Decimal
    prompt_price_unit: Decimal
    prompt_price: Decimal
    completion_tokens: int
    completion_unit_price: Decimal
    completion_price_unit: Decimal
    completion_price: Decimal
    total_tokens: int
    total_price: Decimal
    currency: str
    latency: float

    @classmethod
    def empty_usage(cls):
        """
        创建一个空的 LLMUsage 实例，所有使用情况的数值都被设置为默认值。
        
        参数:
        无
        
        返回值:
        LLMUsage: 一个初始化为默认值的 LLMUsage 类实例。
        """
        return cls(
            prompt_tokens=0,  # 提示令牌数默认为0
            prompt_unit_price=Decimal('0.0'),  # 提示单位价格默认为0
            prompt_price_unit=Decimal('0.0'),  # 提示价格单位默认为0
            prompt_price=Decimal('0.0'),  # 提示价格默认为0
            completion_tokens=0,  # 完成令牌数默认为0
            completion_unit_price=Decimal('0.0'),  # 完成单位价格默认为0
            completion_price_unit=Decimal('0.0'),  # 完成价格单位默认为0
            completion_price=Decimal('0.0'),  # 完成价格默认为0
            total_tokens=0,  # 总令牌数默认为0
            total_price=Decimal('0.0'),  # 总价格默认为0
            currency='USD',  # 货币单位默认为美元
            latency=0.0  # 延迟默认为0
        )


class LLMResult(BaseModel):
    """
    LLM结果的模型类。
    该类封装了与语言模型（LLM）查询结果相关的信息。
    
    属性:
    - model: 使用的模型名称。
    - prompt_messages: 提示信息列表，包含了与用户交互的多次提示。
    - message: 助手的提示消息，为最后一次交互的消息。
    - usage: LLm的使用信息，记录了模型的使用情况。
    - system_fingerprint: 系统指纹信息，可选字段，用于识别系统状态。
    """
    model: str
    prompt_messages: list[PromptMessage]
    message: AssistantPromptMessage
    usage: LLMUsage
    system_fingerprint: Optional[str] = None


class LLMResultChunkDelta(BaseModel):
    """
    LLM结果片段增量的模型类。
    用于表示LLM结果在一个特定片段中的增量变化。
    
    属性:
    - index: 增量片段的索引。
    - message: 助手的提示消息，表示该增量片段的内容。
    - usage: 该增量片段的使用信息，可选字段。
    - finish_reason: 完成原因，表明为什么这个增量片段是最后的或者是因为特定原因结束的，可选字段。
    """
    index: int
    message: AssistantPromptMessage
    usage: Optional[LLMUsage] = None
    finish_reason: Optional[str] = None


class LLMResultChunk(BaseModel):
    """
    LLM结果片段的模型类。
    用于分块处理大型LLM结果，每个片段包含一部分结果数据。
    
    属性:
    - model: 使用的模型名称。
    - prompt_messages: 提示信息列表，针对该结果片段的交互提示。
    - system_fingerprint: 系统指纹信息，可选字段，用于识别在处理该结果片段时的系统状态。
    - delta: 该结果片段相对于前一个片段的增量信息。
    """
    model: str
    prompt_messages: list[PromptMessage]
    system_fingerprint: Optional[str] = None
    delta: LLMResultChunkDelta


class NumTokensResult(PriceInfo):
    """
    计算token数量结果的模型类。
    用于记录和传递关于token数量计算的结果。
    
    属性:
    - tokens: 计算得出的token数量。
    """
    tokens: int
