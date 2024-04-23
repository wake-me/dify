from core.extension.extensible import ExtensionModule, ModuleExtension
from core.external_data_tool.base import ExternalDataTool
from core.moderation.base import Moderation


class Extension:
    # 类 Extension 用于管理模块扩展。
    
    __module_extensions: dict[str, dict[str, ModuleExtension]] = {}  # 私有变量，存储模块扩展的字典。

    module_classes = {
        ExtensionModule.MODERATION: Moderation,  # MODERATION模块对应的类是Moderation。
        ExtensionModule.EXTERNAL_DATA_TOOL: ExternalDataTool  # EXTERNAL_DATA_TOOL模块对应的类是ExternalDataTool。
    }

    def init(self):
        """
        初始化函数，扫描并加载所有模块的扩展。
        """
        for module, module_class in self.module_classes.items():
            self.__module_extensions[module.value] = module_class.scan_extensions()

    def module_extensions(self, module: str) -> list[ModuleExtension]:
        """
        获取指定模块的所有扩展。

        参数:
        module: str - 模块的标识符。

        返回值:
        list[ModuleExtension] - 模块的所有扩展列表。
        """
        module_extensions = self.__module_extensions.get(module)

        if not module_extensions:
            raise ValueError(f"Extension Module {module} not found")

        return list(module_extensions.values())

    def module_extension(self, module: ExtensionModule, extension_name: str) -> ModuleExtension:
        """
        获取指定模块的特定扩展。

        参数:
        module: ExtensionModule - 模块的枚举值。
        extension_name: str - 扩展的名称。

        返回值:
        ModuleExtension - 指定模块的特定扩展。
        """
        module_extensions = self.__module_extensions.get(module.value)

        if not module_extensions:
            raise ValueError(f"Extension Module {module} not found")

        module_extension = module_extensions.get(extension_name)

        if not module_extension:
            raise ValueError(f"Extension {extension_name} not found")

        return module_extension

    def extension_class(self, module: ExtensionModule, extension_name: str) -> type:
        """
        获取指定模块扩展的类。

        参数:
        module: ExtensionModule - 模块的枚举值。
        extension_name: str - 扩展的名称。

        返回值:
        type - 指定模块扩展的类类型。
        """
        module_extension = self.module_extension(module, extension_name)
        return module_extension.extension_class

    def validate_form_schema(self, module: ExtensionModule, extension_name: str, config: dict) -> None:
        """
        验证指定模块扩展的表单架构。

        参数:
        module: ExtensionModule - 模块的枚举值。
        extension_name: str - 扩展的名称。
        config: dict - 配置字典，用于验证表单架构。

        返回值:
        None
        """
        module_extension = self.module_extension(module, extension_name)
        form_schema = module_extension.form_schema

        # TODO: 进行表单架构验证