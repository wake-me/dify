from extensions.ext_code_based_extension import code_based_extension


class CodeBasedExtensionService:
    """
    代码驱动的扩展服务类，用于获取基于代码的模块扩展信息。
    """
    
    @staticmethod
    def get_code_based_extension(module: str) -> list[dict]:
        """
        获取指定模块的非内置扩展信息列表。
        
        :param module: 字符串，表示模块的名称。
        :return: 返回一个列表，每个元素都是一个字典，包含扩展的名称、标签和表单架构信息。
        """
        # 从指定模块获取所有扩展信息
        module_extensions = code_based_extension.module_extensions(module)
        
        # 筛选出非内置扩展，并组装成指定格式的列表返回
        return [{
            'name': module_extension.name,  # 扩展名称
            'label': module_extension.label,  # 扩展标签
            'form_schema': module_extension.form_schema  # 扩展表单架构
        } for module_extension in module_extensions if not module_extension.builtin]
