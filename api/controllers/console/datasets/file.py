from flask import current_app, request
from flask_login import current_user
from flask_restful import Resource, marshal_with

import services
from controllers.console import api
from controllers.console.datasets.error import (
    FileTooLargeError,
    NoFileUploadedError,
    TooManyFilesError,
    UnsupportedFileTypeError,
)
from controllers.console.setup import setup_required
from controllers.console.wraps import account_initialization_required, cloud_edition_billing_resource_check
from fields.file_fields import file_fields, upload_config_fields
from libs.login import login_required
from services.file_service import ALLOWED_EXTENSIONS, UNSTRUSTURED_ALLOWED_EXTENSIONS, FileService

# 定义预览模式下可显示文本的最大字数限制。
PREVIEW_WORDS_LIMIT = 3000


class FileApi(Resource):
    """
    文件API类，提供文件上传和获取文件上传配置信息的功能。
    """

    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(upload_config_fields)
    def get(self):
        """
        获取文件上传配置信息。
        
        返回:
            一个包含文件上传限制信息的字典: 包括文件大小限制、批量上传限制和图片文件大小限制；
            HTTP状态码200。
        """
        # 从应用配置中获取上传相关的限制参数
        file_size_limit = current_app.config.get("UPLOAD_FILE_SIZE_LIMIT")
        batch_count_limit = current_app.config.get("UPLOAD_FILE_BATCH_LIMIT")
        image_file_size_limit = current_app.config.get("UPLOAD_IMAGE_FILE_SIZE_LIMIT")
        
        return {
            'file_size_limit': file_size_limit,
            'batch_count_limit': batch_count_limit,
            'image_file_size_limit': image_file_size_limit
        }, 200

    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(file_fields)
    @cloud_edition_billing_resource_check(resource='documents')
    def post(self):
        """
        上传文件。
        
        参数:
            通过HTTP请求上传的文件。
            
        返回:
            上传成功后的文件信息;
            HTTP状态码201。
            
        异常:
            如果没有文件被上传、上传文件数量超过限制、文件过大或文件类型不受支持，将抛出相应的错误。
        """
        # 从请求中获取文件
        file = request.files['file']

        # 检查文件是否正确上传
        if 'file' not in request.files:
            raise NoFileUploadedError()  # 如果没有文件被上传，则抛出错误
        if len(request.files) > 1:
            raise TooManyFilesError()  # 如果上传了多个文件，则抛出错误
        
        # 尝试上传文件，处理可能的错误
        try:
            upload_file = FileService.upload_file(file, current_user)
        except services.errors.file.FileTooLargeError as file_too_large_error:
            raise FileTooLargeError(file_too_large_error.description)  # 如果文件过大，则抛出错误
        except services.errors.file.UnsupportedFileTypeError:
            raise UnsupportedFileTypeError()  # 如果文件类型不受支持，则抛出错误

        return upload_file, 201


class FilePreviewApi(Resource):
    """
    文件预览API类，提供获取特定文件预览内容的功能。
    
    继承自Resource，使用了装饰器来确保：设置已完成、用户已登录、账户已初始化。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    def get(self, file_id):
        """
        获取指定文件的预览内容。
        
        参数:
        - file_id: 文件的唯一标识符，整数类型。
        
        返回值:
        - 一个包含预览内容的字典。
        """
        file_id = str(file_id)  # 将file_id转换为字符串
        text = FileService.get_file_preview(file_id)  # 从文件服务中获取预览文本
        return {'content': text}  # 返回包含预览内容的字典


class FileSupportTypeApi(Resource):
    """
    文件支持类型API类，提供获取允许的文件扩展名列表的功能。
    
    继承自Resource，使用了装饰器来确保：设置已完成、用户已登录、账户已初始化。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        """
        获取当前支持的文件扩展名列表。
        
        返回值:
        - 一个包含允许的文件扩展名列表的字典。
        """
        etl_type = current_app.config['ETL_TYPE']  # 从应用配置中获取ETL类型
        # 根据ETL类型选择允许的文件扩展名列表
        allowed_extensions = UNSTRUSTURED_ALLOWED_EXTENSIONS if etl_type == 'Unstructured' else ALLOWED_EXTENSIONS
        return {'allowed_extensions': allowed_extensions}  # 返回包含允许扩展名列表的字典


api.add_resource(FileApi, '/files/upload')
api.add_resource(FilePreviewApi, '/files/<uuid:file_id>/preview')
api.add_resource(FileSupportTypeApi, '/files/support-type')
