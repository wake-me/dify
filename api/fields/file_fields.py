from flask_restful import fields

from libs.helper import TimestampField

# 定义上传配置字段
upload_config_fields = {
    'file_size_limit': fields.Integer,  # 文件大小限制，单位为字节
    'batch_count_limit': fields.Integer,  # 批量上传限制数量
    'image_file_size_limit': fields.Integer,  # 图片文件大小限制，单位为字节
}

# 定义文件字段信息
file_fields = {
    'id': fields.String,  # 文件唯一标识符
    'name': fields.String,  # 文件名
    'size': fields.Integer,  # 文件大小，单位为字节
    'extension': fields.String,  # 文件扩展名
    'mime_type': fields.String,  # 文件的MIME类型
    'created_by': fields.String,  # 创建文件的用户标识符
    'created_at': TimestampField,  # 文件创建时间戳
}