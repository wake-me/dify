from decimal import Decimal

from pydantic import BaseModel

from core.model_runtime.entities.model_entities import ModelUsage


class EmbeddingUsage(ModelUsage):
    """
    模型类，用于表示嵌入使用的相关信息。
    
    属性:
    tokens: int - 已使用的令牌数。
    total_tokens: int - 总令牌数。
    unit_price: Decimal - 单价（每个令牌的价格）。
    price_unit: Decimal - 价格单位。
    total_price: Decimal - 总价格。
    currency: str - 货币单位。
    latency: float - 延迟时间（秒）。
    """
    tokens: int
    total_tokens: int
    unit_price: Decimal
    price_unit: Decimal
    total_price: Decimal
    currency: str
    latency: float

class TextEmbeddingResult(BaseModel):
    """
    模型类，用于表示文本嵌入的结果信息。
    
    属性:
    model: str - 使用的模型名称。
    embeddings: list[list[float]] - 嵌入向量的列表，每个嵌入向量是一个浮点数列表。
    usage: EmbeddingUsage - 嵌入使用情况的详细信息。
    """
    model: str
    embeddings: list[list[float]]
    usage: EmbeddingUsage
