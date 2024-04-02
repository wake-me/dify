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
    'id': fields.String,  # 安装应用的唯一标识符
    'app': fields.Nested(app_fields),  # 包含应用的基本信息
    'app_owner_tenant_id': fields.String,  # 应用所有者的租户ID
    'is_pinned': fields.Boolean,  # 是否固定在首页
    'last_used_at': TimestampField,  # 最后使用的时间戳
    'editable': fields.Boolean,  # 是否可以编辑
    'uninstallable': fields.Boolean,  # 是否可以卸载
    'is_agent': fields.Boolean  # 是否为代理应用
}

# 定义已安装应用列表的字段
installed_app_list_fields = {
    'installed_apps': fields.List(fields.Nested(installed_app_fields))  # 包含多个已安装应用的详细信息
}