from flask_restful import fields

from fields.member_fields import simple_account_fields
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
        return value[0]["text"] if value else ""


feedback_fields = {
    "rating": fields.String,
    "content": fields.String,
    "from_source": fields.String,
    "from_end_user_id": fields.String,
    "from_account": fields.Nested(simple_account_fields, allow_null=True),
}

annotation_fields = {
    "id": fields.String,
    "question": fields.String,
    "content": fields.String,
    "account": fields.Nested(simple_account_fields, allow_null=True),
    "created_at": TimestampField,
}

annotation_hit_history_fields = {
    "annotation_id": fields.String(attribute="id"),
    "annotation_create_account": fields.Nested(simple_account_fields, allow_null=True),
    "created_at": TimestampField,
}

message_file_fields = {
    "id": fields.String,
    "type": fields.String,
    "url": fields.String,
    "belongs_to": fields.String(default="user"),
}

agent_thought_fields = {
    "id": fields.String,
    "chain_id": fields.String,
    "message_id": fields.String,
    "position": fields.Integer,
    "thought": fields.String,
    "tool": fields.String,
    "tool_labels": fields.Raw,
    "tool_input": fields.String,
    "created_at": TimestampField,
    "observation": fields.String,
    "files": fields.List(fields.String),
}

message_detail_fields = {
    "id": fields.String,
    "conversation_id": fields.String,
    "inputs": fields.Raw,
    "query": fields.String,
    "message": fields.Raw,
    "message_tokens": fields.Integer,
    "answer": fields.String(attribute="re_sign_file_url_answer"),
    "answer_tokens": fields.Integer,
    "provider_response_latency": fields.Float,
    "from_source": fields.String,
    "from_end_user_id": fields.String,
    "from_account_id": fields.String,
    "feedbacks": fields.List(fields.Nested(feedback_fields)),
    "workflow_run_id": fields.String,
    "annotation": fields.Nested(annotation_fields, allow_null=True),
    "annotation_hit_history": fields.Nested(annotation_hit_history_fields, allow_null=True),
    "created_at": TimestampField,
    "agent_thoughts": fields.List(fields.Nested(agent_thought_fields)),
    "message_files": fields.List(fields.Nested(message_file_fields), attribute="files"),
    "metadata": fields.Raw(attribute="message_metadata_dict"),
    "status": fields.String,
    "error": fields.String,
}

feedback_stat_fields = {"like": fields.Integer, "dislike": fields.Integer}

# 定义模型配置的字段结构
model_config_fields = {
    "opening_statement": fields.String,
    "suggested_questions": fields.Raw,
    "model": fields.Raw,
    "user_input_form": fields.Raw,
    "pre_prompt": fields.String,
    "agent_mode": fields.Raw,
}

# 定义简单配置的字段结构
simple_configs_fields = {
    "prompt_template": fields.String,
}

# 定义简单模型配置的字段结构
simple_model_config_fields = {
    "model": fields.Raw(attribute="model_dict"),
    "pre_prompt": fields.String,
}

# 定义简单消息详情的字段结构
simple_message_detail_fields = {
    "inputs": fields.Raw,
    "query": fields.String,
    "message": MessageTextField,
    "answer": fields.String,
}

# 定义对话的字段结构
conversation_fields = {
    "id": fields.String,
    "status": fields.String,
    "from_source": fields.String,
    "from_end_user_id": fields.String,
    "from_end_user_session_id": fields.String(),
    "from_account_id": fields.String,
    "read_at": TimestampField,
    "created_at": TimestampField,
    "annotation": fields.Nested(annotation_fields, allow_null=True),
    "model_config": fields.Nested(simple_model_config_fields),
    "user_feedback_stats": fields.Nested(feedback_stat_fields),
    "admin_feedback_stats": fields.Nested(feedback_stat_fields),
    "message": fields.Nested(simple_message_detail_fields, attribute="first_message"),
}

# 定义会话分页字段
conversation_pagination_fields = {
    "page": fields.Integer,
    "limit": fields.Integer(attribute="per_page"),
    "total": fields.Integer,
    "has_more": fields.Boolean(attribute="has_next"),
    "data": fields.List(fields.Nested(conversation_fields), attribute="items"),
}

# 定义会话消息详情字段
conversation_message_detail_fields = {
    "id": fields.String,
    "status": fields.String,
    "from_source": fields.String,
    "from_end_user_id": fields.String,
    "from_account_id": fields.String,
    "created_at": TimestampField,
    "model_config": fields.Nested(model_config_fields),
    "message": fields.Nested(message_detail_fields, attribute="first_message"),
}

# 定义带有摘要的会话字段
conversation_with_summary_fields = {
    "id": fields.String,
    "status": fields.String,
    "from_source": fields.String,
    "from_end_user_id": fields.String,
    "from_end_user_session_id": fields.String,
    "from_account_id": fields.String,
    "name": fields.String,
    "summary": fields.String(attribute="summary_or_query"),
    "read_at": TimestampField,
    "created_at": TimestampField,
    "annotated": fields.Boolean,
    "model_config": fields.Nested(simple_model_config_fields),
    "message_count": fields.Integer,
    "user_feedback_stats": fields.Nested(feedback_stat_fields),
    "admin_feedback_stats": fields.Nested(feedback_stat_fields),
}

# 定义带有摘要分页的会话字段
conversation_with_summary_pagination_fields = {
    "page": fields.Integer,
    "limit": fields.Integer(attribute="per_page"),
    "total": fields.Integer,
    "has_more": fields.Boolean(attribute="has_next"),
    "data": fields.List(fields.Nested(conversation_with_summary_fields), attribute="items"),
}

# 定义会话详细信息字段
conversation_detail_fields = {
    "id": fields.String,
    "status": fields.String,
    "from_source": fields.String,
    "from_end_user_id": fields.String,
    "from_account_id": fields.String,
    "created_at": TimestampField,
    "annotated": fields.Boolean,
    "introduction": fields.String,
    "model_config": fields.Nested(model_config_fields),
    "message_count": fields.Integer,
    "user_feedback_stats": fields.Nested(feedback_stat_fields),
    "admin_feedback_stats": fields.Nested(feedback_stat_fields),
}

# 定义简单的会话信息字段
simple_conversation_fields = {
    "id": fields.String,
    "name": fields.String,
    "inputs": fields.Raw,
    "status": fields.String,
    "introduction": fields.String,
    "created_at": TimestampField,
}

# 定义会话无限滚动分页字段
conversation_infinite_scroll_pagination_fields = {
    "limit": fields.Integer,
    "has_more": fields.Boolean,
    "data": fields.List(fields.Nested(simple_conversation_fields)),
}

# 定义包含模型配置的会话信息字段
conversation_with_model_config_fields = {
    **simple_conversation_fields,
    "model_config": fields.Raw,
}

# 定义包含模型配置的会话信息的无限滚动分页字段
conversation_with_model_config_infinite_scroll_pagination_fields = {
    "limit": fields.Integer,
    "has_more": fields.Boolean,
    "data": fields.List(fields.Nested(conversation_with_model_config_fields)),
}
