from flask_restful import marshal_with, reqparse
from flask_restful.inputs import int_range
from werkzeug.exceptions import NotFound

from controllers.web import api
from controllers.web.error import NotChatAppError
from controllers.web.wraps import WebApiResource
from core.app.entities.app_invoke_entities import InvokeFrom
from fields.conversation_fields import conversation_infinite_scroll_pagination_fields, simple_conversation_fields
from libs.helper import uuid_value
from models.model import AppMode
from services.conversation_service import ConversationService
from services.errors.conversation import ConversationNotExistsError, LastConversationNotExistsError
from services.web_conversation_service import WebConversationService


class ConversationListApi(WebApiResource):
    """
    对话列表API，用于获取对话列表的接口。

    参数:
    - app_model: 应用模型，用于判断应用模式是否为聊天模式。
    - end_user: 终端用户，指定请求的用户。

    返回值:
    - 根据请求参数进行分页获取的对话列表信息。
    """

    @marshal_with(conversation_infinite_scroll_pagination_fields)
    def get(self, app_model, end_user):
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in [AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT]:
            raise NotChatAppError()

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('last_id', type=uuid_value, location='args')
        parser.add_argument('limit', type=int_range(1, 100), required=False, default=20, location='args')
        parser.add_argument('pinned', type=str, choices=['true', 'false', None], location='args')
        args = parser.parse_args()

        # 处理"Pinned"请求参数，转换为布尔值
        pinned = None
        if 'pinned' in args and args['pinned'] is not None:
            pinned = True if args['pinned'] == 'true' else False

        try:
            # 根据请求参数进行分页查询对话列表
            return WebConversationService.pagination_by_last_id(
                app_model=app_model,
                user=end_user,
                last_id=args['last_id'],
                limit=args['limit'],
                invoke_from=InvokeFrom.WEB_APP,
                pinned=pinned,
            )
        except LastConversationNotExistsError:
            # 如果查询不到最后的对话记录，抛出404异常
            raise NotFound("Last Conversation Not Exists.")

class ConversationApi(WebApiResource):
    """
    会话接口类，用于处理会话相关的API请求

    方法:
    delete: 删除特定的会话
    """

    def delete(self, app_model, end_user, c_id):
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in [AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT]:
            raise NotChatAppError()

        conversation_id = str(c_id)  # 转换会话ID为字符串格式

        try:
            # 尝试删除会话
            ConversationService.delete(app_model, conversation_id, end_user)
        except ConversationNotExistsError:
            # 如果会话不存在，抛出404异常
            raise NotFound("Conversation Not Exists.")
        # 解除会话的固定状态
        WebConversationService.unpin(app_model, conversation_id, end_user)

        # 返回删除成功的消息
        return {"result": "success"}, 204


class ConversationRenameApi(WebApiResource):
    """
    会话重命名API类，提供通过POST请求来重命名会话的功能。

    参数:
    - app_model: 应用模型，用于确定当前应用的配置和模式。
    - end_user: 终端用户信息，标识请求的用户。
    - c_id: 会话ID，需要被重命名的会话的标识符。

    返回值:
    - 返回重命名会话的操作结果。
    """

    @marshal_with(simple_conversation_fields)
    def post(self, app_model, end_user, c_id):
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in [AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT]:
            raise NotChatAppError()

        conversation_id = str(c_id)

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('name', type=str, required=False, location='json')
        parser.add_argument('auto_generate', type=bool, required=False, default=False, location='json')
        args = parser.parse_args()

        try:
            # 调用服务层方法，尝试重命名会话
            return ConversationService.rename(
                app_model,
                conversation_id,
                end_user,
                args['name'],
                args['auto_generate']
            )
        except ConversationNotExistsError:
            # 如果会话不存在，抛出404错误
            raise NotFound("Conversation Not Exists.")


class ConversationPinApi(WebApiResource):
    """
    对话置顶API接口类

    方法:
    patch: 根据提供的应用模型、终端用户和对话ID，将指定对话置顶
    """

    def patch(self, app_model, end_user, c_id):
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in [AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT]:
            raise NotChatAppError()

        conversation_id = str(c_id)  # 转换对话ID为字符串格式

        try:
            # 尝试将指定对话置顶
            WebConversationService.pin(app_model, conversation_id, end_user)
        except ConversationNotExistsError:
            # 如果对话不存在，抛出异常
            raise NotFound("Conversation Not Exists.")

        return {"result": "success"}  # 返回操作成功的结果


class ConversationUnPinApi(WebApiResource):
    """
    对话取消固定API接口类

    方法：
    patch: 根据提供的应用模型、终端用户和对话ID，取消对该对话的固定状态。

    参数：
    app_model: 应用模型对象，包含应用的相关信息，例如应用的模式。
    end_user: 终端用户信息，标识请求的用户。
    c_id: 对话的ID，用于标识需要取消固定的对话。

    返回值：
    返回一个包含结果信息的字典，例如 {"result": "success"}。
    """

    def patch(self, app_model, end_user, c_id):
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in [AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT]:
            raise NotChatAppError()

        conversation_id = str(c_id)  # 将对话ID转换为字符串格式
        # 调用WebConversationService的服务，取消对话的固定状态
        WebConversationService.unpin(app_model, conversation_id, end_user)

        return {"result": "success"}  # 返回操作成功的标志


api.add_resource(ConversationRenameApi, '/conversations/<uuid:c_id>/name', endpoint='web_conversation_name')
api.add_resource(ConversationListApi, '/conversations')
api.add_resource(ConversationApi, '/conversations/<uuid:c_id>')
api.add_resource(ConversationPinApi, '/conversations/<uuid:c_id>/pin')
api.add_resource(ConversationUnPinApi, '/conversations/<uuid:c_id>/unpin')
