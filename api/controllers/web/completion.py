import logging

from flask_restful import reqparse
from werkzeug.exceptions import InternalServerError, NotFound

import services
from controllers.web import api
from controllers.web.error import (
    AppUnavailableError,
    CompletionRequestError,
    ConversationCompletedError,
    NotChatAppError,
    NotCompletionAppError,
    ProviderModelCurrentlyNotSupportError,
    ProviderNotInitializeError,
    ProviderQuotaExceededError,
)
from controllers.web.wraps import WebApiResource
from core.app.apps.base_app_queue_manager import AppQueueManager
from core.app.entities.app_invoke_entities import InvokeFrom
from core.errors.error import ModelCurrentlyNotSupportError, ProviderTokenNotInitError, QuotaExceededError
from core.model_runtime.errors.invoke import InvokeError
from libs import helper
from libs.helper import uuid_value
from models.model import AppMode
from services.app_generate_service import AppGenerateService


class CompletionApi(WebApiResource):
    """
    定义了一个用于用户完成任务的API接口。

    Attributes:
        WebApiResource: 继承的API资源基类。
    """

    def post(self, app_model, end_user):
        """
        处理POST请求，用于发起完成任务的请求。

        Parameters:
            app_model: 应用模型，用于确定任务的配置和模式。
            end_user: 终端用户信息，用于识别请求的用户。

        Returns:
            返回一个紧凑的响应结果，具体取决于完成服务的处理。

        Raises:
            NotCompletionAppError: 如果应用模式不是'completion'，则抛出异常。
            NotFound: 如果对话不存在，则抛出异常。
            ConversationCompletedError: 如果对话已完成，则抛出异常。
            AppUnavailableError: 如果应用模型配置错误，则抛出异常。
            ProviderNotInitializeError: 如果服务提供者未初始化，则抛出异常。
            ProviderQuotaExceededError: 如果达到服务提供者的配额限制，则抛出异常。
            ProviderModelCurrentlyNotSupportError: 如果当前服务模型不被支持，则抛出异常。
            CompletionRequestError: 如果完成请求发生错误，则抛出异常。
            ValueError: 如果发生值错误，则抛出异常。
            InternalServerError: 如果发生内部服务器错误，则抛出异常。
        """
        # 检查应用模式是否为'completion'
        if app_model.mode != 'completion':
            raise NotCompletionAppError()

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('inputs', type=dict, required=True, location='json')
        parser.add_argument('query', type=str, location='json', default='')
        parser.add_argument('files', type=list, required=False, location='json')
        parser.add_argument('response_mode', type=str, choices=['blocking', 'streaming'], location='json')
        parser.add_argument('retriever_from', type=str, required=False, default='web_app', location='json')

        args = parser.parse_args()

        # 处理响应模式，决定是否采用流式响应
        streaming = args['response_mode'] == 'streaming'
        args['auto_generate_name'] = False

        try:
            response = AppGenerateService.generate(
                app_model=app_model,
                user=end_user,
                args=args,
                invoke_from=InvokeFrom.WEB_APP,
                streaming=streaming
            )

            return helper.compact_generate_response(response)
        except services.errors.conversation.ConversationNotExistsError:
            raise NotFound("Conversation Not Exists.")
        except services.errors.conversation.ConversationCompletedError:
            raise ConversationCompletedError()
        except services.errors.app_model_config.AppModelConfigBrokenError:
            logging.exception("App model config broken.")
            raise AppUnavailableError()
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
        except Exception as e:
            logging.exception("internal server error.")
            raise InternalServerError()


class CompletionStopApi(WebApiResource):
    """
    完成停止API类，用于处理完成任务的停止请求。
    
    方法:
    post: 根据提供的应用模型、最终用户和任务ID，停止指定的任务。
    
    参数:
    app_model: 应用模型对象，包含应用的相关信息。
    end_user: 最终用户对象，标识请求的用户。
    task_id: 任务ID，标识需要停止的任务。
    
    返回值:
    一个包含结果信息的字典和HTTP状态码。成功时返回{'result': 'success'}, 200。
    """
    
    def post(self, app_model, end_user, task_id):
        # 检查应用模式是否为完成模式，如果不是则抛出异常
        if app_model.mode != 'completion':
            raise NotCompletionAppError()

        AppQueueManager.set_stop_flag(task_id, InvokeFrom.WEB_APP, end_user.id)

        # 返回成功结果
        return {'result': 'success'}, 200


