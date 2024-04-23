# 工具文件管理器的配置字典
tool_file_manager = {
    'manager': None
}

class ToolFileParser:
    """
    工具文件解析器类，用于获取工具文件管理器的实例。
    """
    
    @staticmethod
    def get_tool_file_manager() -> 'ToolFileManager':
        """
        获取工具文件管理器的静态方法。

        返回:
            返回工具文件管理器的实例。
        """
        return tool_file_manager['manager']