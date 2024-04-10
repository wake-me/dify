from flask import request
from flask_restful import Resource, marshal_with

import services
from controllers.service_api import api
from controllers.service_api.app.error import (
    FileTooLargeError,
    NoFileUploadedError,
    TooManyFilesError,
    UnsupportedFileTypeError,
)
from controllers.service_api.wraps import FetchUserArg, WhereisUserArg, validate_app_token
from fields.file_fields import file_fields
from models.model import App, EndUser
from services.file_service import FileService


class FileApi(Resource):
    """
    文件API类，用于处理文件上传请求。

    Attributes:
        None
    """

    @validate_app_token(fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.FORM))
    @marshal_with(file_fields)
    def post(self, app_model: App, end_user: EndUser):
        """
        处理文件上传请求。

        Args:
            app_model: 应用模型，用于验证应用令牌。
            end_user: 终端用户模型，用于记录上传文件的用户信息。

        Returns:
            上传成功后的文件信息和HTTP状态码201。

        Raises:
            NoFileUploadedError: 未上传文件错误。
            UnsupportedFileTypeError: 不支持的文件类型错误。
            TooManyFilesError: 上传文件数量过多错误。
            FileTooLargeError: 文件过大错误。
        """
        file = request.files['file']

        # 检查文件是否上传、文件类型是否支持以及上传文件数量是否符合要求
        if 'file' not in request.files:
            raise NoFileUploadedError()
        if not file.mimetype:
            raise UnsupportedFileTypeError()
        if len(request.files) > 1:
            raise TooManyFilesError()

        try:
            # 尝试上传文件
            upload_file = FileService.upload_file(file, end_user)
        except services.errors.file.FileTooLargeError as file_too_large_error:
            # 文件过大时抛出异常
            raise FileTooLargeError(file_too_large_error.description)
        except services.errors.file.UnsupportedFileTypeError:
            # 文件类型不支持时抛出异常
            raise UnsupportedFileTypeError()

        return upload_file, 201


api.add_resource(FileApi, '/files/upload')
