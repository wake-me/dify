from abc import ABC, abstractmethod
from typing import Optional

from core.extension.extensible import Extensible, ExtensionModule


class ExternalDataTool(Extensible, ABC):
    """
    外部数据工具的基类。
    
    参数:
    - module: ExtensionModule 类型，表示扩展模块，此处限定为 EXTERNAL_DATA_TOOL。
    
    属性:
    - app_id: str 类型，应用的ID。
    - variable: str 类型，应用工具的变量名。
    """

    module: ExtensionModule = ExtensionModule.EXTERNAL_DATA_TOOL

    app_id: str
    """应用的ID"""
    variable: str
    """应用工具的变量名"""

    def __init__(self, tenant_id: str, app_id: str, variable: str, config: Optional[dict] = None) -> None:
        """
        初始化外部数据工具实例。
        
        参数:
        - tenant_id: str 类型，租户ID。
        - app_id: str 类型，应用的ID。
        - variable: str 类型，应用工具的变量名。
        - config: Optional[dict] 类型，配置信息，可选。
        """
        super().__init__(tenant_id, config)
        self.app_id = app_id
        self.variable = variable

    @classmethod
    @abstractmethod
    def validate_config(cls, tenant_id: str, config: dict) -> None:
        """
        验证传入的表单配置数据。

        :param cls: 表示类的占位参数，此处应为类的名称，用于实现时指定验证逻辑所在的类
        :param tenant_id: 工作空间的id，用于指定表单配置所属的工作空间
        :param config: 表单的配置数据，需要进行验证的字典数据
        :return: 无返回值
        """
        raise NotImplementedError

    @abstractmethod
    def query(self, inputs: dict, query: Optional[str] = None) -> str:
        """
        查询外部数据工具。

        :param inputs: 用户输入
        :param query: 聊天应用的查询内容，可选
        :return: 工具查询结果
        """
        raise NotImplementedError
