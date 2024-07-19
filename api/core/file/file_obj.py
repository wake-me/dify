import enum
from typing import Optional

from pydantic import BaseModel

from core.app.app_config.entities import FileExtraConfig
from core.file.tool_file_parser import ToolFileParser
from core.file.upload_file_parser import UploadFileParser
from core.model_runtime.entities.message_entities import ImagePromptMessageContent
from extensions.ext_database import db
from models.model import UploadFile


class FileType(enum.Enum):
    """
    文件类型枚举类，定义了文件的基本类型。

    Attributes:
        IMAGE (str): 图片类型的枚举成员。
    """

    IMAGE = 'image'

    @staticmethod
    def value_of(value):
        """
        根据值获取枚举成员。

        Args:
            value (str): 需要获取的枚举成员的值。

        Returns:
            FileType: 与给定值匹配的枚举成员。

        Raises:
            ValueError: 如果没有找到与给定值匹配的枚举成员时抛出。
        """
        for member in FileType:
            if member.value == value:
                return member
        raise ValueError(f"No matching enum found for value '{value}'")

class FileTransferMethod(enum.Enum):
    """
    文件传输方法枚举类，定义了文件传输的不同方式。

    Attributes:
        REMOTE_URL (str): 通过远程URL传输的枚举成员。
        LOCAL_FILE (str): 通过本地文件传输的枚举成员。
        TOOL_FILE (str): 通过工具内部文件传输的枚举成员。
    """

    REMOTE_URL = 'remote_url'
    LOCAL_FILE = 'local_file'
    TOOL_FILE = 'tool_file'

    @staticmethod
    def value_of(value):
        """
        根据值获取枚举成员。

        Args:
            value (str): 需要获取的枚举成员的值。

        Returns:
            FileTransferMethod: 与给定值匹配的枚举成员。

        Raises:
            ValueError: 如果没有找到与给定值匹配的枚举成员时抛出。
        """
        for member in FileTransferMethod:
            if member.value == value:
                return member
        raise ValueError(f"No matching enum found for value '{value}'")

class FileBelongsTo(enum.Enum):
    """
    文件归属枚举类，定义了文件可能的归属。

    Attributes:
        USER (str): 归属于用户的枚举成员。
        ASSISTANT (str): 归属于助手的枚举成员。
    """

    USER = 'user'
    ASSISTANT = 'assistant'

    @staticmethod
    def value_of(value):
        """
        根据值获取枚举成员。

        Args:
            value (str): 需要获取的枚举成员的值。

        Returns:
            FileBelongsTo: 与给定值匹配的枚举成员。

        Raises:
            ValueError: 如果没有找到与给定值匹配的枚举成员时抛出。
        """
        for member in FileBelongsTo:
            if member.value == value:
                return member
        raise ValueError(f"No matching enum found for value '{value}'")

class FileVar(BaseModel):
    # 文件变量类，用于表示与文件相关的变量信息
    id: Optional[str] = None  # 消息文件ID
    tenant_id: str  # 租户ID
    type: FileType  # 文件类型
    transfer_method: FileTransferMethod  # 文件传输方法
    url: Optional[str] = None  # 远程URL
    related_id: Optional[str] = None  # 关联ID
    extra_config: Optional[FileExtraConfig] = None  # 额外配置
    filename: Optional[str] = None  # 文件名
    extension: Optional[str] = None  # 文件扩展名
    mime_type: Optional[str] = None  # MIME类型

    def to_dict(self) -> dict:
        """
        将文件变量信息转换为字典格式
        :return: 文件变量的字典表示
        """
        return {
            '__variant': self.__class__.__name__,
            'tenant_id': self.tenant_id,
            'type': self.type.value,
            'transfer_method': self.transfer_method.value,
            'url': self.preview_url,
            'remote_url': self.url,
            'related_id': self.related_id,
            'filename': self.filename,
            'extension': self.extension,
            'mime_type': self.mime_type,
        }

    def to_markdown(self) -> str:
        """
        将文件转换为Markdown格式的表示
        :return: 文件的Markdown格式字符串
        """
        preview_url = self.preview_url
        if self.type == FileType.IMAGE:
            text = f'![{self.filename or ""}]({preview_url})'
        else:
            text = f'[{self.filename or preview_url}]({preview_url})'

        return text

    @property
    def data(self) -> Optional[str]:
        """
        获取图片数据，根据配置MULTIMODAL_SEND_IMAGE_FORMAT返回文件的签名URL或Base64数据
        :return: 图片数据或文件签名URL
        """
        return self._get_data()

    @property
    def preview_url(self) -> Optional[str]:
        """
        获取签名的预览URL
        :return: 签名预览URL
        """
        return self._get_data(force_url=True)

    @property
    def prompt_message_content(self) -> ImagePromptMessageContent:
        """
        根据文件类型和配置，生成图片提示消息内容
        :return: 图片提示消息内容对象
        """
        if self.type == FileType.IMAGE:
            image_config = self.extra_config.image_config

            return ImagePromptMessageContent(
                data=self.data,
                detail=ImagePromptMessageContent.DETAIL.HIGH
                if image_config.get("detail") == "high" else ImagePromptMessageContent.DETAIL.LOW
            )

    def _get_data(self, force_url: bool = False) -> Optional[str]:
        """
        根据文件类型和传输方法获取文件数据，可能是远程URL或Base64编码的数据
        :param force_url: 是否强制获取URL
        :return: 文件数据或URL
        """
        if self.type == FileType.IMAGE:
            if self.transfer_method == FileTransferMethod.REMOTE_URL:
                return self.url
            elif self.transfer_method == FileTransferMethod.LOCAL_FILE:
                # 获取本地文件上传信息，并转换为图片数据
                upload_file = (db.session.query(UploadFile)
                               .filter(
                    UploadFile.id == self.related_id,
                    UploadFile.tenant_id == self.tenant_id
                ).first())

                return UploadFileParser.get_image_data(
                    upload_file=upload_file,
                    force_url=force_url
                )
            elif self.transfer_method == FileTransferMethod.TOOL_FILE:
                # 获取工具文件，并签名
                extension = self.extension
                return ToolFileParser.get_tool_file_manager().sign_file(tool_file_id=self.related_id, extension=extension)

        return None