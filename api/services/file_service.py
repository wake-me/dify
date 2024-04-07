import datetime
import hashlib
import uuid
from collections.abc import Generator
from typing import Union

from flask import current_app
from flask_login import current_user
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import NotFound

from core.file.upload_file_parser import UploadFileParser
from core.rag.extractor.extract_processor import ExtractProcessor
from extensions.ext_database import db
from extensions.ext_storage import storage
from models.account import Account
from models.model import EndUser, UploadFile
from services.errors.file import FileTooLargeError, UnsupportedFileTypeError

# 定义支持的图片文件扩展名列表，并将其转换为小写和大写两种形式，以便于文件扩展名的大小写不敏感匹配。
IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'webp', 'gif', 'svg']
IMAGE_EXTENSIONS.extend([ext.upper() for ext in IMAGE_EXTENSIONS])

# 定义允许的文件扩展名列表，主要用于验证上传文件的类型。
ALLOWED_EXTENSIONS = ['txt', 'markdown', 'md', 'pdf', 'html', 'htm', 'xlsx', 'docx', 'csv']
# 定义不受信任的文件扩展名列表，比ALLOWED_EXTENSIONS多包含了一些可能包含潜在风险的文件类型。
UNSTRUSTURED_ALLOWED_EXTENSIONS = ['txt', 'markdown', 'md', 'pdf', 'html', 'htm', 'xlsx',
                                   'docx', 'csv', 'eml', 'msg', 'pptx', 'ppt', 'xml']
# 定义预览文本的字数限制。
PREVIEW_WORDS_LIMIT = 3000

