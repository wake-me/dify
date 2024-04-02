from flask_restful import fields

from libs.helper import TimestampField

# 定义文档和段落字段的结构，用于序列化和反序列化数据。

# document_fields 定义了文档级别的字段
document_fields = {
    'id': fields.String,  # 文档唯一标识符
    'data_source_type': fields.String,  # 数据源类型
    'name': fields.String,  # 文档名称
    'doc_type': fields.String,  # 文档类型
}

# segment_fields 定义了文档中段落级别的字段
segment_fields = {
    'id': fields.String,  # 段落唯一标识符
    'position': fields.Integer,  # 段落位置
    'document_id': fields.String,  # 所属文档的唯一标识符
    'content': fields.String,  # 段落内容
    'answer': fields.String,  # 段落的解答或关键信息
    'word_count': fields.Integer,  # 段落中的单词数量
    'tokens': fields.Integer,  # 段落中的标记数量
    'keywords': fields.List(fields.String),  # 段落的关键词列表
    'index_node_id': fields.String,  # 索引节点标识符
    'index_node_hash': fields.String,  # 索引节点哈希值
    'hit_count': fields.Integer,  # 段落被命中的次数
    'enabled': fields.Boolean,  # 段落是否启用
    'disabled_at': TimestampField,  # 段落被禁用的时间戳
    'disabled_by': fields.String,  # 段落被禁用的执行者
    'status': fields.String,  # 段落的状态
    'created_by': fields.String,  # 创建段落的用户
    'created_at': TimestampField,  # 段落创建的时间戳
    'indexing_at': TimestampField,  # 段落索引开始的时间戳
    'completed_at': TimestampField,  # 段落索引完成的时间戳
    'error': fields.String,  # 段落索引过程中的错误信息
    'stopped_at': TimestampField,  # 段落索引停止的时间戳
    'document': fields.Nested(document_fields),  # 包含文档的嵌套字段
}

# hit_testing_record_fields 定义了击中测试记录的字段
hit_testing_record_fields = {
    'segment': fields.Nested(segment_fields),  # 包含段落信息的嵌套字段
    'score': fields.Float,  # 测试得分
    'tsne_position': fields.Raw  # t-SNE（t-Distributed Stochastic Neighbor Embedding）位置数据，用于可视化
}