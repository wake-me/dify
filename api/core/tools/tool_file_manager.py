import base64
import hashlib
import hmac
import logging
import os
import time
from collections.abc import Generator
from mimetypes import guess_extension, guess_type
from typing import Optional, Union
from uuid import uuid4

from flask import current_app
from httpx import get

from extensions.ext_database import db
from extensions.ext_storage import storage
from models.model import MessageFile
from models.tools import ToolFile

logger = logging.getLogger(__name__)


class ToolFileManager:
    @staticmethod
    def sign_file(tool_file_id: str, extension: str) -> str:
        """
        对文件进行签名，以获取一个临时URL。
        
        参数:
        - tool_file_id: str - 工具文件的ID
        - extension: str - 文件的扩展名
        
        返回值:
        - str: 签名后的文件预览URL
        """
        # 获取基础URL
        base_url = current_app.config.get('FILES_URL')
        # 构建文件预览URL
        file_preview_url = f'{base_url}/files/tools/{tool_file_id}{extension}'

        # 生成时间戳
        timestamp = str(int(time.time()))
        # 生成随机数
        nonce = os.urandom(16).hex()
        # 准备待签名的数据
        data_to_sign = f"file-preview|{tool_file_id}|{timestamp}|{nonce}"
        # 获取密钥
        secret_key = current_app.config['SECRET_KEY'].encode()
        # 计算签名
        sign = hmac.new(secret_key, data_to_sign.encode(), hashlib.sha256).digest()
        # 对签名进行编码
        encoded_sign = base64.urlsafe_b64encode(sign).decode()

        # 返回带签名的文件预览URL
        return f"{file_preview_url}?timestamp={timestamp}&nonce={nonce}&sign={encoded_sign}"

    @staticmethod
    def verify_file(file_id: str, timestamp: str, nonce: str, sign: str) -> bool:
        """
        验证文件签名的有效性。

        参数:
        - file_id: 文件的唯一标识符。
        - timestamp: 签名时的时间戳。
        - nonce: 签名时的随机数，用于防止重放攻击。
        - sign: 文件签名，用于验证数据的完整性。

        返回值:
        - 返回一个布尔值，True表示签名验证通过，False表示验证失败。
        """
        # 构造待签名字符串
        data_to_sign = f"file-preview|{file_id}|{timestamp}|{nonce}"
        # 获取应用的密钥
        secret_key = current_app.config['SECRET_KEY'].encode()
        # 计算签名
        recalculated_sign = hmac.new(secret_key, data_to_sign.encode(), hashlib.sha256).digest()
        # 对计算得到的签名进行Base64编码
        recalculated_encoded_sign = base64.urlsafe_b64encode(recalculated_sign).decode()

        # 验证签名是否匹配
        if sign != recalculated_encoded_sign:
            return False

        # 检查时间戳是否过期，过期时间为5分钟
        current_time = int(time.time())
        return current_time - int(timestamp) <= current_app.config.get('FILES_ACCESS_TIMEOUT')

    @staticmethod
    def create_file_by_raw(user_id: str, tenant_id: str,
                        conversation_id: Optional[str], file_binary: bytes,
                        mimetype: str
                        ) -> ToolFile:
        """
        创建文件。

        参数:
        - user_id (str): 用户ID。
        - tenant_id (str): 租户ID。
        - conversation_id (Optional[str]): 会话ID，可以为None。
        - file_binary (bytes): 文件二进制数据。
        - mimetype (str): 文件的MIME类型。

        返回值:
        - ToolFile: 创建的文件对象。
        """

        # 根据MIME类型猜测文件扩展名，若无则默认为.bin
        extension = guess_extension(mimetype) or '.bin'
        # 生成唯一的文件名
        unique_name = uuid4().hex
        filename = f"tools/{tenant_id}/{unique_name}{extension}"
        storage.save(filename, file_binary)

        # 创建ToolFile对象，关联用户、租户、会话和文件信息
        tool_file = ToolFile(user_id=user_id, tenant_id=tenant_id,
                            conversation_id=conversation_id, file_key=filename, mimetype=mimetype)

        # 将ToolFile对象添加到数据库会话并提交
        db.session.add(tool_file)
        db.session.commit()

        return tool_file

    @staticmethod
    def create_file_by_url(user_id: str, tenant_id: str,
                        conversation_id: str, file_url: str,
                        ) -> ToolFile:
        """
        根据提供的URL创建文件。

        参数:
        - user_id: 用户ID，类型为str。
        - tenant_id: 租户ID，类型为str。
        - conversation_id: 会话ID，类型为str。
        - file_url: 文件的URL，类型为str。
        
        返回值:
        - 生成的ToolFile对象。
        """
        # 尝试下载文件
        response = get(file_url)
        response.raise_for_status()
        blob = response.content
        # 猜测文件类型和扩展名
        mimetype = guess_type(file_url)[0] or 'octet/stream'
        extension = guess_extension(mimetype) or '.bin'
        # 生成唯一文件名
        unique_name = uuid4().hex
        filename = f"tools/{tenant_id}/{unique_name}{extension}"
        storage.save(filename, blob)

        # 创建ToolFile对象并加入数据库会话
        tool_file = ToolFile(user_id=user_id, tenant_id=tenant_id,
                            conversation_id=conversation_id, file_key=filename,
                            mimetype=mimetype, original_url=file_url)

        db.session.add(tool_file)
        db.session.commit()

        return tool_file

    @staticmethod
    def create_file_by_key(user_id: str, tenant_id: str,
                        conversation_id: str, file_key: str,
                        mimetype: str
                        ) -> ToolFile:
        """
        创建文件对象。

        参数:
        user_id (str): 用户ID。
        tenant_id (str): 租户ID。
        conversation_id (str): 会话ID。
        file_key (str): 文件键。
        mimetype (str): 文件的MIME类型。

        返回:
        ToolFile: 文件对象。
        """
        # 创建ToolFile实例
        tool_file = ToolFile(user_id=user_id, tenant_id=tenant_id,
                            conversation_id=conversation_id, file_key=file_key, mimetype=mimetype)
        return tool_file

    @staticmethod
    def get_file_binary(id: str) -> Union[tuple[bytes, str], None]:
        """
        获取文件的二进制数据。

        :param id: 文件的唯一标识符。
        :return: 返回一个包含文件二进制数据和MIME类型的元组，如果文件不存在则返回None。

        详细说明：
        1. 根据提供的文件ID从数据库中查询对应的ToolFile对象。
        2. 如果查询到ToolFile对象存在，则从存储系统中加载一次该文件的二进制数据。
        3. 返回文件的二进制数据和MIME类型作为元组；如果文件不存在，则返回None。
        """
        # 从数据库中查询指定ID的ToolFile对象
        tool_file: ToolFile = db.session.query(ToolFile).filter(
            ToolFile.id == id,
        ).first()

        if not tool_file:
            return None  # 如果找不到对应的文件，直接返回None

        # 加载文件的二进制数据
        blob = storage.load_once(tool_file.file_key)

        # 返回文件的二进制数据和MIME类型
        return blob, tool_file.mimetype

    @staticmethod
    def get_file_binary_by_message_file_id(id: str) -> Union[tuple[bytes, str], None]:
        """
        获取指定文件id的文件二进制数据和MIME类型。

        :param id: 文件的唯一标识符。
        :return: 返回一个包含文件二进制数据和MIME类型的元组，如果找不到文件则返回None。

        """
        # 从数据库中查询对应文件id的消息文件
        message_file: MessageFile = db.session.query(MessageFile).filter(
            MessageFile.id == id,
        ).first()

        # 从消息文件的URL中提取工具文件ID
        tool_file_id = message_file.url.split('/')[-1]
        # 去除文件扩展名获取纯ID
        tool_file_id = tool_file_id.split('.')[0]

        # 查询工具文件信息
        tool_file: ToolFile = db.session.query(ToolFile).filter(
            ToolFile.id == tool_file_id,
        ).first()

        # 如果工具文件不存在，则直接返回None
        if not tool_file:
            return None

        # 从存储系统中加载文件二进制数据
        blob = storage.load_once(tool_file.file_key)

        # 返回文件二进制数据和MIME类型
        return blob, tool_file.mimetype

    @staticmethod
    def get_file_generator_by_tool_file_id(tool_file_id: str) -> Union[tuple[Generator, str], None]:
        """
        获取指定工具文件ID的文件二进制数据。

        :param tool_file_id: 工具文件的ID
        :type tool_file_id: str

        :return: 返回一个包含文件二进制流的生成器和文件MIME类型的元组，如果文件不存在则返回None
        :rtype: Union[tuple[Generator, str], None]
        """
        # 从数据库中查询对应ID的工具文件
        tool_file: ToolFile = db.session.query(ToolFile).filter(
            ToolFile.id == tool_file_id,
        ).first()

        # 如果工具文件不存在，则直接返回None
        if not tool_file:
            return None

        # 从存储系统中加载文件的二进制流
        generator = storage.load_stream(tool_file.file_key)

        # 返回文件二进制流生成器和MIME类型
        return generator, tool_file.mimetype


# init tool_file_parser
from core.file.tool_file_parser import tool_file_manager

tool_file_manager['manager'] = ToolFileManager
