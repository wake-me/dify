from flask_restful import fields

from libs.helper import TimestampField

# 定义段落字段的映射，用于序列化和反序列化数据
segment_fields = {
    'id': fields.String,  # 段落的唯一标识符
    'position': fields.Integer,  # 段落的位置
    'document_id': fields.String,  # 文档的唯一标识符
    'content': fields.String,  # 段落的内容
    'answer': fields.String,  # 相关的答案
    'word_count': fields.Integer,  # 段落中的单词数量
    'tokens': fields.Integer,  # 段落中的标记数量
    'keywords': fields.List(fields.String),  # 段落的关键词列表
    'index_node_id': fields.String,  # 索引节点的唯一标识符
    'index_node_hash': fields.String,  # 索引节点的哈希值
    'hit_count': fields.Integer,  # 搜索命中的次数
    'enabled': fields.Boolean,  # 段落是否启用
    'disabled_at': TimestampField,  # 段落被禁用的时间戳
    'disabled_by': fields.String,  # 禁用段落的用户标识
    'status': fields.String,  # 段落的状态
    'created_by': fields.String,  # 创建段落的用户标识
    'created_at': TimestampField,  # 段落创建的时间戳
    'indexing_at': TimestampField,  # 段落索引开始的时间戳
    'completed_at': TimestampField,  # 段落索引完成的时间戳
    'error': fields.String,  # 索引过程中的错误信息
    'stopped_at': TimestampField  # 段落索引停止的时间戳
}

# 定义段落列表响应的结构，用于API响应
segment_list_response = {
    'data': fields.List(fields.Nested(segment_fields)),  # 段落数据列表
    'has_more': fields.Boolean,  # 是否还有更多的段落数据
    'limit': fields.Integer  # 返回数据的限制数量
}