from flask_restful import fields

from libs.helper import TimestampField

# 定义文档和段落字段的结构，用于序列化和反序列化数据。

# document_fields 定义了文档级别的字段
document_fields = {
    "id": fields.String,
    "data_source_type": fields.String,
    "name": fields.String,
    "doc_type": fields.String,
}

# segment_fields 定义了文档中段落级别的字段
segment_fields = {
    "id": fields.String,
    "position": fields.Integer,
    "document_id": fields.String,
    "content": fields.String,
    "answer": fields.String,
    "word_count": fields.Integer,
    "tokens": fields.Integer,
    "keywords": fields.List(fields.String),
    "index_node_id": fields.String,
    "index_node_hash": fields.String,
    "hit_count": fields.Integer,
    "enabled": fields.Boolean,
    "disabled_at": TimestampField,
    "disabled_by": fields.String,
    "status": fields.String,
    "created_by": fields.String,
    "created_at": TimestampField,
    "indexing_at": TimestampField,
    "completed_at": TimestampField,
    "error": fields.String,
    "stopped_at": TimestampField,
    "document": fields.Nested(document_fields),
}

# hit_testing_record_fields 定义了击中测试记录的字段
hit_testing_record_fields = {
    "segment": fields.Nested(segment_fields),
    "score": fields.Float,
    "tsne_position": fields.Raw,
}
