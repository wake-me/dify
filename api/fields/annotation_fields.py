from flask_restful import fields

from libs.helper import TimestampField

annotation_fields = {
    "id": fields.String,
    "question": fields.String,
    "answer": fields.Raw(attribute='content'),
    "hit_count": fields.Integer,
    "created_at": TimestampField,
    # 'account': fields.Nested(simple_account_fields, allow_null=True)
}

# 定义注解列表的字段结构
annotation_list_fields = {
    "data": fields.List(fields.Nested(annotation_fields)),  # 注解数据列表
}

# 定义注解命中历史的字段结构
annotation_hit_history_fields = {
    "id": fields.String,  # 命中ID
    "source": fields.String,  # 数据源
    "score": fields.Float,  # 命中得分
    "question": fields.String,  # 命中问题
    "created_at": TimestampField,  # 命中时间
    "match": fields.String(attribute='annotation_question'),  # 匹配的注解问题
    "response": fields.String(attribute='annotation_content')  # 响应的注解内容
}

# 定义注解命中历史列表的字段结构
annotation_hit_history_list_fields = {
    "data": fields.List(fields.Nested(annotation_hit_history_fields)),  # 注解命中历史数据列表
}