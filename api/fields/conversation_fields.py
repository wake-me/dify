from flask_restful import fields

from libs.helper import TimestampField


class MessageTextField(fields.Raw):
    """
    自定义字段类，用于处理消息文本格式化。

    参数:
    - value: 输入值，期望是一个列表，其中包含至少一个字典，字典中应有'text'键。

    返回:
    - 如果输入值存在且非空，则返回第一个字典中的'text'值；如果为空，则返回空字符串。
    """
    def format(self, value):
        return value[0]['text'] if value else ''

# 定义了一系列字段用于序列化和反序列化
account_fields = {
    'id': fields.String,  # 账户ID
    'name': fields.String,  # 账户名称
    'email': fields.String  # 账户邮箱
}

feedback_fields = {
    'rating': fields.String,  # 评分
    'content': fields.String,  # 反馈内容
    'from_source': fields.String,  # 反馈来源
    'from_end_user_id': fields.String,  # 终端用户ID
    'from_account': fields.Nested(account_fields, allow_null=True),  # 发送反馈的账户信息
}

annotation_fields = {
    'id': fields.String,  # 注解ID
    'question': fields.String,  # 注解问题
    'content': fields.String,  # 注解内容
    'account': fields.Nested(account_fields, allow_null=True),  # 创建注解的账户信息
    'created_at': TimestampField  # 创建时间
}

annotation_hit_history_fields = {
    'annotation_id': fields.String(attribute='id'),  # 注解ID
    'annotation_create_account': fields.Nested(account_fields, allow_null=True),  # 创建注解的账户信息
    'created_at': TimestampField  # 创建时间
}

message_file_fields = {
    'id': fields.String,  # 文件ID
    'type': fields.String,  # 文件类型
    'url': fields.String,  # 文件URL
    'belongs_to': fields.String(default='user'),  # 文件归属
}

agent_thought_fields = {
    'id': fields.String,  # 思考记录ID
    'chain_id': fields.String,  # 链ID
    'message_id': fields.String,  # 消息ID
    'position': fields.Integer,  # 位置
    'thought': fields.String,  # 思考内容
    'tool': fields.String,  # 使用的工具
    'tool_labels': fields.Raw,  # 工具标签
    'tool_input': fields.String,  # 工具输入
    'created_at': TimestampField,  # 创建时间
    'observation': fields.String,  # 观察结果
    'files': fields.List(fields.String),  # 关联文件列表
}

message_detail_fields = {
    'id': fields.String,  # 消息ID
    'conversation_id': fields.String,  # 对话ID
    'inputs': fields.Raw,  # 输入数据
    'query': fields.String,  # 查询内容
    'message': fields.Raw,  # 消息内容
    'message_tokens': fields.Integer,  # 消息分词数
    'answer': fields.String,  # 答案
    'answer_tokens': fields.Integer,  # 答案分词数
    'provider_response_latency': fields.Float,  # 提供者响应延迟
    'from_source': fields.String,  # 来源
    'from_end_user_id': fields.String,  # 终端用户ID
    'from_account_id': fields.String,  # 发送消息的账户ID
    'feedbacks': fields.List(fields.Nested(feedback_fields)),  # 反馈列表
    'annotation': fields.Nested(annotation_fields, allow_null=True),  # 注解信息
    'annotation_hit_history': fields.Nested(annotation_hit_history_fields, allow_null=True),  # 注解命中历史
    'created_at': TimestampField,  # 创建时间
    'agent_thoughts': fields.List(fields.Nested(agent_thought_fields)),  # 代理思考记录
    'message_files': fields.List(fields.Nested(message_file_fields), attribute='files'),  # 消息文件列表
}

# 定义反馈统计数据的字段结构
feedback_stat_fields = {
    'like': fields.Integer,  # 点赞数
    'dislike': fields.Integer  # 不点赞数
}

# 定义模型配置的字段结构
model_config_fields = {
    'opening_statement': fields.String,  # 开场白
    'suggested_questions': fields.Raw,  # 建议的问题
    'model': fields.Raw,  # 模型配置
    'user_input_form': fields.Raw,  # 用户输入表单
    'pre_prompt': fields.String,  # 提示信息
    'agent_mode': fields.Raw  # 代理模式配置
}

# 定义简单配置的字段结构
simple_configs_fields = {
    'prompt_template': fields.String,  # 提示模板
}

# 定义简单模型配置的字段结构
simple_model_config_fields = {
    'model': fields.Raw(attribute='model_dict'),  # 模型配置，使用model_dict属性
    'pre_prompt': fields.String,  # 提示信息
}

# 定义简单消息详情的字段结构
simple_message_detail_fields = {
    'inputs': fields.Raw,  # 输入信息
    'query': fields.String,  # 查询内容
    'message': MessageTextField,  # 消息内容
    'answer': fields.String,  # 答案
}

