from typing import Optional

from pydantic import BaseModel, ConfigDict

from models.dataset import Document
from models.model import UploadFile


class NotionInfo(BaseModel):
    """
    Notion导入信息类。
    
    用于存储从Notion导入的相关信息，包括工作区ID、对象ID、页面类型和文档信息。
    """
    notion_workspace_id: str
    notion_obj_id: str
    notion_page_type: str
    document: Document = None
    tenant_id: str
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __init__(self, **data) -> None:
        super().__init__(**data)


class WebsiteInfo(BaseModel):
    """
    website import info.
    """
    provider: str
    job_id: str
    url: str
    mode: str
    tenant_id: str
    only_main_content: bool = False

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
    datasource_type: str
    upload_file: Optional[UploadFile] = None
    notion_info: Optional[NotionInfo] = None
    website_info: Optional[WebsiteInfo] = None
    document_model: Optional[str] = None
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __init__(self, **data) -> None:
        """
        初始化ExtractSetting实例。
        
        :param **data: 包含提取设置的数据字典。
        """
        super().__init__(**data)