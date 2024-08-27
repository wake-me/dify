from flask import Response, request
from flask_restful import Resource
from werkzeug.exceptions import NotFound

import services
from controllers.files import api
from libs.exception import BaseHTTPException
from services.account_service import TenantService
from services.file_service import FileService


class ImagePreviewApi(Resource):
    """
    图片预览API类，继承自Resource。
    
    方法:
    - get: 根据文件ID获取图片预览。
    
    参数:
    - file_id: 文件ID，用于获取图片预览。
    
    返回值:
    - 对于无效请求，返回400状态码和错误信息。
    - 对于支持的文件类型，返回图片预览和对应的MIME类型。
    """
    
    def get(self, file_id):
        # 将file_id转换为字符串格式
        file_id = str(file_id)

        timestamp = request.args.get("timestamp")
        nonce = request.args.get("nonce")
        sign = request.args.get("sign")

        # 若缺少时间戳、随机数或签名，则返回无效请求信息
        if not timestamp or not nonce or not sign:
            return {"content": "Invalid request."}, 400

        try:
            generator, mimetype = FileService.get_image_preview(file_id, timestamp, nonce, sign)
        except services.errors.file.UnsupportedFileTypeError:
            # 若文件类型不支持，则抛出异常
            raise UnsupportedFileTypeError()

        # 返回图片预览响应
        return Response(generator, mimetype=mimetype)


class WorkspaceWebappLogoApi(Resource):
    """
    用于获取工作空间Web应用的Logo的API接口
    
    参数:
    - workspace_id: 工作空间的ID，可以是数字或字符串
    
    返回值:
    - 返回一个Response对象，包含Web应用Logo的图像数据和MIME类型
    """
    
    def get(self, workspace_id):
        # 将workspace_id转换为字符串格式
        workspace_id = str(workspace_id)

        # 根据workspace_id获取定制配置，尝试获取替换Web应用Logo的文件ID
        custom_config = TenantService.get_custom_config(workspace_id)
        webapp_logo_file_id = custom_config.get("replace_webapp_logo") if custom_config is not None else None

        # 如果未找到webapp_logo_file_id，则抛出未找到错误
        if not webapp_logo_file_id:
            raise NotFound("webapp logo is not found")

        try:
            # 尝试根据webapp_logo_file_id获取图像预览及其MIME类型
            generator, mimetype = FileService.get_public_image_preview(
                webapp_logo_file_id,
            )
        except services.errors.file.UnsupportedFileTypeError:
            # 如果文件类型不受支持，则抛出不受支持的文件类型错误
            raise UnsupportedFileTypeError()

        # 返回图像数据和MIME类型
        return Response(generator, mimetype=mimetype)


api.add_resource(ImagePreviewApi, "/files/<uuid:file_id>/image-preview")
api.add_resource(WorkspaceWebappLogoApi, "/files/workspaces/<uuid:workspace_id>/webapp-logo")


class UnsupportedFileTypeError(BaseHTTPException):
    error_code = "unsupported_file_type"
    description = "File type not allowed."
    code = 415