# 定义对话的字段结构
conversation_fields = {
    'id': fields.String,  # 对话ID
    'status': fields.String,  # 对话状态
    'from_source': fields.String,  # 来源
    'from_end_user_id': fields.String,  # 终端用户ID
    'from_end_user_session_id': fields.String(),  # 终端用户会话ID
    'from_account_id': fields.String,  # 账户ID
    'read_at': TimestampField,  # 阅读时间戳
    'created_at': TimestampField,  # 创建时间戳
    'annotation': fields.Nested(annotation_fields, allow_null=True),  # 注解数据
    'model_config': fields.Nested(simple_model_config_fields),  # 模型配置
    'user_feedback_stats': fields.Nested(feedback_stat_fields),  # 用户反馈统计数据
    'admin_feedback_stats': fields.Nested(feedback_stat_fields),  # 管理员反馈统计数据
    'message': fields.Nested(simple_message_detail_fields, attribute='first_message')  # 对话中的第一条消息
}

# 定义会话分页字段
conversation_pagination_fields = {
    'page': fields.Integer,  # 当前页码
    'limit': fields.Integer(attribute='per_page'),  # 每页数量
    'total': fields.Integer,  # 总数
    'has_more': fields.Boolean(attribute='has_next'),  # 是否有下一页
    'data': fields.List(fields.Nested(conversation_fields), attribute='items')  # 数据列表
}

# 定义会话消息详情字段
conversation_message_detail_fields = {
    'id': fields.String,  # 消息ID
    'status': fields.String,  # 状态
    'from_source': fields.String,  # 消息来源
    'from_end_user_id': fields.String,  # 发送者终端用户ID
    'from_account_id': fields.String,  # 发送者账户ID
    'created_at': TimestampField,  # 创建时间
    'model_config': fields.Nested(model_config_fields),  # 模型配置
    'message': fields.Nested(message_detail_fields, attribute='first_message'),  # 消息内容
}

# 定义带有摘要的会话字段
conversation_with_summary_fields = {
    'id': fields.String,  # 会话ID
    'status': fields.String,  # 状态
    'from_source': fields.String,  # 来源
    'from_end_user_id': fields.String,  # 终端用户ID
    'from_end_user_session_id': fields.String,  # 终端用户会话ID
    'from_account_id': fields.String,  # 账户ID
    'name': fields.String,  # 会话名称
    'summary': fields.String(attribute='summary_or_query'),  # 摘要或查询内容
    'read_at': TimestampField,  # 阅读时间
    'created_at': TimestampField,  # 创建时间
    'annotated': fields.Boolean,  # 是否已注释
    'model_config': fields.Nested(simple_model_config_fields),  # 简单模型配置
    'message_count': fields.Integer,  # 消息数量
    'user_feedback_stats': fields.Nested(feedback_stat_fields),  # 用户反馈统计
    'admin_feedback_stats': fields.Nested(feedback_stat_fields)  # 管理员反馈统计
}

# 定义带有摘要分页的会话字段
conversation_with_summary_pagination_fields = {
    'page': fields.Integer,  # 当前页码
    'limit': fields.Integer(attribute='per_page'),  # 每页数量
    'total': fields.Integer,  # 总数
    'has_more': fields.Boolean(attribute='has_next'),  # 是否有下一页
    'data': fields.List(fields.Nested(conversation_with_summary_fields), attribute='items')  # 数据列表
}

# 定义会话详细信息字段
conversation_detail_fields = {
    'id': fields.String,  # 会话ID
    'status': fields.String,  # 状态
    'from_source': fields.String,  # 来源
    'from_end_user_id': fields.String,  # 终端用户ID
    'from_account_id': fields.String,  # 账户ID
    'created_at': TimestampField,  # 创建时间
    'annotated': fields.Boolean,  # 是否已注释
    'introduction': fields.String,  # 介绍
    'model_config': fields.Nested(model_config_fields),  # 模型配置
    'message_count': fields.Integer,  # 消息数量
    'user_feedback_stats': fields.Nested(feedback_stat_fields),  # 用户反馈统计
    'admin_feedback_stats': fields.Nested(feedback_stat_fields)  # 管理员反馈统计
}

# 定义简单的会话信息字段
simple_conversation_fields = {
    'id': fields.String,  # 会话ID
    'name': fields.String,  # 会话名称
    'inputs': fields.Raw,  # 输入信息，原始格式
    'status': fields.String,  # 会话状态
    'introduction': fields.String,  # 会话介绍
    'created_at': TimestampField  # 创建时间戳
}

# 定义会话无限滚动分页字段
conversation_infinite_scroll_pagination_fields = {
    'limit': fields.Integer,  # 分页限制数量
    'has_more': fields.Boolean,  # 是否还有更多数据
    'data': fields.List(fields.Nested(simple_conversation_fields))  # 数据列表，嵌套简单的会话字段
}

# 定义包含模型配置的会话信息字段
conversation_with_model_config_fields = {
    **simple_conversation_fields,  # 继承简单的会话信息字段
    'model_config': fields.Raw,  # 模型配置信息，原始格式
}

# 定义包含模型配置的会话信息的无限滚动分页字段
conversation_with_model_config_infinite_scroll_pagination_fields = {
    'limit': fields.Integer,  # 分页限制数量
    'has_more': fields.Boolean,  # 是否还有更多数据
    'data': fields.List(fields.Nested(conversation_with_model_config_fields))  # 数据列表，嵌套包含模型配置的会话信息字段
}