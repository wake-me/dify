from flask_login import current_user
from flask_restful import marshal_with, reqparse
from flask_restful.inputs import int_range
from werkzeug.exceptions import NotFound

from controllers.console import api
from controllers.console.explore.error import NotChatAppError
from controllers.console.explore.wraps import InstalledAppResource
from core.app.entities.app_invoke_entities import InvokeFrom
from fields.conversation_fields import conversation_infinite_scroll_pagination_fields, simple_conversation_fields
from libs.helper import uuid_value
from models.model import AppMode
from services.conversation_service import ConversationService
from services.errors.conversation import ConversationNotExistsError, LastConversationNotExistsError
from services.web_conversation_service import WebConversationService


class ConversationListApi(InstalledAppResource):
    @marshal_with(conversation_infinite_scroll_pagination_fields)
    def get(self, installed_app):
        """
        处理GET请求，根据参数获取对话列表。
        
        参数:
        - installed_app: 已安装的应用对象。
        
        返回:
        - 根据请求参数进行分页和筛选后的对话列表。
        """
        app_model = installed_app.app
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in [AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT]:
            raise NotChatAppError()

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument("last_id", type=uuid_value, location="args")
        parser.add_argument("limit", type=int_range(1, 100), required=False, default=20, location="args")
        parser.add_argument("pinned", type=str, choices=["true", "false", None], location="args")
        args = parser.parse_args()

        # 解析并处理"pinned"参数
        pinned = None
        if "pinned" in args and args["pinned"] is not None:
            pinned = True if args["pinned"] == "true" else False

        try:
            # 根据参数进行对话分页查询
            return WebConversationService.pagination_by_last_id(
                app_model=app_model,
                user=current_user,
                last_id=args["last_id"],
                limit=args["limit"],
                invoke_from=InvokeFrom.EXPLORE,
                pinned=pinned,
            )
        except LastConversationNotExistsError:
            # 处理未找到最后一条对话的情况
            raise NotFound("Last Conversation Not Exists.")

class ConversationApi(InstalledAppResource):
    """
    会话API类，提供删除会话的功能。

    参数:
    - installed_app: 安装的应用对象，用于获取应用相关信息。
    - c_id: 会话的ID，需要转换为字符串格式。

    返回值:
    - 删除会话成功则返回一个包含结果信息的字典和HTTP状态码204。
    - 如果会话不存在或应用不是聊天模式，则抛出相应的异常。
    """

    def delete(self, installed_app, c_id):
        # 校验应用是否为聊天模式
        app_model = installed_app.app
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in [AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT]:
            raise NotChatAppError()

        conversation_id = str(c_id)
        try:
            # 尝试删除会话
            ConversationService.delete(app_model, conversation_id, current_user)
        except ConversationNotExistsError:
            # 如果会话不存在，抛出404异常
            raise NotFound("Conversation Not Exists.")
        # 解除会话的固定状态
        WebConversationService.unpin(app_model, conversation_id, current_user)

        # 返回删除成功的信息
        return {"result": "success"}, 204


class ConversationRenameApi(InstalledAppResource):
    @marshal_with(simple_conversation_fields)
    def post(self, installed_app, c_id):
        # 获取应用模型，并检查应用模式是否为聊天模式
        app_model = installed_app.app
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in [AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT]:
            raise NotChatAppError()

        conversation_id = str(c_id)  # 将会话ID转换为字符串格式

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument("name", type=str, required=False, location="json")
        parser.add_argument("auto_generate", type=bool, required=False, default=False, location="json")
        args = parser.parse_args()

        try:
            # 调用服务层方法进行会话重命名操作
            return ConversationService.rename(
                app_model, conversation_id, current_user, args["name"], args["auto_generate"]
            )
        except ConversationNotExistsError:
            # 若会话不存在，则抛出未找到错误
            raise NotFound("Conversation Not Exists.")


class ConversationPinApi(InstalledAppResource):
    def patch(self, installed_app, c_id):
        app_model = installed_app.app
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in [AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT]:
            raise NotChatAppError()

        conversation_id = str(c_id)  # 将会话ID转换为字符串格式

        try:
            # 尝试将指定的会话置顶
            WebConversationService.pin(app_model, conversation_id, current_user)
        except ConversationNotExistsError:
            # 如果会话不存在，则抛出未找到错误
            raise NotFound("Conversation Not Exists.")

        return {"result": "success"}  # 返回操作成功的结果


class ConversationUnPinApi(InstalledAppResource):
    """
    对话取消固定API类，用于处理应用安装后的对话取消固定请求。
    
    参数:
    - installed_app: 安装的应用对象，用于获取应用相关信息。
    - c_id: 对话的ID，需要转换为字符串格式。
    
    返回值:
    - 返回一个包含结果信息的字典，例如 {"result": "success"}。
    """
    
    def patch(self, installed_app, c_id):
        # 获取关联的应用模型
        app_model = installed_app.app
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in [AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT]:
            raise NotChatAppError()

        # 将对话ID转换为字符串格式
        conversation_id = str(c_id)
        
        # 调用服务层方法，取消对话的固定状态
        WebConversationService.unpin(app_model, conversation_id, current_user)

        # 返回操作成功的标志
        return {"result": "success"}


api.add_resource(
    ConversationRenameApi,
    "/installed-apps/<uuid:installed_app_id>/conversations/<uuid:c_id>/name",
    endpoint="installed_app_conversation_rename",
)
api.add_resource(
    ConversationListApi, "/installed-apps/<uuid:installed_app_id>/conversations", endpoint="installed_app_conversations"
)
api.add_resource(
    ConversationApi,
    "/installed-apps/<uuid:installed_app_id>/conversations/<uuid:c_id>",
    endpoint="installed_app_conversation",
)
api.add_resource(
    ConversationPinApi,
    "/installed-apps/<uuid:installed_app_id>/conversations/<uuid:c_id>/pin",
    endpoint="installed_app_conversation_pin",
)
api.add_resource(
    ConversationUnPinApi,
    "/installed-apps/<uuid:installed_app_id>/conversations/<uuid:c_id>/unpin",
    endpoint="installed_app_conversation_unpin",
)