class FileService:

    @staticmethod
    def upload_file(file: FileStorage, user: Union[Account, EndUser], only_image: bool = False) -> UploadFile:
        """
        上传文件到服务器并保存到数据库。

        参数:
        - file: FileStorage对象，待上传的文件。
        - user: Account或EndUser对象，上传文件的用户。
        - only_image: 布尔值，默认为False，如果为True，则只允许上传图片。

        返回值:
        - UploadFile对象，包含上传文件的信息。

        抛出:
        - UnsupportedFileTypeError: 如果文件类型不受支持。
        - FileTooLargeError: 如果文件大小超过限制。
        """
        # 获取文件扩展名
        extension = file.filename.split('.')[-1]
        # 获取应用配置中的ETL类型
        etl_type = current_app.config['ETL_TYPE']
        # 根据ETL类型确定允许的文件扩展名列表
        allowed_extensions = UNSTRUSTURED_ALLOWED_EXTENSIONS + IMAGE_EXTENSIONS if etl_type == 'Unstructured' \
            else ALLOWED_EXTENSIONS + IMAGE_EXTENSIONS
        # 检查文件扩展名是否受支持
        if extension.lower() not in allowed_extensions:
            raise UnsupportedFileTypeError()
        elif only_image and extension.lower() not in IMAGE_EXTENSIONS:
            raise UnsupportedFileTypeError()

        # 读取文件内容
        file_content = file.read()

        # 获取文件大小
        file_size = len(file_content)

        # 根据文件扩展名确定文件大小限制
        if extension.lower() in IMAGE_EXTENSIONS:
            file_size_limit = current_app.config.get("UPLOAD_IMAGE_FILE_SIZE_LIMIT") * 1024 * 1024
        else:
            file_size_limit = current_app.config.get("UPLOAD_FILE_SIZE_LIMIT") * 1024 * 1024

        # 检查文件大小是否超过限制
        if file_size > file_size_limit:
            message = f'File size exceeded. {file_size} > {file_size_limit}'
            raise FileTooLargeError(message)

        # 使用UUID作为文件名
        file_uuid = str(uuid.uuid4())

        # 根据用户类型获取当前租户ID
        if isinstance(user, Account):
            current_tenant_id = user.current_tenant_id
        else:
            # end_user
            current_tenant_id = user.tenant_id

        # 构造文件存储路径
        file_key = 'upload_files/' + current_tenant_id + '/' + file_uuid + '.' + extension

        # 将文件内容保存到存储系统
        storage.save(file_key, file_content)

        # 保存文件信息到数据库
        config = current_app.config
        upload_file = UploadFile(
            tenant_id=current_tenant_id,
            storage_type=config['STORAGE_TYPE'],
            key=file_key,
            name=file.filename,
            size=file_size,
            extension=extension,
            mime_type=file.mimetype,
            created_by_role=('account' if isinstance(user, Account) else 'end_user'),
            created_by=user.id,
            created_at=datetime.datetime.utcnow(),
            used=False,
            hash=hashlib.sha3_256(file_content).hexdigest()
        )

        db.session.add(upload_file)
        db.session.commit()

        return upload_file

    @staticmethod
    def upload_text(text: str, text_name: str) -> UploadFile:
        """
        上传文本到服务器的存储系统，并在数据库中记录文件信息。
        
        参数:
        text: str - 要上传的文本内容。
        text_name: str - 文本的原始名称。
        
        返回值:
        UploadFile - 包含上传文件信息的对象。
        """
        # 使用UUID作为文件名
        file_uuid = str(uuid.uuid4())
        # 构建文件在存储系统中的键值
        file_key = 'upload_files/' + current_user.current_tenant_id + '/' + file_uuid + '.txt'

        # 将文本内容编码后保存到存储系统
        storage.save(file_key, text.encode('utf-8'))

        # 在数据库中创建新的文件记录
        config = current_app.config
        upload_file = UploadFile(
            tenant_id=current_user.current_tenant_id,
            storage_type=config['STORAGE_TYPE'],
            key=file_key,
            name=text_name + '.txt',
            size=len(text),
            extension='txt',
            mime_type='text/plain',
            created_by=current_user.id,
            created_at=datetime.datetime.utcnow(),
            used=True,
            used_by=current_user.id,
            used_at=datetime.datetime.utcnow()
        )

        # 将新文件记录添加到数据库会话并提交
        db.session.add(upload_file)
        db.session.commit()

        return upload_file

    @staticmethod
    def get_file_preview(file_id: str) -> str:
        """
        获取文件的预览文本。
        
        参数:
        file_id (str): 文件的唯一标识符。
        
        返回:
        str: 文件的预览文本。如果文件不存在或文件类型不受支持，则抛出相应的异常。
        """
        # 从数据库中查询对应的文件信息
        upload_file = db.session.query(UploadFile) \
            .filter(UploadFile.id == file_id) \
            .first()

        if not upload_file:
            # 如果文件不存在，则抛出异常
            raise NotFound("File not found")

        # 根据应用配置确定文件类型是否受支持
        extension = upload_file.extension
        etl_type = current_app.config['ETL_TYPE']
        allowed_extensions = UNSTRUSTURED_ALLOWED_EXTENSIONS if etl_type == 'Unstructured' else ALLOWED_EXTENSIONS
        if extension.lower() not in allowed_extensions:
            # 如果文件类型不受支持，则抛出异常
            raise UnsupportedFileTypeError()

        # 从文件中提取文本，并限制预览的字数
        text = ExtractProcessor.load_from_upload_file(upload_file, return_text=True)
        text = text[0:PREVIEW_WORDS_LIMIT] if text else ''

        return text

    @staticmethod
    def get_image_preview(file_id: str, timestamp: str, nonce: str, sign: str) -> tuple[Generator, str]:
        """
        获取图片预览

        参数:
        file_id (str): 文件ID。
        timestamp (str): 请求的时间戳。
        nonce (str): 随机字符串，用于防止重放攻击。
        sign (str): 签名字符串，用于验证请求的合法性。

        返回:
        tuple[Generator, str]: 一个元组，包含文件的生成器（用于逐块读取文件）和文件的MIME类型。
        """
        # 验证文件签名的合法性
        result = UploadFileParser.verify_image_file_signature(file_id, timestamp, nonce, sign)
        if not result:
            raise NotFound("File not found or signature is invalid")

        # 从数据库中查询文件信息
        upload_file = db.session.query(UploadFile) \
            .filter(UploadFile.id == file_id) \
            .first()

        if not upload_file:
            raise NotFound("File not found or signature is invalid")

        # 检查文件扩展名是否为支持的图片类型
        extension = upload_file.extension
        if extension.lower() not in IMAGE_EXTENSIONS:
            raise UnsupportedFileTypeError()

        # 从存储系统中加载文件
        generator = storage.load(upload_file.key, stream=True)

        return generator, upload_file.mime_type

    @staticmethod
    def get_public_image_preview(file_id: str) -> tuple[Generator, str]:
        """
        获取公开图片预览
        
        参数:
        file_id (str): 文件ID，用于查询数据库中的上传文件记录。
        
        返回值:
        tuple[Generator, str]: 返回一个元组，包含图片数据的生成器和图片的MIME类型。
        
        抛出:
        NotFound: 如果文件不存在或签名无效。
        UnsupportedFileTypeError: 如果文件扩展名不是图片类型。
        """
        # 从数据库中查询文件记录
        upload_file = db.session.query(UploadFile) \
            .filter(UploadFile.id == file_id) \
            .first()

        if not upload_file:
            raise NotFound("File not found or signature is invalid")

        # 检查文件扩展名是否为图片类型
        extension = upload_file.extension
        if extension.lower() not in IMAGE_EXTENSIONS:
            raise UnsupportedFileTypeError()

        # 从存储系统加载图片
        generator = storage.load(upload_file.key)

        return generator, upload_file.mime_type
