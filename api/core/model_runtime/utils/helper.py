import pydantic
from pydantic import BaseModel


def dump_model(model: BaseModel) -> dict:
    """
    将 Pydantic 模型实例转换为字典形式。
    
    参数:
    - model: BaseModel 类型，待转换的 Pydantic 模型实例。
    
    返回值:
    - dict: 转换后得到的字典，包含模型的所有字段和值。
    """
    if hasattr(pydantic, 'model_dump'):
        # 如果 pydantic 库支持 model_dump 方法，则使用该方法转换模型
        return pydantic.model_dump(model)
    else:
        # 否则，回退到使用模型的 dict 方法进行转换
        return model.dict()