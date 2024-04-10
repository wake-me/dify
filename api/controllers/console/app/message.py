import logging

from flask_login import current_user
from flask_restful import Resource, fields, marshal_with, reqparse
from flask_restful.inputs import int_range
from werkzeug.exceptions import Forbidden, InternalServerError, NotFound

from controllers.console import api
from controllers.console.app.error import (
    CompletionRequestError,
    ProviderModelCurrentlyNotSupportError,
    ProviderNotInitializeError,
    ProviderQuotaExceededError,
)
from controllers.console.app.wraps import get_app_model
from controllers.console.explore.error import AppSuggestedQuestionsAfterAnswerDisabledError
from controllers.console.setup import setup_required
from controllers.console.wraps import account_initialization_required, cloud_edition_billing_resource_check
from core.app.entities.app_invoke_entities import InvokeFrom
from core.errors.error import ModelCurrentlyNotSupportError, ProviderTokenNotInitError, QuotaExceededError
from core.model_runtime.errors.invoke import InvokeError
from extensions.ext_database import db
from fields.conversation_fields import annotation_fields, message_detail_fields
from libs.helper import uuid_value
from libs.infinite_scroll_pagination import InfiniteScrollPagination
from libs.login import login_required
from models.model import AppMode, Conversation, Message, MessageAnnotation, MessageFeedback
from services.annotation_service import AppAnnotationService
from services.errors.conversation import ConversationNotExistsError
from services.errors.message import MessageNotExistsError, SuggestedQuestionsAfterAnswerDisabledError
from services.message_service import MessageService


class ChatMessageListApi(Resource):
    # 定义聊天消息列表API，提供获取无限滚动消息列表的功能
    message_infinite_scroll_pagination_fields = {
        'limit': fields.Integer,  # 请求返回的最大消息数量
        'has_more': fields.Boolean,  # 是否还有更多消息
        'data': fields.List(fields.Nested(message_detail_fields))  # 消息数据列表
    }

    @setup_required
    @login_required
    @get_app_model(mode=[AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT])
    @account_initialization_required
    @marshal_with(message_infinite_scroll_pagination_fields)
    def get(self, app_model):
        parser = reqparse.RequestParser()
        parser.add_argument('conversation_id', required=True, type=uuid_value, location='args')
        parser.add_argument('first_id', type=uuid_value, location='args')
        parser.add_argument('limit', type=int_range(1, 100), required=False, default=20, location='args')
        args = parser.parse_args()

        # 根据conversation_id查询对话信息
        conversation = db.session.query(Conversation).filter(
            Conversation.id == args['conversation_id'],
            Conversation.app_id == app_model.id
        ).first()

        # 对话不存在时抛出异常
        if not conversation:
            raise NotFound("Conversation Not Exists.")

        # 根据first_id查询起始消息，用于获取之前的对话历史
        if args['first_id']:
            first_message = db.session.query(Message) \
                .filter(Message.conversation_id == conversation.id, Message.id == args['first_id']).first()

            # 若起始消息不存在则抛出异常
            if not first_message:
                raise NotFound("First message not found")

            # 查询从起始消息之前的消息，按时间倒序，限制条数
            history_messages = db.session.query(Message).filter(
                Message.conversation_id == conversation.id,
                Message.created_at < first_message.created_at,
                Message.id != first_message.id
            ) \
                .order_by(Message.created_at.desc()).limit(args['limit']).all()
        else:
            # 若没有提供first_id，则直接查询最新的对话历史
            history_messages = db.session.query(Message).filter(Message.conversation_id == conversation.id) \
                .order_by(Message.created_at.desc()).limit(args['limit']).all()

        # 判断是否还有更多的消息可供查询
        has_more = False
        if len(history_messages) == args['limit']:
            current_page_first_message = history_messages[-1]
            rest_count = db.session.query(Message).filter(
                Message.conversation_id == conversation.id,
                Message.created_at < current_page_first_message.created_at,
                Message.id != current_page_first_message.id
            ).count()

            if rest_count > 0:
                has_more = True

        # 将查询结果反转，以便按时间正序展示
        history_messages = list(reversed(history_messages))

        # 返回无限滚动分页数据
        return InfiniteScrollPagination(
            data=history_messages,
            limit=args['limit'],
            has_more=has_more
        )

class MessageFeedbackApi(Resource):
    """
    消息反馈API类，提供创建或更新消息反馈的功能。

    Attributes:
        app_id (str): 应用的唯一标识符。
    """

    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model
    def post(self, app_model):
        parser = reqparse.RequestParser()
        parser.add_argument('message_id', required=True, type=uuid_value, location='json')
        parser.add_argument('rating', type=str, choices=['like', 'dislike', None], location='json')
        args = parser.parse_args()

        message_id = str(args['message_id'])

        # 根据消息ID和应用ID查询消息
        message = db.session.query(Message).filter(
            Message.id == message_id,
            Message.app_id == app_model.id
        ).first()

        if not message:
            raise NotFound("Message Not Exists.")

        feedback = message.admin_feedback

        # 根据提供的评级更新或删除反馈，或创建新的反馈
        if not args['rating'] and feedback:
            db.session.delete(feedback)
        elif args['rating'] and feedback:
            feedback.rating = args['rating']
        elif not args['rating'] and not feedback:
            raise ValueError('rating cannot be None when feedback not exists')
        else:
            feedback = MessageFeedback(
                app_id=app_model.id,
                conversation_id=message.conversation_id,
                message_id=message.id,
                rating=args['rating'],
                from_source='admin',
                from_account_id=current_user.id
            )
            db.session.add(feedback)

        db.session.commit()

        return {'result': 'success'}


