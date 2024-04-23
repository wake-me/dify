from typing import Optional

from core.extension.extensible import ExtensionModule
from extensions.ext_code_based_extension import code_based_extension


class ExternalDataToolFactory:
    """
    外部数据工具工厂类，用于创建和管理外部数据工具的实例。

    :param name: 工具名称，字符串类型，用于指定外部数据工具的名称。
    :param tenant_id: 工作空间ID，字符串类型，标识工具所属的工作空间。
    :param app_id: 应用ID，字符串类型，用于唯一标识应用。
    :param variable: 变量，字符串类型，目前未使用的参数。
    :param config: 配置，字典类型，包含外部数据工具的配置信息。
    """

    def __init__(self, name: str, tenant_id: str, app_id: str, variable: str, config: dict) -> None:
        # 根据提供的工具名称获取扩展类，并实例化该扩展类
        extension_class = code_based_extension.extension_class(ExtensionModule.EXTERNAL_DATA_TOOL, name)
        self.__extension_instance = extension_class(
            tenant_id=tenant_id,
            app_id=app_id,
            variable=variable,
            config=config
        )

    @classmethod
    def validate_config(cls, name: str, tenant_id: str, config: dict) -> None:
        """
        验证传入的表单配置数据。

        :param name: 外部数据工具的名称。
        :param tenant_id: 工作空间的ID。
        :param config: 表单配置数据。
        :return: 无返回值，但会在数据验证不通过时抛出异常。
        """
        # 验证表单配置的数据结构是否符合指定的模式
        code_based_extension.validate_form_schema(ExtensionModule.EXTERNAL_DATA_TOOL, name, config)
        # 根据工具名称获取扩展类，并使用该类验证配置数据的具体内容
        extension_class = code_based_extension.extension_class(ExtensionModule.EXTERNAL_DATA_TOOL, name)
        extension_class.validate_config(tenant_id, config)

    def query(self, inputs: dict, query: Optional[str] = None) -> str:
        """
        查询外部数据工具。

        :param inputs: 用户输入的数据。
        :param query: 聊天应用的查询字符串，可选参数。
        :return: 工具的查询结果，字符串类型。
        """
        # 调用外部数据工具实例的查询方法，返回查询结果
        return self.__extension_instance.query(inputs, query)
