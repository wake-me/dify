import json
import logging
from collections.abc import Generator
from typing import Union

from flask import Response, stream_with_context
from flask_login import current_user
from flask_restful import marshal_with, reqparse
from flask_restful.inputs import int_range
from werkzeug.exceptions import InternalServerError, NotFound

import services
from controllers.console import api
from controllers.console.app.error import (
    AppMoreLikeThisDisabledError,
    CompletionRequestError,
    ProviderModelCurrentlyNotSupportError,
    ProviderNotInitializeError,
    ProviderQuotaExceededError,
)
from controllers.console.explore.error import (
    AppSuggestedQuestionsAfterAnswerDisabledError,
    NotChatAppError,
    NotCompletionAppError,
)
from controllers.console.explore.wraps import InstalledAppResource
from core.entities.application_entities import InvokeFrom
from core.errors.error import ModelCurrentlyNotSupportError, ProviderTokenNotInitError, QuotaExceededError
from core.model_runtime.errors.invoke import InvokeError
from fields.message_fields import message_infinite_scroll_pagination_fields
from libs.helper import uuid_value
from services.completion_service import CompletionService
from services.errors.app import MoreLikeThisDisabledError
from services.errors.conversation import ConversationNotExistsError
from services.errors.message import MessageNotExistsError, SuggestedQuestionsAfterAnswerDisabledError
from services.message_service import MessageService


class MessageListApi(InstalledAppResource):
    """
    获取消息列表的API接口，支持无限滚动分页。

    参数:
    - installed_app: 已安装的应用对象，用于确定请求的应用。

    返回值:
    - 返回一个分页后的消息列表。
    """

    @marshal_with(message_infinite_scroll_pagination_fields)
    def get(self, installed_app):
        """
        处理GET请求，根据提供的参数获取特定对话中的消息列表。

        参数:
        - conversation_id: 对话的唯一标识符，必需。
        - first_id: 列表的起始消息ID，必需。
        - limit: 请求的消息数量，默认为20，可选。

        返回值:
        - 根据提供的起始消息ID和对话ID，返回指定数量的消息列表。

        异常:
        - NotChatAppError: 如果应用模式不是聊天模式，则抛出此错误。
        - NotFound: 如果对话或起始消息不存在，则抛出此错误。
        """
        
        app_model = installed_app.app

        # 检查应用模式是否为聊天模式
        if app_model.mode != 'chat':
            raise NotChatAppError()

        parser = reqparse.RequestParser()
        # 添加请求参数解析
        parser.add_argument('conversation_id', required=True, type=uuid_value, location='args')
        parser.add_argument('first_id', type=uuid_value, location='args')
        parser.add_argument('limit', type=int_range(1, 100), required=False, default=20, location='args')
        args = parser.parse_args()

        try:
            # 调用服务层进行分页查询
            return MessageService.pagination_by_first_id(app_model, current_user,
                                                     args['conversation_id'], args['first_id'], args['limit'])
        except services.errors.conversation.ConversationNotExistsError:
            raise NotFound("Conversation Not Exists.")
        except services.errors.message.FirstMessageNotExistsError:
            raise NotFound("First Message Not Exists.")

class MessageFeedbackApi(InstalledAppResource):
    """
    提供消息反馈的API接口，允许用户对特定消息进行点赞或点踩。

    参数:
    - installed_app: 安装的应用对象，用于确定操作的上下文。
    - message_id: 消息的唯一标识符，用于指定给予反馈的消息。

    返回值:
    - 返回一个包含结果信息的字典，例如 {'result': 'success'}。
    """

    def post(self, installed_app, message_id):
        # 将传入的installed_app转换为应用模型，准备进行消息服务的操作
        app_model = installed_app.app

        # 确保消息ID为字符串类型，方便后续处理
        message_id = str(message_id)

        # 初始化请求解析器，用于解析客户端提交的点赞或点踩类型
        parser = reqparse.RequestParser()
        parser.add_argument('rating', type=str, choices=['like', 'dislike', None], location='json')
        args = parser.parse_args()

        try:
            # 尝试创建消息反馈，包括应用模型、消息ID、当前用户和点赞/点踩类型
            MessageService.create_feedback(app_model, message_id, current_user, args['rating'])
        except services.errors.message.MessageNotExistsError:
            # 如果消息不存在，则抛出404错误
            raise NotFound("Message Not Exists.")

        # 返回成功结果
        return {'result': 'success'}