class MessageAnnotationApi(Resource):
    """
    消息注释API，用于处理消息的注释相关请求。
    
    Attributes:
        Resource: 继承自Flask-RESTful的Resource类，用于创建RESTful API资源。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    @cloud_edition_billing_resource_check('annotation')
    @get_app_model
    @marshal_with(annotation_fields)
    def post(self, app_model):
        # The role of the current user in the ta table must be admin or owner
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        parser = reqparse.RequestParser()
        parser.add_argument('message_id', required=False, type=uuid_value, location='json')
        parser.add_argument('question', required=True, type=str, location='json')
        parser.add_argument('answer', required=True, type=str, location='json')
        parser.add_argument('annotation_reply', required=False, type=dict, location='json')
        args = parser.parse_args()
        annotation = AppAnnotationService.up_insert_app_annotation_from_message(args, app_model.id)

        return annotation


class MessageAnnotationCountApi(Resource):
    """
    获取指定应用的消息注解数量的API接口类
    
    方法:
    - get: 根据应用ID获取该应用的消息注解数量
    
    参数:
    - app_id: 应用的唯一标识符，类型为整数或字符串
    
    返回值:
    - 一个包含注解数量的字典，如 {'count': n}
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model
    def get(self, app_model):
        count = db.session.query(MessageAnnotation).filter(
            MessageAnnotation.app_id == app_model.id
        ).count()

        return {'count': count}


class MessageSuggestedQuestionApi(Resource):
    """
    提供获取消息建议问题的API接口。
    
    要求先进行设置、登录和账户初始化。
    
    参数:
    - app_id: 应用的ID，将被转换为字符串格式。
    - message_id: 消息的ID，将被转换为字符串格式。
    
    返回值:
    - 一个包含问题数据的字典。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT])
    def get(self, app_model, message_id):
        message_id = str(message_id)

        try:
            # 尝试获取回答后的建议问题
            questions = MessageService.get_suggested_questions_after_answer(
                app_model=app_model,
                message_id=message_id,
                user=current_user,
                invoke_from=InvokeFrom.DEBUGGER
            )
        except MessageNotExistsError:
            # 消息不存在时抛出异常
            raise NotFound("Message not found")
        except ConversationNotExistsError:
            # 对话不存在时抛出异常
            raise NotFound("Conversation not found")
        except ProviderTokenNotInitError as ex:
            # 提供者令牌未初始化时抛出异常
            raise ProviderNotInitializeError(ex.description)
        except QuotaExceededError:
            # 额度超出时抛出异常
            raise ProviderQuotaExceededError()
        except ModelCurrentlyNotSupportError:
            # 当前模型不支持时抛出异常
            raise ProviderModelCurrentlyNotSupportError()
        except InvokeError as e:
            # 调用错误时抛出异常
            raise CompletionRequestError(e.description)
        except SuggestedQuestionsAfterAnswerDisabledError:
            raise AppSuggestedQuestionsAfterAnswerDisabledError()
        except Exception:
            # 其他异常时记录日志并抛出内部服务器错误
            logging.exception("internal server error.")
            raise InternalServerError()

        return {'data': questions}  # 返回问题数据


class MessageApi(Resource):
    """
    消息API类，用于处理消息相关的RESTful请求。

    属性:
        Resource: 父类，提供RESTful API的基本方法。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model
    @marshal_with(message_detail_fields)
    def get(self, app_model, message_id):
        message_id = str(message_id)

        # 查询数据库，获取指定消息
        message = db.session.query(Message).filter(
            Message.id == message_id,
            Message.app_id == app_model.id
        ).first()

        if not message:
            raise NotFound("Message Not Exists.")  # 如果消息不存在，抛出异常

        return message  # 返回查询到的消息


api.add_resource(MessageSuggestedQuestionApi, '/apps/<uuid:app_id>/chat-messages/<uuid:message_id>/suggested-questions')
api.add_resource(ChatMessageListApi, '/apps/<uuid:app_id>/chat-messages', endpoint='console_chat_messages')
api.add_resource(MessageFeedbackApi, '/apps/<uuid:app_id>/feedbacks')
api.add_resource(MessageAnnotationApi, '/apps/<uuid:app_id>/annotations')
api.add_resource(MessageAnnotationCountApi, '/apps/<uuid:app_id>/annotations/count')
api.add_resource(MessageApi, '/apps/<uuid:app_id>/messages/<uuid:message_id>', endpoint='console_message')
