from enum import Enum


class DatasourceType(Enum):
    """
    数据源类型枚举类，定义了数据源的类型。

    参数:
    无

    返回值:
    无
    """

    FILE = "upload_file"  # 表示文件类型数据源
    NOTION = "notion_import"  # 表示Notion类型数据源