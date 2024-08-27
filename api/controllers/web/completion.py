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
from controllers.web.error import InvokeRateLimitError as InvokeRateLimitHttpError
from controllers.web.wraps import WebApiResource
from core.app.apps.base_app_queue_manager import AppQueueManager
from core.app.entities.app_invoke_entities import InvokeFrom
from core.errors.error import ModelCurrentlyNotSupportError, ProviderTokenNotInitError, QuotaExceededError
from core.model_runtime.errors.invoke import InvokeError
from libs import helper
from libs.helper import uuid_value
from models.model import AppMode
from services.app_generate_service import AppGenerateService
from services.errors.llm import InvokeRateLimitError


class CompletionApi(WebApiResource):
    def post(self, app_model, end_user):
        if app_model.mode != "completion":
            raise NotCompletionAppError()

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument("inputs", type=dict, required=True, location="json")
        parser.add_argument("query", type=str, location="json", default="")
        parser.add_argument("files", type=list, required=False, location="json")
        parser.add_argument("response_mode", type=str, choices=["blocking", "streaming"], location="json")
        parser.add_argument("retriever_from", type=str, required=False, default="web_app", location="json")

        args = parser.parse_args()

        streaming = args["response_mode"] == "streaming"
        args["auto_generate_name"] = False

        try:
            response = AppGenerateService.generate(
                app_model=app_model, user=end_user, args=args, invoke_from=InvokeFrom.WEB_APP, streaming=streaming
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
        if app_model.mode != "completion":
            raise NotCompletionAppError()

        AppQueueManager.set_stop_flag(task_id, InvokeFrom.WEB_APP, end_user.id)

        return {"result": "success"}, 200


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
        parser.add_argument("inputs", type=dict, required=True, location="json")
        parser.add_argument("query", type=str, required=True, location="json")
        parser.add_argument("files", type=list, required=False, location="json")
        parser.add_argument("response_mode", type=str, choices=["blocking", "streaming"], location="json")
        parser.add_argument("conversation_id", type=uuid_value, location="json")
        parser.add_argument("retriever_from", type=str, required=False, default="web_app", location="json")

        args = parser.parse_args()

        streaming = args["response_mode"] == "streaming"
        args["auto_generate_name"] = False

        try:
            response = AppGenerateService.generate(
                app_model=app_model, user=end_user, args=args, invoke_from=InvokeFrom.WEB_APP, streaming=streaming
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
        except InvokeRateLimitError as ex:
            raise InvokeRateLimitHttpError(ex.description)
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

        return {"result": "success"}, 200


api.add_resource(CompletionApi, "/completion-messages")
api.add_resource(CompletionStopApi, "/completion-messages/<string:task_id>/stop")
api.add_resource(ChatApi, "/chat-messages")
api.add_resource(ChatStopApi, "/chat-messages/<string:task_id>/stop")
