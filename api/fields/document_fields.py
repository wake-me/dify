from flask_restful import fields

from fields.dataset_fields import dataset_fields
from libs.helper import TimestampField

# 定义文档字段的结构
document_fields = {
    'id': fields.String,
    'position': fields.Integer,
    'data_source_type': fields.String,
    'data_source_info': fields.Raw(attribute='data_source_info_dict'),
    'data_source_detail_dict': fields.Raw(attribute='data_source_detail_dict'),
    'dataset_process_rule_id': fields.String,
    'name': fields.String,
    'created_from': fields.String,
    'created_by': fields.String,
    'created_at': TimestampField,
    'tokens': fields.Integer,
    'indexing_status': fields.String,
    'error': fields.String,
    'enabled': fields.Boolean,
    'disabled_at': TimestampField,
    'disabled_by': fields.String,
    'archived': fields.Boolean,
    'display_status': fields.String,
    'word_count': fields.Integer,
    'hit_count': fields.Integer,
    'doc_form': fields.String,
}

# 定义包含段落信息的文档字段结构
document_with_segments_fields = {
    'id': fields.String,
    'position': fields.Integer,
    'data_source_type': fields.String,
    'data_source_info': fields.Raw(attribute='data_source_info_dict'),
    'data_source_detail_dict': fields.Raw(attribute='data_source_detail_dict'),
    'dataset_process_rule_id': fields.String,
    'name': fields.String,
    'created_from': fields.String,
    'created_by': fields.String,
    'created_at': TimestampField,
    'tokens': fields.Integer,
    'indexing_status': fields.String,
    'error': fields.String,
    'enabled': fields.Boolean,
    'disabled_at': TimestampField,
    'disabled_by': fields.String,
    'archived': fields.Boolean,
    'display_status': fields.String,
    'word_count': fields.Integer,
    'hit_count': fields.Integer,
    'completed_segments': fields.Integer,
    'total_segments': fields.Integer
}

# 定义数据集和文档的字段结构
dataset_and_document_fields = {
    'dataset': fields.Nested(dataset_fields),  # 数据集信息
    'documents': fields.List(fields.Nested(document_fields)),  # 文档列表
    'batch': fields.String  # 批次信息
}

# 定义文档状态的字段结构
document_status_fields = {
    'id': fields.String,  # 文档ID
    'indexing_status': fields.String,  # 索引状态
    'processing_started_at': TimestampField,  # 处理开始时间
    'parsing_completed_at': TimestampField,  # 解析完成时间
    'cleaning_completed_at': TimestampField,  # 清理完成时间
    'splitting_completed_at': TimestampField,  # 切分完成时间
    'completed_at': TimestampField,  # 完成时间
    'paused_at': TimestampField,  # 暂停时间
    'error': fields.String,  # 错误信息
    'stopped_at': TimestampField,  # 停止时间
    'completed_segments': fields.Integer,  # 完成的段落数
    'total_segments': fields.Integer  # 总段落数
}

# 定义文档状态列表的字段结构
document_status_fields_list = {
    'data': fields.List(fields.Nested(document_status_fields))  # 文档状态列表
}