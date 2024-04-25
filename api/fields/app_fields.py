from flask_restful import fields

from libs.helper import TimestampField

# 定义应用详情的基本字段
app_detail_kernel_fields = {
    'id': fields.String,
    'name': fields.String,
    'description': fields.String,
    'mode': fields.String(attribute='mode_compatible_with_agent'),
    'icon': fields.String,
    'icon_background': fields.String,
}

# 定义相关应用列表的字段结构
related_app_list = {
    'data': fields.List(fields.Nested(app_detail_kernel_fields)),  # 相关应用数据列表
    'total': fields.Integer,  # 相关应用总数
}

# 定义模型配置的字段结构
model_config_fields = {
    'opening_statement': fields.String,
    'suggested_questions': fields.Raw(attribute='suggested_questions_list'),
    'suggested_questions_after_answer': fields.Raw(attribute='suggested_questions_after_answer_dict'),
    'speech_to_text': fields.Raw(attribute='speech_to_text_dict'),
    'text_to_speech': fields.Raw(attribute='text_to_speech_dict'),
    'retriever_resource': fields.Raw(attribute='retriever_resource_dict'),
    'annotation_reply': fields.Raw(attribute='annotation_reply_dict'),
    'more_like_this': fields.Raw(attribute='more_like_this_dict'),
    'sensitive_word_avoidance': fields.Raw(attribute='sensitive_word_avoidance_dict'),
    'external_data_tools': fields.Raw(attribute='external_data_tools_list'),
    'model': fields.Raw(attribute='model_dict'),
    'user_input_form': fields.Raw(attribute='user_input_form_list'),
    'dataset_query_variable': fields.String,
    'pre_prompt': fields.String,
    'agent_mode': fields.Raw(attribute='agent_mode_dict'),
    'prompt_type': fields.String,
    'chat_prompt_config': fields.Raw(attribute='chat_prompt_config_dict'),
    'completion_prompt_config': fields.Raw(attribute='completion_prompt_config_dict'),
    'dataset_configs': fields.Raw(attribute='dataset_configs_dict'),
    'file_upload': fields.Raw(attribute='file_upload_dict'),
    'created_at': TimestampField
}

# 定义应用详情页面展示的字段结构
app_detail_fields = {
    'id': fields.String,
    'name': fields.String,
    'description': fields.String,
    'mode': fields.String(attribute='mode_compatible_with_agent'),
    'icon': fields.String,
    'icon_background': fields.String,
    'enable_site': fields.Boolean,
    'enable_api': fields.Boolean,
    'model_config': fields.Nested(model_config_fields, attribute='app_model_config', allow_null=True),
    'created_at': TimestampField
}

# 定义提示配置的字段结构
prompt_config_fields = {
    'prompt_template': fields.String,  # 提示模板
}

# 定义部分模型配置的字段结构，用于更新等操作
model_config_partial_fields = {
    'model': fields.Raw(attribute='model_dict'),
    'pre_prompt': fields.String,
}

tag_fields = {
    'id': fields.String,
    'name': fields.String,
    'type': fields.String
}

# 定义与应用程序相关的部分字段及其类型
app_partial_fields = {
    'id': fields.String,
    'name': fields.String,
    'description': fields.String(attribute='desc_or_prompt'),
    'mode': fields.String(attribute='mode_compatible_with_agent'),
    'icon': fields.String,
    'icon_background': fields.String,
    'model_config': fields.Nested(model_config_partial_fields, attribute='app_model_config', allow_null=True),
    'created_at': TimestampField,
    'tags': fields.List(fields.Nested(tag_fields))
}


app_pagination_fields = {
    'page': fields.Integer,  # 当前页码
    'limit': fields.Integer(attribute='per_page'),  # 每页记录数
    'total': fields.Integer,  # 总记录数
    'has_more': fields.Boolean(attribute='has_next'),  # 是否有下一页
    'data': fields.List(fields.Nested(app_partial_fields), attribute='items')  # 数据列表
}

# 定义模板的字段及其类型
template_fields = {
    'name': fields.String,  # 模板名称
    'icon': fields.String,  # 模板图标链接
    'icon_background': fields.String,  # 图标背景颜色
    'description': fields.String,  # 模板描述
    'mode': fields.String,  # 模板的模式
    'model_config': fields.Nested(model_config_fields),  # 模板的模型配置
}

# 定义模板列表的字段
template_list_fields = {
    'data': fields.List(fields.Nested(template_fields)),  # 模板数据列表
}

# 定义站点信息的字段及其类型
site_fields = {
    'access_token': fields.String(attribute='code'),  # 站点的访问令牌
    'code': fields.String,  # 站点的唯一标识符
    'title': fields.String,  # 站点的标题
    'icon': fields.String,  # 站点的图标链接
    'icon_background': fields.String,  # 图标背景颜色
    'description': fields.String,  # 站点的描述
    'default_language': fields.String,  # 站点的默认语言
    'customize_domain': fields.String,  # 自定义站点域名
    'copyright': fields.String,  # 站点的版权信息
    'privacy_policy': fields.String,  # 站点的隐私政策
    'customize_token_strategy': fields.String,  # 自定义令牌策略
    'prompt_public': fields.Boolean,  # 是否公开提示
    'app_base_url': fields.String,  # 应用的基础URL
}

# 定义包含站点信息的 app 详情字段
app_detail_fields_with_site = {
    'id': fields.String,
    'name': fields.String,
    'description': fields.String,
    'mode': fields.String(attribute='mode_compatible_with_agent'),
    'icon': fields.String,
    'icon_background': fields.String,
    'enable_site': fields.Boolean,
    'enable_api': fields.Boolean,
    'model_config': fields.Nested(model_config_fields, attribute='app_model_config', allow_null=True),
    'site': fields.Nested(site_fields),
    'api_base_url': fields.String,
    'created_at': TimestampField,
    'deleted_tools': fields.List(fields.String),
}

# 定义站点相关字段
app_site_fields = {
    'app_id': fields.String,  # 关联的应用ID
    'access_token': fields.String(attribute='code'),  # 访问令牌（代码）
    'code': fields.String,  # 站点的唯一标识符
    'title': fields.String,  # 站点的标题
    'icon': fields.String,  # 站点的图标链接
    'icon_background': fields.String,  # 站点图标的背景颜色
    'description': fields.String,  # 站点的描述
    'default_language': fields.String,  # 默认的语言设置
    'customize_domain': fields.String,  # 自定义的域名
    'copyright': fields.String,  # 版权信息
    'privacy_policy': fields.String,  # 隐私政策
    'customize_token_strategy': fields.String,  # 自定义令牌策略
    'prompt_public': fields.Boolean  # 是否公开提示
}