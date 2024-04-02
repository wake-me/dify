from flask_restful import fields

from libs.helper import TimestampField

# 定义用于集成图标信息的字段结构
integrate_icon_fields = {
    'type': fields.String,  # 图标类型
    'url': fields.String,  # 图标URL
    'emoji': fields.String  # 图标表情
}

# 定义用于集成页面信息的字段结构
integrate_page_fields = {
    'page_name': fields.String,  # 页面名称
    'page_id': fields.String,  # 页面ID
    'page_icon': fields.Nested(integrate_icon_fields, allow_null=True),  # 页面图标，可以为空
    'is_bound': fields.Boolean,  # 是否绑定
    'parent_id': fields.String,  # 父页面ID
    'type': fields.String  # 页面类型
}

# 定义用于集成工作区信息的字段结构
integrate_workspace_fields = {
    'workspace_name': fields.String,  # 工作区名称
    'workspace_id': fields.String,  # 工作区ID
    'workspace_icon': fields.String,  # 工作区图标
    'pages': fields.List(fields.Nested(integrate_page_fields))  # 页面列表
}

# 定义用于集成Notion信息列表的字段结构
integrate_notion_info_list_fields = {
    'notion_info': fields.List(fields.Nested(integrate_workspace_fields)),  # Notion信息列表
}

# 重新定义用于集成图标信息的字段结构（与上方重复，可能用于不同场合）
integrate_icon_fields = {
    'type': fields.String,  # 图标类型
    'url': fields.String,  # 图标URL
    'emoji': fields.String  # 图标表情
}

# 重新定义用于集成页面信息的字段结构（与上方相似，但省略了'is_bound'字段）
integrate_page_fields = {
    'page_name': fields.String,  # 页面名称
    'page_id': fields.String,  # 页面ID
    'page_icon': fields.Nested(integrate_icon_fields, allow_null=True),  # 页面图标，可以为空
    'parent_id': fields.String,  # 父页面ID
    'type': fields.String  # 页面类型
}

# 重新定义用于集成工作区信息的字段结构，增加了'total'字段用于表示总数
integrate_workspace_fields = {
    'workspace_name': fields.String,  # 工作区名称
    'workspace_id': fields.String,  # 工作区ID
    'workspace_icon': fields.String,  # 工作区图标
    'pages': fields.List(fields.Nested(integrate_page_fields)),  # 页面列表
    'total': fields.Integer  # 总数
}

# 定义用于资源集成信息的字段结构
integrate_fields = {
    'id': fields.String,  # ID
    'provider': fields.String,  # 提供者
    'created_at': TimestampField,  # 创建时间
    'is_bound': fields.Boolean,  # 是否绑定
    'disabled': fields.Boolean,  # 是否禁用
    'link': fields.String,  # 链接
    'source_info': fields.Nested(integrate_workspace_fields)  # 来源信息，嵌套了工作区字段结构
}

# 定义用于集成信息列表的字段结构
integrate_list_fields = {
    'data': fields.List(fields.Nested(integrate_fields)),  # 数据列表，包含多个集成字段结构的项
}