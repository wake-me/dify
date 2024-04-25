from enum import Enum


class IndexType(Enum):
    """
    索引类型枚举类，用于定义不同的索引类型。
    
    属性:
    - PARAGRAPH_INDEX: 段落索引类型，使用"text_model"作为标识。
    - QA_INDEX: 问题回答索引类型，使用"qa_model"作为标识。
    - PARENT_CHILD_INDEX: 父子关系索引类型，使用"parent_child_index"作为标识。
    - SUMMARY_INDEX: 摘要索引类型，使用"summary_index"作为标识。
    """
    PARAGRAPH_INDEX = "text_model"  # 段落索引
    QA_INDEX = "qa_model"  # 问题回答索引
    PARENT_CHILD_INDEX = "parent_child_index"  # 父子关系索引
    SUMMARY_INDEX = "summary_index"  # 摘要索引