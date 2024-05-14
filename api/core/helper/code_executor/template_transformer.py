from abc import ABC, abstractmethod
from typing import Optional

from core.helper.code_executor.entities import CodeDependency


class TemplateTransformer(ABC):
    """
    模板转换器的基类，用于定义代码转换的通用接口。
    """
    
    @classmethod
    @abstractmethod
    def transform_caller(cls, code: str, inputs: dict, 
                         dependencies: Optional[list[CodeDependency]] = None) -> tuple[str, str, list[CodeDependency]]:
        """
        将代码转换为Python运行器可以执行的形式。
        
        :param code: 需要转换的代码字符串。
        :param inputs: 代码执行时所需的输入字典。
        :return: 返回一个元组，包含运行器代码和预加载代码。
        """
        pass
    
    @classmethod
    @abstractmethod
    def transform_response(cls, response: str) -> dict:
        """
        将响应字符串转换为字典格式。
        
        :param response: 从运行器接收的响应字符串。
        :return: 返回一个基于响应字符串解析后的字典。
        """
        pass