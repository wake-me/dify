from flask_login import current_user
from flask_restful import fields, marshal_with, reqparse
from flask_restful.inputs import int_range
from werkzeug.exceptions import NotFound

from controllers.console import api
from controllers.console.explore.error import NotCompletionAppError
from controllers.console.explore.wraps import InstalledAppResource
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

class SavedMessageListApi(InstalledAppResource):
    # 定义无限滚动分页字段
    saved_message_infinite_scroll_pagination_fields = {
        'limit': fields.Integer,  # 请求限制的数量
        'has_more': fields.Boolean,  # 是否还有更多数据
        'data': fields.List(fields.Nested(message_fields))  # 数据列表
    }

    @marshal_with(saved_message_infinite_scroll_pagination_fields)
    def get(self, installed_app):
        """
        获取已保存消息的分页列表

        :param installed_app: 已安装的应用对象
        :return: 根据last_id和limit分页获取的已保存消息列表
        """
        app_model = installed_app.app
        # 检查应用模式是否为完成模式
        if app_model.mode != 'completion':
            raise NotCompletionAppError()

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('last_id', type=uuid_value, location='args')
        parser.add_argument('limit', type=int_range(1, 100), required=False, default=20, location='args')
        args = parser.parse_args()

        # 根据last_id和limit进行分页查询
        return SavedMessageService.pagination_by_last_id(app_model, current_user, args['last_id'], args['limit'])

    def post(self, installed_app):
        """
        保存一条消息

        :param installed_app: 已安装的应用对象
        :return: 保存结果
        """
        app_model = installed_app.app
        # 检查应用模式是否为完成模式
        if app_model.mode != 'completion':
            raise NotCompletionAppError()

        # 解析请求体参数
        parser = reqparse.RequestParser()
        parser.add_argument('message_id', type=uuid_value, required=True, location='json')
        args = parser.parse_args()

        try:
            # 尝试保存消息
            SavedMessageService.save(app_model, current_user, args['message_id'])
        except MessageNotExistsError:
            # 如果消息不存在，则抛出404异常
            raise NotFound("Message Not Exists.")

        return {'result': 'success'}


class SavedMessageApi(InstalledAppResource):
    """
    提供已保存消息的API接口。
    
    方法:
    delete: 删除指定的消息。
    
    参数:
    installed_app: 安装的应用对象，用于获取应用相关信息。
    message_id: 消息的唯一标识符，用于指定要删除的消息。
    
    返回值:
    返回一个包含结果信息的字典，例如 {'result': 'success'}。
    """
    
    def delete(self, installed_app, message_id):
        # 转换消息ID为字符串格式
        app_model = installed_app.app
        message_id = str(message_id)

        # 检查应用是否为完成模式，如果不是则抛出异常
        if app_model.mode != 'completion':
            raise NotCompletionAppError()

        # 调用服务层方法，删除指定的消息
        SavedMessageService.delete(app_model, current_user, message_id)

        # 返回删除成功的结果
        return {'result': 'success'}


api.add_resource(SavedMessageListApi, '/installed-apps/<uuid:installed_app_id>/saved-messages', endpoint='installed_app_saved_messages')
api.add_resource(SavedMessageApi, '/installed-apps/<uuid:installed_app_id>/saved-messages/<uuid:message_id>', endpoint='installed_app_saved_message')
