from extensions.ext_code_based_extension import code_based_extension


class CodeBasedExtensionService:
    @staticmethod
    def get_code_based_extension(module: str) -> list[dict]:
        """
        获取指定模块的非内置扩展信息列表。
        
        :param module: 字符串，表示模块的名称。
        :return: 返回一个列表，每个元素都是一个字典，包含扩展的名称、标签和表单架构信息。
        """
        # 从指定模块获取所有扩展信息
        module_extensions = code_based_extension.module_extensions(module)
        return [
            {
                "name": module_extension.name,
                "label": module_extension.label,
                "form_schema": module_extension.form_schema,
            }
            for module_extension in module_extensions
            if not module_extension.builtin
        ]
