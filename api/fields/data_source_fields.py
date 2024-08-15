from flask_restful import fields

from libs.helper import TimestampField

integrate_icon_fields = {"type": fields.String, "url": fields.String, "emoji": fields.String}

# 定义用于集成页面信息的字段结构
integrate_page_fields = {
    "page_name": fields.String,
    "page_id": fields.String,
    "page_icon": fields.Nested(integrate_icon_fields, allow_null=True),
    "is_bound": fields.Boolean,
    "parent_id": fields.String,
    "type": fields.String,
}

# 定义用于集成工作区信息的字段结构
integrate_workspace_fields = {
    "workspace_name": fields.String,
    "workspace_id": fields.String,
    "workspace_icon": fields.String,
    "pages": fields.List(fields.Nested(integrate_page_fields)),
}

# 定义用于集成Notion信息列表的字段结构
integrate_notion_info_list_fields = {
    "notion_info": fields.List(fields.Nested(integrate_workspace_fields)),
}

integrate_icon_fields = {"type": fields.String, "url": fields.String, "emoji": fields.String}

# 重新定义用于集成页面信息的字段结构（与上方相似，但省略了'is_bound'字段）
integrate_page_fields = {
    "page_name": fields.String,
    "page_id": fields.String,
    "page_icon": fields.Nested(integrate_icon_fields, allow_null=True),
    "parent_id": fields.String,
    "type": fields.String,
}

# 重新定义用于集成工作区信息的字段结构，增加了'total'字段用于表示总数
integrate_workspace_fields = {
    "workspace_name": fields.String,
    "workspace_id": fields.String,
    "workspace_icon": fields.String,
    "pages": fields.List(fields.Nested(integrate_page_fields)),
    "total": fields.Integer,
}

# 定义用于资源集成信息的字段结构
integrate_fields = {
    "id": fields.String,
    "provider": fields.String,
    "created_at": TimestampField,
    "is_bound": fields.Boolean,
    "disabled": fields.Boolean,
    "link": fields.String,
    "source_info": fields.Nested(integrate_workspace_fields),
}

# 定义用于集成信息列表的字段结构
integrate_list_fields = {
    "data": fields.List(fields.Nested(integrate_fields)),
}
