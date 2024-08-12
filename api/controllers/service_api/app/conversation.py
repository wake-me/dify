from flask_restful import Resource, marshal_with, reqparse
from flask_restful.inputs import int_range
from werkzeug.exceptions import NotFound

import services
from controllers.service_api import api
from controllers.service_api.app.error import NotChatAppError
from controllers.service_api.wraps import FetchUserArg, WhereisUserArg, validate_app_token
from core.app.entities.app_invoke_entities import InvokeFrom
from fields.conversation_fields import conversation_infinite_scroll_pagination_fields, simple_conversation_fields
from libs.helper import uuid_value
from models.model import App, AppMode, EndUser
from services.conversation_service import ConversationService


class ConversationApi(Resource):
    """
    对话API类，用于提供与对话相关的RESTful接口。

    Attributes:
        Resource: 继承自Flask-RESTful库中的Resource类，用于创建RESTful API资源。
    """

    @validate_app_token(fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.QUERY))
    @marshal_with(conversation_infinite_scroll_pagination_fields)
    def get(self, app_model: App, end_user: EndUser):
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in [AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT]:
            raise NotChatAppError()

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('last_id', type=uuid_value, location='args')  # 最后一条对话的ID
        parser.add_argument('limit', type=int_range(1, 100), required=False, default=20, location='args')  # 获取的对话数量限制
        args = parser.parse_args()

        try:
            return ConversationService.pagination_by_last_id(
                app_model=app_model,
                user=end_user,
                last_id=args['last_id'],
                limit=args['limit'],
                invoke_from=InvokeFrom.SERVICE_API
            )
        except services.errors.conversation.LastConversationNotExistsError:
            # 如果最后一条对话不存在，则抛出404错误
            raise NotFound("Last Conversation Not Exists.")


class ConversationDetailApi(Resource):
    """
    对话详情API接口类，用于处理与对话详情相关的RESTful请求。
    
    Attributes:
        Resource: 继承自Flask-RESTful库的Resource类，用于创建RESTful API资源。
    """
    
    @validate_app_token(fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.JSON))
    @marshal_with(simple_conversation_fields)
    def delete(self, app_model: App, end_user: EndUser, c_id):
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in [AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT]:
            raise NotChatAppError()

        conversation_id = str(c_id)  # 将对话ID转换为字符串格式

        try:
            # 尝试删除指定的对话记录
            ConversationService.delete(app_model, conversation_id, end_user)
        except services.errors.conversation.ConversationNotExistsError:
            # 如果对话不存在，则抛出404错误
            raise NotFound("Conversation Not Exists.")
        return {'result': 'success'}, 200


class ConversationRenameApi(Resource):
    """
    用于会话重命名的API接口类。
    
    方法:
    - post: 用于更改会话的名称。
    
    参数:
    - app_model: 应用模型，包含应用的相关信息。
    - end_user: 终端用户信息。
    - c_id: 会话的ID。
    
    返回值:
    - 修改后的会话信息。
    """

    @validate_app_token(fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.JSON))
    @marshal_with(simple_conversation_fields)
    def post(self, app_model: App, end_user: EndUser, c_id):
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in [AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT]:
            raise NotChatAppError()

        conversation_id = str(c_id)  # 将会话ID转换为字符串格式

        parser = reqparse.RequestParser()  # 创建请求解析器
        parser.add_argument('name', type=str, required=False, location='json')  # 添加名称参数
        parser.add_argument('auto_generate', type=bool, required=False, default=False, location='json')  # 添加是否自动生成参数
        args = parser.parse_args()  # 解析请求参数

        try:
            return ConversationService.rename(
                app_model,
                conversation_id,
                end_user,
                args['name'],
                args['auto_generate']
            )  # 尝试重命名会话并返回结果
        except services.errors.conversation.ConversationNotExistsError:
            raise NotFound("Conversation Not Exists.")  # 如果会话不存在，则抛出异常


api.add_resource(ConversationRenameApi, '/conversations/<uuid:c_id>/name', endpoint='conversation_name')
api.add_resource(ConversationApi, '/conversations')
api.add_resource(ConversationDetailApi, '/conversations/<uuid:c_id>', endpoint='conversation_detail')
