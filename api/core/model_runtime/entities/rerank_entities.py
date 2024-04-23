from pydantic import BaseModel


class RerankDocument(BaseModel):
    """
    重排文档的模型类。
    
    参数:
    - index: int，文档的索引号。
    - text: str，文档的文本内容。
    - score: float，文档的评分。
    """
    index: int
    text: str
    score: float


class RerankResult(BaseModel):
    """
    重排结果的模型类。
    
    参数:
    - model: str，使用的重排模型名称。
    - docs: list[RerankDocument]，重排后的文档列表。
    """
    model: str
    docs: list[RerankDocument]