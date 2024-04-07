import json
import logging
from collections.abc import Generator
from typing import Union

from flask import Response, stream_with_context
from flask_restful import fields, marshal_with, reqparse
from flask_restful.inputs import int_range
from werkzeug.exceptions import InternalServerError, NotFound

import services
from controllers.web import api
from controllers.web.error import (
    AppMoreLikeThisDisabledError,
    AppSuggestedQuestionsAfterAnswerDisabledError,
    CompletionRequestError,
    NotChatAppError,
    NotCompletionAppError,
    ProviderModelCurrentlyNotSupportError,
    ProviderNotInitializeError,
    ProviderQuotaExceededError,
)
from controllers.web.wraps import WebApiResource
from core.entities.application_entities import InvokeFrom
from core.errors.error import ModelCurrentlyNotSupportError, ProviderTokenNotInitError, QuotaExceededError
from core.model_runtime.errors.invoke import InvokeError
from fields.conversation_fields import message_file_fields
from fields.message_fields import agent_thought_fields
from libs.helper import TimestampField, uuid_value
from services.completion_service import CompletionService
from services.errors.app import MoreLikeThisDisabledError
from services.errors.conversation import ConversationNotExistsError
from services.errors.message import MessageNotExistsError, SuggestedQuestionsAfterAnswerDisabledError
from services.message_service import MessageService


class MessageListApi(WebApiResource):
    """
    消息列表API资源类，用于处理消息列表的获取。

    属性:
    - feedback_fields: 反馈信息的字段定义。
    - retriever_resource_fields: 检索资源的字段定义。
    - message_fields: 消息的字段定义。
    - message_infinite_scroll_pagination_fields: 无限滚动分页消息的字段定义。
    """

    # 定义反馈信息的字段
    feedback_fields = {
        'rating': fields.String
    }

    # 定义检索资源的字段
    retriever_resource_fields = {
        'id': fields.String,  # 资源的唯一标识符
        'message_id': fields.String,  # 消息的唯一标识符
        'position': fields.Integer,  # 资源在消息中的位置
        'dataset_id': fields.String,  # 数据集的唯一标识符
        'dataset_name': fields.String,  # 数据集的名称
        'document_id': fields.String,  # 文档的唯一标识符
        'document_name': fields.String,  # 文档的名称
        'data_source_type': fields.String,  # 数据源的类型
        'segment_id': fields.String,  # 文本段的唯一标识符
        'score': fields.Float,  # 查询结果的相关性分数
        'hit_count': fields.Integer,  # 命中结果的数量
        'word_count': fields.Integer,  # 文本段的单词数量
        'segment_position': fields.Integer,  # 文本段在文档中的位置
        'index_node_hash': fields.String,  # 索引节点的哈希值
        'content': fields.String,  # 文本段的内容
        'created_at': TimestampField  # 资源创建的时间戳
    }

    # 定义消息的字段
    message_fields = {
        'id': fields.String,  # 消息的唯一标识符
        'conversation_id': fields.String,  # 对话的唯一标识符
        'inputs': fields.Raw,  # 输入的消息内容，保持原始格式
        'query': fields.String,  # 用户的查询内容
        'answer': fields.String,  # 对应的答案内容
        'message_files': fields.List(fields.Nested(message_file_fields), attribute='files'),  # 消息附带的文件列表
        'feedback': fields.Nested(feedback_fields, attribute='user_feedback', allow_null=True),  # 用户反馈的信息，可以为空
        'retriever_resources': fields.List(fields.Nested(retriever_resource_fields)),  # 检索器使用的资源列表
        'created_at': TimestampField,  # 消息创建的时间戳
        'agent_thoughts': fields.List(fields.Nested(agent_thought_fields))  # 代理（AI）思考过程或内部信息
    }

    """
    定义了一个用于无限滚动分页消息的字段字典。
    
    字典中包含了分页消息必要的字段及其类型：
    - 'limit': 表示每页的数据数量，类型为整数。
    - 'has_more': 表示是否还有更多的数据可供加载，类型为布尔值。
    - 'data': 存储实际的数据内容，类型为嵌套的消息字段列表。
    
    这个定义适用于需要进行无限滚动加载数据的场景，比如在网页或应用中的消息列表。
    """
    message_infinite_scroll_pagination_fields = {
        'limit': fields.Integer,
        'has_more': fields.Boolean,
        'data': fields.List(fields.Nested(message_fields))
    }

    @marshal_with(message_infinite_scroll_pagination_fields)
    def get(self, app_model, end_user):
        """
        获取消息列表，支持无限滚动分页。

        参数:
        - app_model: 应用模型，用于判断应用模式。
        - end_user: 终端用户信息。

        返回:
        - 分页消息列表。

        异常:
        - NotChatAppError: 聊天模式应用不存在错误。
        - NotFound: 对话或起始消息不存在错误。
        """
        # 检查应用模式是否为聊天模式
        if app_model.mode != 'chat':
            raise NotChatAppError()

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('conversation_id', required=True, type=uuid_value, location='args')
        parser.add_argument('first_id', type=uuid_value, location='args')
        parser.add_argument('limit', type=int_range(1, 100), required=False, default=20, location='args')
        args = parser.parse_args()

        try:
            # 根据起始ID和对话ID进行分页查询
            return MessageService.pagination_by_first_id(app_model, end_user,
                                                     args['conversation_id'], args['first_id'], args['limit'])
        except services.errors.conversation.ConversationNotExistsError:
            raise NotFound("Conversation Not Exists.")
        except services.errors.message.FirstMessageNotExistsError:
            raise NotFound("First Message Not Exists.")


