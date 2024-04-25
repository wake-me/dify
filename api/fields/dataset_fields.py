from flask_restful import fields

from libs.helper import TimestampField

# 定义数据集字段
dataset_fields = {
    'id': fields.String,  # 数据集ID
    'name': fields.String,  # 数据集名称
    'description': fields.String,  # 数据集描述
    'permission': fields.String,  # 数据集权限
    'data_source_type': fields.String,  # 数据源类型
    'indexing_technique': fields.String,  # 索引技术
    'created_by': fields.String,  # 创建者
    'created_at': TimestampField,  # 创建时间
}

# 定义重排模型字段
reranking_model_fields = {
    'reranking_provider_name': fields.String,  # 重排模型提供者名称
    'reranking_model_name': fields.String  # 重排模型名称
}

# 定义数据集检索模型字段
dataset_retrieval_model_fields = {
    'search_method': fields.String,  # 检索方法
    'reranking_enable': fields.Boolean,  # 是否启用重排
    'reranking_model': fields.Nested(reranking_model_fields),  # 重排模型详情
    'top_k': fields.Integer,  # 返回结果数量
    'score_threshold_enabled': fields.Boolean,  # 是否启用得分阈值
    'score_threshold': fields.Float  # 得分阈值
}

tag_fields = {
    'id': fields.String,
    'name': fields.String,
    'type': fields.String
}

dataset_detail_fields = {
    'id': fields.String,
    'name': fields.String,
    'description': fields.String,
    'provider': fields.String,
    'permission': fields.String,
    'data_source_type': fields.String,
    'indexing_technique': fields.String,
    'app_count': fields.Integer,
    'document_count': fields.Integer,
    'word_count': fields.Integer,
    'created_by': fields.String,
    'created_at': TimestampField,
    'updated_by': fields.String,
    'updated_at': TimestampField,
    'embedding_model': fields.String,
    'embedding_model_provider': fields.String,
    'embedding_available': fields.Boolean,
    'retrieval_model_dict': fields.Nested(dataset_retrieval_model_fields),
    'tags': fields.List(fields.Nested(tag_fields))
}

# 定义数据集查询详细信息字段
dataset_query_detail_fields = {
    "id": fields.String,  # 查询ID
    "content": fields.String,  # 查询内容
    "source": fields.String,  # 查询来源
    "source_app_id": fields.String,  # 来源应用ID
    "created_by_role": fields.String,  # 创建者角色
    "created_by": fields.String,  # 创建者
    "created_at": TimestampField  # 创建时间
}


