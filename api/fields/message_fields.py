from flask_restful import fields

from fields.conversation_fields import message_file_fields
from libs.helper import TimestampField

# 定义反馈信息的字段结构
feedback_fields = {
    'rating': fields.String
}

# 定义检索器资源的字段结构
retriever_resource_fields = {
    'id': fields.String,  # 资源ID
    'message_id': fields.String,  # 消息ID
    'position': fields.Integer,  # 位置
    'dataset_id': fields.String,  # 数据集ID
    'dataset_name': fields.String,  # 数据集名称
    'document_id': fields.String,  # 文档ID
    'document_name': fields.String,  # 文档名称
    'data_source_type': fields.String,  # 数据源类型
    'segment_id': fields.String,  # 段落ID
    'score': fields.Float,  # 分数
    'hit_count': fields.Integer,  # 命中次数
    'word_count': fields.Integer,  # 单词数量
    'segment_position': fields.Integer,  # 段落位置
    'index_node_hash': fields.String,  # 索引节点哈希值
    'content': fields.String,  # 内容
    'created_at': TimestampField  # 创建时间
}

# 重新定义反馈信息的字段结构（此处可能为重复代码，考虑精简）
feedback_fields = {
    'rating': fields.String
}

# 定义代理思考的字段结构
agent_thought_fields = {
    'id': fields.String,  # ID
    'chain_id': fields.String,  # 链ID
    'message_id': fields.String,  # 消息ID
    'position': fields.Integer,  # 位置
    'thought': fields.String,  # 思考内容
    'tool': fields.String,  # 工具
    'tool_labels': fields.Raw,  # 工具标签
    'tool_input': fields.String,  # 工具输入
    'created_at': TimestampField,  # 创建时间
    'observation': fields.String,  # 观察结果
    'files': fields.List(fields.String)  # 文件列表
}

# 再次定义检索器资源的字段结构（此处可能为重复代码，考虑精简）
retriever_resource_fields = {
    'id': fields.String,  # 资源ID
    'message_id': fields.String,  # 消息ID
    'position': fields.Integer,  # 位置
    'dataset_id': fields.String,  # 数据集ID
    'dataset_name': fields.String,  # 数据集名称
    'document_id': fields.String,  # 文档ID
    'document_name': fields.String,  # 文档名称
    'data_source_type': fields.String,  # 数据源类型
    'segment_id': fields.String,  # 段落ID
    'score': fields.Float,  # 分数
    'hit_count': fields.Integer,  # 命中次数
    'word_count': fields.Integer,  # 单词数量
    'segment_position': fields.Integer,  # 段落位置
    'index_node_hash': fields.String,  # 索引节点哈希值
    'content': fields.String,  # 内容
    'created_at': TimestampField  # 创建时间
}

# 定义消息的字段结构
message_fields = {
    'id': fields.String,  # 消息ID
    'conversation_id': fields.String,  # 对话ID
    'inputs': fields.Raw,  # 输入内容
    'query': fields.String,  # 查询内容
    'answer': fields.String,  # 答案
    'feedback': fields.Nested(feedback_fields, attribute='user_feedback', allow_null=True),  # 用户反馈
    'retriever_resources': fields.List(fields.Nested(retriever_resource_fields)),  # 检索器资源列表
    'created_at': TimestampField,  # 创建时间
    'agent_thoughts': fields.List(fields.Nested(agent_thought_fields)),  # 代理思考列表
    'message_files': fields.List(fields.Nested(message_file_fields), attribute='files')  # 消息文件列表
}

# 定义消息无限滚动分页字段结构
message_infinite_scroll_pagination_fields = {
    'limit': fields.Integer,  # 限制数量
    'has_more': fields.Boolean,  # 是否有更多数据
    'data': fields.List(fields.Nested(message_fields))  # 数据列表
}