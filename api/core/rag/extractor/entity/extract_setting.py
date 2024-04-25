from pydantic import BaseModel

from models.dataset import Document
from models.model import UploadFile


class NotionInfo(BaseModel):
    """
    Notion导入信息类。
    
    用于存储从Notion导入的相关信息，包括工作区ID、对象ID、页面类型和文档信息。
    """

    notion_workspace_id: str  # Notion工作区ID
    notion_obj_id: str  # Notion对象ID
    notion_page_type: str  # Notion页面类型
    document: Document = None  # 关联的文档对象
    tenant_id: str  # 租户ID

    class Config:
        arbitrary_types_allowed = True  # 允许任意类型的数据

    def __init__(self, **data) -> None:
        """
        初始化NotionInfo实例。
        
        :param **data: 包含Notion信息的数据字典。
        """
        super().__init__(**data)


class ExtractSetting(BaseModel):
    """
    提取设置模型类。
    
    用于存储数据提取相关的设置信息，包括数据源类型、上传文件和Notion信息。
    """

    datasource_type: str  # 数据源类型
    upload_file: UploadFile = None  # 上传的文件
    notion_info: NotionInfo = None  # Notion信息
    document_model: str = None  # 文档模型

    class Config:
        arbitrary_types_allowed = True  # 允许任意类型的数据

    def __init__(self, **data) -> None:
        """
        初始化ExtractSetting实例。
        
        :param **data: 包含提取设置的数据字典。
        """
        super().__init__(**data)