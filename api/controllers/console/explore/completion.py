import json
import logging
from collections.abc import Generator
from datetime import datetime
from typing import Union

from flask import Response, stream_with_context
from flask_login import current_user
from flask_restful import reqparse
from werkzeug.exceptions import InternalServerError, NotFound

import services
from controllers.console import api
from controllers.console.app.error import (
    AppUnavailableError,
    CompletionRequestError,
    ConversationCompletedError,
    ProviderModelCurrentlyNotSupportError,
    ProviderNotInitializeError,
    ProviderQuotaExceededError,
)
from controllers.console.explore.error import NotChatAppError, NotCompletionAppError
from controllers.console.explore.wraps import InstalledAppResource
from core.application_queue_manager import ApplicationQueueManager
from core.entities.application_entities import InvokeFrom
from core.errors.error import ModelCurrentlyNotSupportError, ProviderTokenNotInitError, QuotaExceededError
from core.model_runtime.errors.invoke import InvokeError
from extensions.ext_database import db
from libs.helper import uuid_value
from services.completion_service import CompletionService


# define completion api for user
class CompletionApi(InstalledAppResource):
    """
    提供完成API的类，用于处理与安装应用相关的完成请求。

    方法:
    - post: 处理完成请求，并返回相应的完成响应。
    """

    def post(self, installed_app):
        """
        处理完成请求。

        参数:
        - installed_app: 已安装的应用对象，用于获取应用模型和进行后续处理。

        返回:
        - 根据请求生成的紧凑型响应数据。

        异常:
        - NotCompletionAppError: 如果应用模型不是完成模式，则抛出此异常。
        - NotFound: 如果对话不存在，则抛出此异常。
        - ConversationCompletedError: 如果对话已完成，则抛出此异常。
        - AppUnavailableError: 如果应用模型配置损坏，则抛出此异常。
        - ProviderNotInitializeError: 如果服务提供者未初始化，则抛出此异常。
        - ProviderQuotaExceededError: 如果达到服务提供者的配额限制，则抛出此异常。
        - ProviderModelCurrentlyNotSupportError: 如果当前服务提供者不支持指定模型，则抛出此异常。
        - CompletionRequestError: 如果完成请求发生错误，则抛出此异常。
        - ValueError: 如果发生值错误，则直接抛出。
        - InternalServerError: 如果发生内部服务器错误，则抛出此异常。
        """
        app_model = installed_app.app
        # 检查应用模式是否为完成模式
        if app_model.mode != 'completion':
            raise NotCompletionAppError()

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('inputs', type=dict, required=True, location='json')
        parser.add_argument('query', type=str, location='json', default='')
        parser.add_argument('files', type=list, required=False, location='json')
        parser.add_argument('response_mode', type=str, choices=['blocking', 'streaming'], location='json')
        parser.add_argument('retriever_from', type=str, required=False, default='explore_app', location='json')
        args = parser.parse_args()

        # 处理响应模式，并设置自动生成名称为False
        streaming = args['response_mode'] == 'streaming'
        args['auto_generate_name'] = False

        # 更新安装应用的最后使用时间
        installed_app.last_used_at = datetime.utcnow()
        db.session.commit()

        try:
            # 调用完成服务，获取响应
            response = CompletionService.completion(
                app_model=app_model,
                user=current_user,
                args=args,
                invoke_from=InvokeFrom.EXPLORE,
                streaming=streaming
            )

            # 返回紧凑型响应
            return compact_response(response)
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


class CompletionStopApi(InstalledAppResource):
    """
    用于处理完成停止任务的API请求。

    参数:
    - installed_app: 已安装的应用对象，用于获取应用模型。
    - task_id: 任务ID，标识需要停止的任务。

    返回值:
    - 一个包含结果信息的字典和HTTP状态码。成功时返回 {'result': 'success'}, 200。
    """
    def post(self, installed_app, task_id):
        # 获取应用模型
        app_model = installed_app.app
        # 检查应用模式是否为'completion'，如果不是，则抛出异常
        if app_model.mode != 'completion':
            raise NotCompletionAppError()

        # 设置任务停止标志
        ApplicationQueueManager.set_stop_flag(task_id, InvokeFrom.EXPLORE, current_user.id)

        # 返回成功结果
        return {'result': 'success'}, 200


