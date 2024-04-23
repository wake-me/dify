from typing import Optional

from pydantic import BaseModel


class I18nObject(BaseModel):
    """
    I18n对象的模型类，用于表示具有国际化属性的对象。
    
    参数:
    - zh_Hans: 中文（简体）版本的字符串。可选参数，默认为None。
    - en_US: 英文（美国）版本的字符串。必需参数。
    
    返回值:
    - 无
    """
    zh_Hans: Optional[str] = None  # 中文（简体）属性
    en_US: str  # 英文（美国）属性

    def __init__(self, **data):
        super().__init__(**data)  # 调用父类构造函数初始化属性
        if not self.zh_Hans:  # 如果没有提供中文（简体）属性，则将其设置为英文（美国）属性的值
            self.zh_Hans = self.en_US