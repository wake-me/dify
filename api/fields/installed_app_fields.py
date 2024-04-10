from flask_restful import fields

from libs.helper import TimestampField

# 定义应用的基本字段
app_fields = {
    'id': fields.String,  # 应用的唯一标识符
    'name': fields.String,  # 应用的名称
    'mode': fields.String,  # 应用的模式
    'icon': fields.String,  # 应用的图标链接
    'icon_background': fields.String  # 图标背景颜色
}

# 定义已安装应用的详细字段
installed_app_fields = {
    'id': fields.String,
    'app': fields.Nested(app_fields),
    'app_owner_tenant_id': fields.String,
    'is_pinned': fields.Boolean,
    'last_used_at': TimestampField,
    'editable': fields.Boolean,
    'uninstallable': fields.Boolean
}

# 定义已安装应用列表的字段
installed_app_list_fields = {
    'installed_apps': fields.List(fields.Nested(installed_app_fields))  # 包含多个已安装应用的详细信息
}