class ChatApi(InstalledAppResource):
    """
    聊天API类，用于处理与聊天相关的API请求。

    Attributes:
        InstalledAppResource: 继承的基类，提供安装应用的资源处理方法。
    """

    def post(self, installed_app):
        """
        处理POST请求，用于发起一个新的聊天会话或继续一个存在的会话。

        Args:
            installed_app: 已安装的应用对象，用于获取应用配置和状态。

        Returns:
            返回聊天响应的结果，格式化为API友好的响应格式。

        Raises:
            NotChatAppError: 如果应用不是聊天模式，则抛出异常。
            NotFound: 如果会话不存在，则抛出异常。
            ConversationCompletedError: 如果会话已经完成，则抛出异常。
            AppUnavailableError: 如果应用配置错误，则抛出异常。
            ProviderNotInitializeError: 如果服务提供者未初始化，则抛出异常。
            ProviderQuotaExceededError: 如果达到服务提供者的配额限制，则抛出异常。
            ProviderModelCurrentlyNotSupportError: 如果指定模型当前不被支持，则抛出异常。
            CompletionRequestError: 如果完成请求发生错误，则抛出异常。
            ValueError: 如果出现值错误，则抛出异常。
            InternalServerError: 如果发生内部服务器错误，则抛出异常。
        """
        # 检查应用是否为聊天模式
        app_model = installed_app.app
        if app_model.mode != 'chat':
            raise NotChatAppError()

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('inputs', type=dict, required=True, location='json')
        parser.add_argument('query', type=str, required=True, location='json')
        parser.add_argument('files', type=list, required=False, location='json')
        parser.add_argument('response_mode', type=str, choices=['blocking', 'streaming'], location='json')
        parser.add_argument('conversation_id', type=uuid_value, location='json')
        parser.add_argument('retriever_from', type=str, required=False, default='explore_app', location='json')
        args = parser.parse_args()

        # 处理响应模式，决定是否使用流式响应
        streaming = args['response_mode'] == 'streaming'
        args['auto_generate_name'] = False

        # 更新安装应用的最后使用时间
        installed_app.last_used_at = datetime.utcnow()
        db.session.commit()

        try:
            # 调用完成服务，获取聊天响应
            response = CompletionService.completion(
                app_model=app_model,
                user=current_user,
                args=args,
                invoke_from=InvokeFrom.EXPLORE,
                streaming=streaming
            )

            # 返回紧凑的响应格式
            return compact_response(response)
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


class ChatStopApi(InstalledAppResource):
    """
    停止聊天任务的API接口类。
    
    方法:
    post: 接收停止聊天任务的请求。
    
    参数:
    installed_app: 已安装的应用对象，用于获取应用模型。
    task_id: 任务ID，用于标识需要停止的任务。
    
    返回值:
    返回一个包含结果信息的字典和HTTP状态码200，表示成功停止任务。
    """
    
    def post(self, installed_app, task_id):
        # 获取应用模型，并检查应用模式是否为聊天模式
        app_model = installed_app.app
        if app_model.mode != 'chat':
            raise NotChatAppError()  # 如果不是聊天模式，抛出异常

        # 设置任务停止标志
        ApplicationQueueManager.set_stop_flag(task_id, InvokeFrom.EXPLORE, current_user.id)

        # 返回成功结果
        return {'result': 'success'}, 200


def compact_response(response: Union[dict, Generator]) -> Response:
    if isinstance(response, dict):
        return Response(response=json.dumps(response), status=200, mimetype='application/json')
    else:
        def generate() -> Generator:
            yield from response

        return Response(stream_with_context(generate()), status=200,
                        mimetype='text/event-stream')


api.add_resource(CompletionApi, '/installed-apps/<uuid:installed_app_id>/completion-messages', endpoint='installed_app_completion')
api.add_resource(CompletionStopApi, '/installed-apps/<uuid:installed_app_id>/completion-messages/<string:task_id>/stop', endpoint='installed_app_stop_completion')
api.add_resource(ChatApi, '/installed-apps/<uuid:installed_app_id>/chat-messages', endpoint='installed_app_chat_completion')
api.add_resource(ChatStopApi, '/installed-apps/<uuid:installed_app_id>/chat-messages/<string:task_id>/stop', endpoint='installed_app_stop_chat_completion')
