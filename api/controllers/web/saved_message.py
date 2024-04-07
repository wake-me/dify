from flask_restful import fields, marshal_with, reqparse
from flask_restful.inputs import int_range
from werkzeug.exceptions import NotFound

from controllers.web import api
from controllers.web.error import NotCompletionAppError
from controllers.web.wraps import WebApiResource
from fields.conversation_fields import message_file_fields
from libs.helper import TimestampField, uuid_value
from services.errors.message import MessageNotExistsError
from services.saved_message_service import SavedMessageService

# 定义反馈信息的字段结构
feedback_fields = {
    'rating': fields.String  # 评分字段，类型为字符串
}

# 定义消息的字段结构
message_fields = {
    'id': fields.String,  # 消息ID，类型为字符串
    'inputs': fields.Raw,  # 输入信息，原始格式
    'query': fields.String,  # 查询内容，类型为字符串
    'answer': fields.String,  # 回答内容，类型为字符串
    'message_files': fields.List(  # 消息附件列表，每个附件信息嵌套在message_file_fields定义的结构中
        fields.Nested(message_file_fields, attribute='files'),
    ),
    'feedback': fields.Nested(  # 用户反馈信息，嵌套在feedback_fields定义的结构中，可以为空
        feedback_fields, attribute='user_feedback', allow_null=True
    ),
    'created_at': TimestampField  # 创建时间戳字段
}


class SavedMessageListApi(WebApiResource):
    # 定义无限滚动分页字段
    saved_message_infinite_scroll_pagination_fields = {
        'limit': fields.Integer,  # 请求限制的数量
        'has_more': fields.Boolean,  # 是否还有更多数据
        'data': fields.List(fields.Nested(message_fields))  # 数据列表，嵌套消息字段
    }

    @marshal_with(saved_message_infinite_scroll_pagination_fields)
    def get(self, app_model, end_user):
        """
        获取保存的消息列表，支持无限滚动分页。

        参数:
        - app_model: 应用模型，用于判断应用模式。
        - end_user: 终端用户信息。

        返回值:
        - 分页后的消息列表数据。

        异常:
        - NotCompletionAppError: 如果应用模式不是'completion'，则抛出异常。
        """
        # 检查应用模式是否为'completion'
        if app_model.mode != 'completion':
            raise NotCompletionAppError()

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('last_id', type=uuid_value, location='args')
        parser.add_argument('limit', type=int_range(1, 100), required=False, default=20, location='args')
        args = parser.parse_args()

        # 根据last_id和limit进行分页查询
        return SavedMessageService.pagination_by_last_id(app_model, end_user, args['last_id'], args['limit'])

    def post(self, app_model, end_user):
        """
        保存一条消息。

        参数:
        - app_model: 应用模型，用于判断应用模式。
        - end_user: 终端用户信息。

        返回值:
        - {'result': 'success'}，表示保存成功。

        异常:
        - NotCompletionAppError: 如果应用模式不是'completion'，则抛出异常。
        - NotFound: 如果消息不存在，则抛出异常。
        """
        # 检查应用模式是否为'completion'
        if app_model.mode != 'completion':
            raise NotCompletionAppError()

        # 解析请求体参数
        parser = reqparse.RequestParser()
        parser.add_argument('message_id', type=uuid_value, required=True, location='json')
        args = parser.parse_args()

        try:
            # 尝试保存消息
            SavedMessageService.save(app_model, end_user, args['message_id'])
        except MessageNotExistsError:
            # 如果消息不存在，则抛出异常
            raise NotFound("Message Not Exists.")

        return {'result': 'success'}


class SavedMessageApi(WebApiResource):
    """
    SavedMessageApi类，继承自WebApiResource，用于处理消息删除的API请求。

    方法:
    - delete: 删除特定应用模型、终端用户和消息ID的消息。
    """

    def delete(self, app_model, end_user, message_id):
        """
        删除指定应用模型、终端用户和消息ID的消息。

        参数:
        - app_model: 应用模型对象，包含应用的相关信息。
        - end_user: 终端用户标识，用于指定消息的接收方。
        - message_id: 消息ID，唯一标识要删除的消息。

        返回值:
        - 字典，包含删除操作的结果信息，默认为{'result': 'success'}。
        """

        message_id = str(message_id)  # 确保消息ID为字符串格式

        # 检查应用模型的模式是否为'completion'，如果不是，则抛出异常
        if app_model.mode != 'completion':
            raise NotCompletionAppError()

        # 调用SavedMessageService的服务方法，执行实际的消息删除操作
        SavedMessageService.delete(app_model, end_user, message_id)

        # 返回删除成功的结果信息
        return {'result': 'success'}


api.add_resource(SavedMessageListApi, '/saved-messages')
api.add_resource(SavedMessageApi, '/saved-messages/<uuid:message_id>')