class MessageFeedbackApi(WebApiResource):
    """
    消息反馈API类，用于处理消息反馈的POST请求。

    参数:
    - app_model: 应用模型，标识反馈所属的应用。
    - end_user: 终端用户，标识给出反馈的用户。
    - message_id: 消息ID，标识被反馈的消息。

    返回值:
    - 返回一个包含结果信息的字典。
    """

    def post(self, app_model, end_user, message_id):
        # 将消息ID转换为字符串格式
        message_id = str(message_id)

        # 初始化请求解析器，用于解析请求体中的参数
        parser = reqparse.RequestParser()
        # 添加评分参数到解析器，支持'like', 'dislike'和None三种选择
        parser.add_argument('rating', type=str, choices=['like', 'dislike', None], location='json')
        # 解析请求体中的参数
        args = parser.parse_args()

        try:
            # 尝试创建消息反馈
            MessageService.create_feedback(app_model, message_id, end_user, args['rating'])
        except services.errors.message.MessageNotExistsError:
            # 如果消息不存在，则抛出404错误
            raise NotFound("Message Not Exists.")

        # 返回操作成功的结果
        return {'result': 'success'}


class MessageMoreLikeThisApi(WebApiResource):
    """
    提供消息更多相似内容的API接口。
    
    参数:
    - app_model: 应用模型，用于确定应用的配置和模式。
    - end_user: 终端用户信息，标识请求的用户。
    - message_id: 消息ID，用于查找特定的消息。
    
    返回值:
    - 返回一个压缩后的响应，具体格式取决于请求的response_mode。
    
    抛出:
    - NotCompletionAppError: 如果应用模式不是'completion'，则抛出此错误。
    - NotFound: 如果消息不存在，则抛出此错误。
    - AppMoreLikeThisDisabledError: 如果应用禁用了更多相似内容功能，则抛出此错误。
    - ProviderNotInitializeError: 如果服务提供者未初始化，则抛出此错误。
    - ProviderQuotaExceededError: 如果达到服务提供者的配额限制，则抛出此错误。
    - ProviderModelCurrentlyNotSupportError: 如果服务提供者当前不支持指定模型，则抛出此错误。
    - CompletionRequestError: 如果完成请求发生错误，则抛出此错误。
    - ValueError: 如果遇到无效值错误，则抛出。
    - InternalServerError: 如果发生内部服务器错误，则抛出。
    """

    def get(self, app_model, end_user, message_id):
        # 检查应用模式是否为'completion'
        if app_model.mode != 'completion':
            raise NotCompletionAppError()

        message_id = str(message_id)  # 确保消息ID为字符串格式

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('response_mode', type=str, required=True, choices=['blocking', 'streaming'], location='args')
        args = parser.parse_args()

        # 根据响应模式确定是否流式返回结果
        streaming = args['response_mode'] == 'streaming'

        try:
            # 生成更多相似内容的响应
            response = CompletionService.generate_more_like_this(
                app_model=app_model,
                user=end_user,
                message_id=message_id,
                invoke_from=InvokeFrom.WEB_APP,
                streaming=streaming
            )

            # 返回压缩后的响应
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
    """
    根据传入的响应内容类型，生成相应的 Response 对象。
    
    参数:
    - response: 可以是字典或者生成器。如果为字典，则直接以 JSON 格式返回；如果为生成器，则以流的形式返回。
    
    返回值:
    - Response: 根据输入的 response 参数类型，返回一个配置了相应内容和类型的 Response 对象。
    """
    if isinstance(response, dict):
        # 如果响应是字典，则将其转换为 JSON 格式，并设置相应的状态码和 MIME 类型
        return Response(response=json.dumps(response), status=200, mimetype='application/json')
    else:
        # 如果响应是生成器，则定义一个内部生成器函数将其内容逐个yield，并配置响应为流式传输
        def generate() -> Generator:
            yield from response

        # 返回一个配置了生成器、状态码和 MIME 类型的 Response 对象，用于流式传输
        return Response(stream_with_context(generate()), status=200,
                        mimetype='text/event-stream')


