from flask_restful import fields

from libs.helper import AppIconUrlField, TimestampField

# 定义应用的基本字段
app_fields = {
    "id": fields.String,
    "name": fields.String,
    "mode": fields.String,
    "icon_type": fields.String,
    "icon": fields.String,
    "icon_background": fields.String,
    "icon_url": AppIconUrlField,
}

# 定义已安装应用的详细字段
installed_app_fields = {
    "id": fields.String,
    "app": fields.Nested(app_fields),
    "app_owner_tenant_id": fields.String,
    "is_pinned": fields.Boolean,
    "last_used_at": TimestampField,
    "editable": fields.Boolean,
    "uninstallable": fields.Boolean,
}

installed_app_list_fields = {"installed_apps": fields.List(fields.Nested(installed_app_fields))}
