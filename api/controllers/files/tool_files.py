from flask import Response
from flask_restful import Resource, reqparse
from werkzeug.exceptions import Forbidden, NotFound

from controllers.files import api
from core.tools.tool_file_manager import ToolFileManager
from libs.exception import BaseHTTPException


class ToolFilePreviewApi(Resource):
    """
    提供工具文件预览的API接口
    
    参数:
    - file_id: 文件ID，用于标识要预览的文件
    - extension: 文件扩展名，用于指定文件类型
    
    返回值:
    - 返回一个响应对象，包含文件生成器和MIME类型
    """
    
    def get(self, file_id, extension):
        file_id = str(file_id)  # 将file_id转换为字符串

        # 初始化请求解析器
        parser = reqparse.RequestParser()

        # 添加请求参数解析规则
        parser.add_argument('timestamp', type=str, required=True, location='args')
        parser.add_argument('nonce', type=str, required=True, location='args')
        parser.add_argument('sign', type=str, required=True, location='args')

        # 解析请求参数
        args = parser.parse_args()

        # 验证请求的合法性
        if not ToolFileManager.verify_file(file_id=file_id,
                                            timestamp=args['timestamp'],
                                            nonce=args['nonce'],
                                            sign=args['sign'],
        ):
            raise Forbidden('Invalid request.')
        
        try:
            # 尝试根据文件ID获取文件生成器
            result = ToolFileManager.get_file_generator_by_message_file_id(
                file_id,
            )

            # 如果文件不存在，抛出未找到错误
            if not result:
                raise NotFound('file is not found')
            
            generator, mimetype = result  # 解析获取的结果
        except Exception:
            # 如果遇到不支持的文件类型，抛出错误
            raise UnsupportedFileTypeError()

        # 返回文件生成器和MIME类型
        return Response(generator, mimetype=mimetype)

api.add_resource(ToolFilePreviewApi, '/files/tools/<uuid:file_id>.<string:extension>')

class UnsupportedFileTypeError(BaseHTTPException):
    error_code = 'unsupported_file_type'
    description = "File type not allowed."
    code = 415
