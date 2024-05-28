import logging

from flask_restful import Resource, fields, marshal_with, reqparse
from flask_restful.inputs import int_range
from werkzeug.exceptions import BadRequest, InternalServerError, NotFound

import services
from controllers.service_api import api
from controllers.service_api.app.error import NotChatAppError
from controllers.service_api.wraps import FetchUserArg, WhereisUserArg, validate_app_token
from core.app.entities.app_invoke_entities import InvokeFrom
from fields.conversation_fields import message_file_fields
from libs.helper import TimestampField, uuid_value
from models.model import App, AppMode, EndUser
from services.errors.message import SuggestedQuestionsAfterAnswerDisabledError
from services.message_service import MessageService


class MessageListApi(Resource):
    # 定义反馈信息的字段结构
    feedback_fields = {
        'rating': fields.String  # 评分，以字符串形式存储
    }

    # 定义检索结果资源的字段结构
    retriever_resource_fields = {
        'id': fields.String,  # 唯一标识符
        'message_id': fields.String,  # 消息ID
        'position': fields.Integer,  # 位置信息
        'dataset_id': fields.String,  # 数据集ID
        'dataset_name': fields.String,  # 数据集名称
        'document_id': fields.String,  # 文档ID
        'document_name': fields.String,  # 文档名称
        'data_source_type': fields.String,  # 数据源类型
        'segment_id': fields.String,  # 片段ID
        'score': fields.Float,  # 得分
        'hit_count': fields.Integer,  # 命中次数
        'word_count': fields.Integer,  # 单元词数
        'segment_position': fields.Integer,  # 片段位置
        'index_node_hash': fields.String,  # 索引节点哈希值
        'content': fields.String,  # 内容
        'created_at': TimestampField  # 创建时间戳
    }

    # 定义代理思考的字段结构
    agent_thought_fields = {
        'id': fields.String,  # 唯一标识符
        'chain_id': fields.String,  # 链ID
        'message_id': fields.String,  # 消息ID
        'position': fields.Integer,  # 位置信息
        'thought': fields.String,  # 思考内容
        'tool': fields.String,  # 使用的工具
        'tool_labels': fields.Raw,  # 工具标签，原始格式
        'tool_input': fields.String,  # 工具输入
        'created_at': TimestampField,  # 创建时间戳
        'observation': fields.String,  # 观察结果
        'message_files': fields.List(fields.String, attribute='files')  # 消息关联的文件列表
    }

        # 定义消息对象的字段
    message_fields = {
        'id': fields.String,
        'conversation_id': fields.String,
        'inputs': fields.Raw,
        'query': fields.String,
        'answer': fields.String(attribute='re_sign_file_url_answer'),
        'message_files': fields.List(fields.Nested(message_file_fields), attribute='files'),
        'feedback': fields.Nested(feedback_fields, attribute='user_feedback', allow_null=True),
        'retriever_resources': fields.List(fields.Nested(retriever_resource_fields)),
        'created_at': TimestampField,
        'agent_thoughts': fields.List(fields.Nested(agent_thought_fields)),
        'status': fields.String,
        'error': fields.String,
    }

    # 定义消息无限滚动分页字段
    message_infinite_scroll_pagination_fields = {
        'limit': fields.Integer,  # 限制返回的记录数
        'has_more': fields.Boolean,  # 是否还有更多消息
        'data': fields.List(fields.Nested(message_fields))  # 消息数据列表
    }

    @validate_app_token(fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.QUERY))
    @marshal_with(message_infinite_scroll_pagination_fields)
    def get(self, app_model: App, end_user: EndUser):
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in [AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT]:
            raise NotChatAppError()

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('conversation_id', required=True, type=uuid_value, location='args')
        parser.add_argument('first_id', type=uuid_value, location='args')
        parser.add_argument('limit', type=int_range(1, 100), required=False, default=20, location='args')
        args = parser.parse_args()

        try:
            # 调用服务层方法，根据参数获取分页消息数据
            return MessageService.pagination_by_first_id(app_model, end_user,
                                                         args['conversation_id'], args['first_id'], args['limit'])
        except services.errors.conversation.ConversationNotExistsError:
            # 会话不存在时抛出异常
            raise NotFound("Conversation Not Exists.")
        except services.errors.message.FirstMessageNotExistsError:
            # 第一条消息不存在时抛出异常
            raise NotFound("First Message Not Exists.")


class MessageFeedbackApi(Resource):
    @validate_app_token(fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.JSON, required=True))
    def post(self, app_model: App, end_user: EndUser, message_id):
        """
        提交消息反馈。

        Args:
            app_model (App): 应用模型，代表一个具体的应用。
            end_user (EndUser): 终端用户，代表进行反馈的用户。
            message_id (int): 消息ID，用于标识需要反馈的具体消息。

        Returns:
            dict: 包含反馈结果的成功信息。

        Raises:
            NotFound: 如果消息不存在，则抛出此异常。
        """
        message_id = str(message_id)  # 将消息ID转换为字符串

        parser = reqparse.RequestParser()  # 创建请求解析器
        # 添加参数解析规则，支持'like', 'dislike'和None三种评价
        parser.add_argument('rating', type=str, choices=['like', 'dislike', None], location='json')
        args = parser.parse_args()  # 解析客户端提交的参数

        try:
            # 尝试创建消息反馈
            MessageService.create_feedback(app_model, message_id, end_user, args['rating'])
        except services.errors.message.MessageNotExistsError:
            # 如果消息不存在，抛出404异常
            raise NotFound("Message Not Exists.")

        return {'result': 'success'}  # 返回反馈成功的响应

class MessageSuggestedApi(Resource):
    @validate_app_token(fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.QUERY, required=True))
    def get(self, app_model: App, end_user: EndUser, message_id):
        message_id = str(message_id)
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in [AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT]:
            raise NotChatAppError()

        try:
            # 尝试获取在给定消息之后的建议问题
            questions = MessageService.get_suggested_questions_after_answer(
                app_model=app_model,
                user=end_user,
                message_id=message_id,
                invoke_from=InvokeFrom.SERVICE_API
            )
        except services.errors.message.MessageNotExistsError:  # 消息不存在时抛出异常
            raise NotFound("Message Not Exists.")
        except SuggestedQuestionsAfterAnswerDisabledError:
            raise BadRequest("Message Not Exists.")
        except Exception:
            logging.exception("internal server error.")
            raise InternalServerError()

        return {'result': 'success', 'data': questions}  # 返回成功结果和建议问题列表

api.add_resource(MessageListApi, '/messages')
api.add_resource(MessageFeedbackApi, '/messages/<uuid:message_id>/feedbacks')
api.add_resource(MessageSuggestedApi, '/messages/<uuid:message_id>/suggested')
