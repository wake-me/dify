from flask_restful import fields

from fields.dataset_fields import dataset_fields
from libs.helper import TimestampField

# 定义文档字段的结构
document_fields = {
    'id': fields.String,  # 文档ID
    'position': fields.Integer,  # 文档位置
    'data_source_type': fields.String,  # 数据源类型
    'data_source_info': fields.Raw(attribute='data_source_info_dict'),  # 数据源信息
    'dataset_process_rule_id': fields.String,  # 数据集处理规则ID
    'name': fields.String,  # 文档名称
    'created_from': fields.String,  # 创建来源
    'created_by': fields.String,  # 创建者
    'created_at': TimestampField,  # 创建时间
    'tokens': fields.Integer,  # 令牌数
    'indexing_status': fields.String,  # 索引状态
    'error': fields.String,  # 错误信息
    'enabled': fields.Boolean,  # 是否启用
    'disabled_at': TimestampField,  # 禁用时间
    'disabled_by': fields.String,  # 禁用者
    'archived': fields.Boolean,  # 是否归档
    'display_status': fields.String,  # 显示状态
    'word_count': fields.Integer,  # 单词数
    'hit_count': fields.Integer,  # 访问次数
    'doc_form': fields.String,  # 文档形式
}

# 定义包含段落信息的文档字段结构
document_with_segments_fields = {
    'id': fields.String,  # 文档ID
    'position': fields.Integer,  # 文档位置
    'data_source_type': fields.String,  # 数据源类型
    'data_source_info': fields.Raw(attribute='data_source_info_dict'),  # 数据源信息
    'dataset_process_rule_id': fields.String,  # 数据集处理规则ID
    'name': fields.String,  # 文档名称
    'created_from': fields.String,  # 创建来源
    'created_by': fields.String,  # 创建者
    'created_at': TimestampField,  # 创建时间
    'tokens': fields.Integer,  # 令牌数
    'indexing_status': fields.String,  # 索引状态
    'error': fields.String,  # 错误信息
    'enabled': fields.Boolean,  # 是否启用
    'disabled_at': TimestampField,  # 禁用时间
    'disabled_by': fields.String,  # 禁用者
    'archived': fields.Boolean,  # 是否归档
    'display_status': fields.String,  # 显示状态
    'word_count': fields.Integer,  # 单词数
    'hit_count': fields.Integer,  # 访问次数
    'completed_segments': fields.Integer,  # 完成的段落数
    'total_segments': fields.Integer  # 总段落数
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