class ChatApi(WebApiResource):
    """
    聊天API类，用于处理聊天应用的后端请求。

    方法:
    post: 处理聊天应用程序的提交请求，包括用户输入的消息、查询信息等。

    参数:
    app_model: 应用模型，用于确定应用的配置和模式。
    end_user: 终端用户，标识请求的发起用户。

    返回值:
    返回处理后的响应数据，具体取决于请求的处理结果。
    """

    def post(self, app_model, end_user):
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in [AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT]:
            raise NotChatAppError()

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('inputs', type=dict, required=True, location='json')
        parser.add_argument('query', type=str, required=True, location='json')
        parser.add_argument('files', type=list, required=False, location='json')
        parser.add_argument('response_mode', type=str, choices=['blocking', 'streaming'], location='json')
        parser.add_argument('conversation_id', type=uuid_value, location='json')
        parser.add_argument('retriever_from', type=str, required=False, default='web_app', location='json')

        args = parser.parse_args()

        # 处理响应模式为流式传输的情况
        streaming = args['response_mode'] == 'streaming'
        args['auto_generate_name'] = False

        try:
            response = AppGenerateService.generate(
                app_model=app_model,
                user=end_user,
                args=args,
                invoke_from=InvokeFrom.WEB_APP,
                streaming=streaming
            )

            return helper.compact_generate_response(response)
        except services.errors.conversation.ConversationNotExistsError:
            # 处理对话不存在的异常
            raise NotFound("Conversation Not Exists.")
        except services.errors.conversation.ConversationCompletedError:
            # 处理对话已完成的异常
            raise ConversationCompletedError()
        except services.errors.app_model_config.AppModelConfigBrokenError:
            # 处理应用模型配置错误的异常
            logging.exception("App model config broken.")
            raise AppUnavailableError()
        except ProviderTokenNotInitError as ex:
            # 处理服务提供者令牌未初始化的异常
            raise ProviderNotInitializeError(ex.description)
        except QuotaExceededError:
            # 处理配额超出的异常
            raise ProviderQuotaExceededError()
        except ModelCurrentlyNotSupportError:
            # 处理模型当前不支持的异常
            raise ProviderModelCurrentlyNotSupportError()
        except InvokeError as e:
            # 处理调用错误的异常
            raise CompletionRequestError(e.description)
        except ValueError as e:
            # 直接抛出值错误异常
            raise e
        except Exception as e:
            # 处理其他所有异常，记录日志，并返回内部服务器错误
            logging.exception("internal server error.")
            raise InternalServerError()


class ChatStopApi(WebApiResource):
    """
    停止聊天API接口类，用于通过POST请求停止特定任务。

    参数:
    - app_model: 应用模型，用于检查应用模式是否为聊天模式。
    - end_user: 终端用户信息，需要包含用户的ID。
    - task_id: 任务ID，标识需要停止的任务。

    返回值:
    - 一个包含结果信息的字典和HTTP状态码200，表示成功停止任务。
    """
    def post(self, app_model, end_user, task_id):
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in [AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT]:
            raise NotChatAppError()

        AppQueueManager.set_stop_flag(task_id, InvokeFrom.WEB_APP, end_user.id)

        # 返回成功结果和HTTP状态码200
        return {'result': 'success'}, 200


api.add_resource(CompletionApi, '/completion-messages')
api.add_resource(CompletionStopApi, '/completion-messages/<string:task_id>/stop')
api.add_resource(ChatApi, '/chat-messages')
api.add_resource(ChatStopApi, '/chat-messages/<string:task_id>/stop')