class MessageSuggestedQuestionApi(WebApiResource):
    """
    提供获取消息建议问题的API接口。
    
    参数:
    - app_model: 应用模型，用于确定应用的运行模式等。
    - end_user: 终端用户信息，标识请求的用户。
    - message_id: 消息ID，用于查找相关的建议问题。
    
    返回值:
    - 返回一个包含建议问题的字典。
    
    抛出:
    - NotCompletionAppError: 如果应用模式不为'chat'。
    - NotFound: 如果消息或对话不存在。
    - AppSuggestedQuestionsAfterAnswerDisabledError: 如果应用的答后建议问题功能被禁用。
    - ProviderNotInitializeError: 如果服务提供者令牌未初始化。
    - ProviderQuotaExceededError: 如果达到服务提供者的配额限制。
    - ProviderModelCurrentlyNotSupportError: 如果当前服务提供者不支持的模型。
    - CompletionRequestError: 如果调用过程中发生错误。
    - InternalServerError: 如果发生内部服务器错误。
    """

    def get(self, app_model, end_user, message_id):
        # 检查应用模式是否为'chat'
        if app_model.mode != 'chat':
            raise NotCompletionAppError()

        message_id = str(message_id)  # 确保消息ID为字符串格式

        try:
            # 尝试获取回答后的建议问题
            questions = MessageService.get_suggested_questions_after_answer(
                app_model=app_model,
                user=end_user,
                message_id=message_id
            )
        except MessageNotExistsError:
            raise NotFound("Message not found")  # 消息不存在异常处理
        except ConversationNotExistsError:
            raise NotFound("Conversation not found")  # 对话不存在异常处理
        except SuggestedQuestionsAfterAnswerDisabledError:
            raise AppSuggestedQuestionsAfterAnswerDisabledError()  # 禁用答后建议问题异常处理
        except ProviderTokenNotInitError as ex:
            raise ProviderNotInitializeError(ex.description)  # 提供者令牌未初始化异常处理
        except QuotaExceededError:
            raise ProviderQuotaExceededError()  # 配额超出异常处理
        except ModelCurrentlyNotSupportError:
            raise ProviderModelCurrentlyNotSupportError()  # 当前模型不支持异常处理
        except InvokeError as e:
            raise CompletionRequestError(e.description)  # 调用错误异常处理
        except Exception:
            logging.exception("internal server error.")  # 内部服务器错误异常处理
            raise InternalServerError()

        return {'data': questions}  # 返回建议问题数据


api.add_resource(MessageListApi, '/messages')
api.add_resource(MessageFeedbackApi, '/messages/<uuid:message_id>/feedbacks')
api.add_resource(MessageMoreLikeThisApi, '/messages/<uuid:message_id>/more-like-this')
api.add_resource(MessageSuggestedQuestionApi, '/messages/<uuid:message_id>/suggested-questions')
