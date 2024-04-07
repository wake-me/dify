from flask import request
from flask_restful import marshal_with

import services
from controllers.web import api
from controllers.web.error import FileTooLargeError, NoFileUploadedError, TooManyFilesError, UnsupportedFileTypeError
from controllers.web.wraps import WebApiResource
from fields.file_fields import file_fields
from services.file_service import FileService


class FileApi(WebApiResource):
    """
    文件API类，用于处理文件上传操作。

    Attributes:
        WebApiResource: 继承的基类，提供API资源的基础方法。
    """

    @marshal_with(file_fields)
    def post(self, app_model, end_user):
        """
        处理文件上传请求。

        Args:
            app_model: 应用模型，用于文件上传时的背景信息。
            end_user: 终端用户信息，标识文件上传的用户。

        Returns:
            upload_file: 上传成功后返回的文件信息。
            201: HTTP状态码，表示成功创建资源。

        Raises:
            NoFileUploadedError: 未上传文件时抛出。
            TooManyFilesError: 上传文件数量超过1个时抛出。
            FileTooLargeError: 文件大小超过限制时抛出。
            UnsupportedFileTypeError: 文件类型不受支持时抛出。
        """
        # 从请求中获取文件
        file = request.files['file']

        # 检查文件是否上传以及是否只上传了一个文件
        if 'file' not in request.files:
            raise NoFileUploadedError()
        
        if len(request.files) > 1:
            raise TooManyFilesError()

        try:
            # 尝试上传文件
            upload_file = FileService.upload_file(file, end_user)
        except services.errors.file.FileTooLargeError as file_too_large_error:
            # 文件大小超出限制时抛出异常
            raise FileTooLargeError(file_too_large_error.description)
        except services.errors.file.UnsupportedFileTypeError:
            # 文件类型不受支持时抛出异常
            raise UnsupportedFileTypeError()

        return upload_file, 201


api.add_resource(FileApi, '/files/upload')