class MessageMoreLikeThisApi(InstalledAppResource):
    """
    提供一个接口，用于获取与指定消息更相似的内容。
    
    参数:
    - installed_app: 已安装的应用对象，用于确定调用的应用。
    - message_id: 消息的唯一标识符，用于查找原始消息。
    
    返回值:
    - 返回一个根据请求模式（blocking或streaming）生成的响应。
    
    抛出:
    - NotCompletionAppError: 如果应用模式不是'completion'，则抛出此错误。
    - NotFound: 如果消息不存在，则抛出此错误。
    - AppMoreLikeThisDisabledError: 如果应用的"更多类似"功能被禁用，则抛出此错误。
    - ProviderNotInitializeError: 如果服务提供者令牌未初始化，则抛出此错误。
    - ProviderQuotaExceededError: 如果达到服务提供者的配额限制，则抛出此错误。
    - ProviderModelCurrentlyNotSupportError: 如果当前服务提供者不支持指定模型，则抛出此错误。
    - CompletionRequestError: 如果调用完成服务发生错误，则抛出此错误。
    - ValueError: 如果遇到值错误，则直接抛出。
    - InternalServerError: 如果发生内部服务器错误，则抛出此错误。
    """

    def get(self, installed_app, message_id):
        # 校验调用的应用模式是否为'completion'
        app_model = installed_app.app
        if app_model.mode != 'completion':
            raise NotCompletionAppError()

        message_id = str(message_id)

        # 解析请求参数，包括响应模式（blocking或streaming）
        parser = reqparse.RequestParser()
        parser.add_argument('response_mode', type=str, required=True, choices=['blocking', 'streaming'], location='args')
        args = parser.parse_args()

        # 根据响应模式确定是否为流式响应
        streaming = args['response_mode'] == 'streaming'

        try:
            # 调用服务生成更多类似的内容
            response = CompletionService.generate_more_like_this(
                app_model=app_model,
                user=current_user,
                message_id=message_id,
                invoke_from=InvokeFrom.EXPLORE,
                streaming=streaming
            )
            # 返回紧凑的响应格式
            return compact_response(response)
        except MessageNotExistsError:
            raise NotFound("Message Not Exists.")
        except MoreLikeThisDisabledError:
            raise AppMoreLikeThisDisabledError()
        except ProviderTokenNotInitError as ex:
            raise ProviderNotInitializeError(ex.description)
        except QuotaExceededError:
            raise ProviderQuotaExceededError()
        except ModelCurrentlyNotSupportError:
            raise ProviderModelCurrentlyNotSupportError()
        except InvokeError as e:
            raise CompletionRequestError(e.description)
        except ValueError as e:
            raise e
        except Exception:
            # 记录并抛出内部服务器错误
            logging.exception("internal server error.")
            raise InternalServerError()


def compact_response(response: Union[dict, Generator]) -> Response:
    if isinstance(response, dict):
        return Response(response=json.dumps(response), status=200, mimetype='application/json')
    else:
        def generate() -> Generator:
            yield from response

        return Response(stream_with_context(generate()), status=200,
                        mimetype='text/event-stream')


class MessageSuggestedQuestionApi(InstalledAppResource):
    """
    提供获取消息建议问题的API接口。
    
    参数:
    - installed_app: 已安装的应用对象，用于获取应用模型和验证应用状态。
    - message_id: 消息的唯一标识符，用于查询相关的建议问题。
    
    返回值:
    - 返回一个包含建议问题的字典。
    """
    
    def get(self, installed_app, message_id):
        app_model = installed_app.app
        # 验证应用是否为聊天模式
        if app_model.mode != 'chat':
            raise NotCompletionAppError()

        message_id = str(message_id)

        try:
            # 尝试获取回答后的建议问题
            questions = MessageService.get_suggested_questions_after_answer(
                app_model=app_model,
                user=current_user,
                message_id=message_id
            )
        except MessageNotExistsError:
            raise NotFound("Message not found")  # 消息不存在异常处理
        except ConversationNotExistsError:
            raise NotFound("Conversation not found")  # 对话不存在异常处理
        except SuggestedQuestionsAfterAnswerDisabledError:
            raise AppSuggestedQuestionsAfterAnswerDisabledError()  # 建议问题功能被禁用异常处理
        except ProviderTokenNotInitError as ex:
            raise ProviderNotInitializeError(ex.description)  # 供应商令牌未初始化异常处理
        except QuotaExceededError:
            raise ProviderQuotaExceededError()  # 配额超出异常处理
        except ModelCurrentlyNotSupportError:
            raise ProviderModelCurrentlyNotSupportError()  # 当前模型不支持异常处理
        except InvokeError as e:
            raise CompletionRequestError(e.description)  # 调用错误异常处理
        except Exception:
            logging.exception("internal server error.")  # 服务器内部错误异常处理
            raise InternalServerError()

        return {'data': questions}  # 返回建议问题数据


api.add_resource(MessageListApi, '/installed-apps/<uuid:installed_app_id>/messages', endpoint='installed_app_messages')
api.add_resource(MessageFeedbackApi, '/installed-apps/<uuid:installed_app_id>/messages/<uuid:message_id>/feedbacks', endpoint='installed_app_message_feedback')
api.add_resource(MessageMoreLikeThisApi, '/installed-apps/<uuid:installed_app_id>/messages/<uuid:message_id>/more-like-this', endpoint='installed_app_more_like_this')
api.add_resource(MessageSuggestedQuestionApi, '/installed-apps/<uuid:installed_app_id>/messages/<uuid:message_id>/suggested-questions', endpoint='installed_app_suggested_question')
