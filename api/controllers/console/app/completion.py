import json
import logging
from collections.abc import Generator
from typing import Union

import flask_login
from flask import Response, stream_with_context
from flask_restful import Resource, reqparse
from werkzeug.exceptions import InternalServerError, NotFound

import services
from controllers.console import api
from controllers.console.app import _get_app
from controllers.console.app.error import (
    AppUnavailableError,
    CompletionRequestError,
    ConversationCompletedError,
    ProviderModelCurrentlyNotSupportError,
    ProviderNotInitializeError,
    ProviderQuotaExceededError,
)
from controllers.console.setup import setup_required
from controllers.console.wraps import account_initialization_required
from core.application_queue_manager import ApplicationQueueManager
from core.entities.application_entities import InvokeFrom
from core.errors.error import ModelCurrentlyNotSupportError, ProviderTokenNotInitError, QuotaExceededError
from core.model_runtime.errors.invoke import InvokeError
from libs.helper import uuid_value
from libs.login import login_required
from services.completion_service import CompletionService


# define completion message api for user
class CompletionMessageApi(Resource):
    """
    完成信息API接口类，提供发送完成信息的功能。
    
    Attributes:
        Resource: 继承自Flask-RESTful的Resource类，用于创建RESTful资源。
    """

    @setup_required
    @login_required
    @account_initialization_required
    def post(self, app_id):
        """
        发送完成信息的POST请求处理函数。
        
        Args:
            app_id (int): 应用的ID，需转换为字符串格式。
            
        Returns:
            返回处理完成信息请求后的响应数据。
            
        Raises:
            NotFound: 如果对话不存在则抛出异常。
            ConversationCompletedError: 如果对话已经完成则抛出异常。
            AppUnavailableError: 如果应用配置损坏则抛出异常。
            ProviderNotInitializeError: 如果服务提供者未初始化则抛出异常。
            ProviderQuotaExceededError: 如果达到服务提供者的配额限制则抛出异常。
            ProviderModelCurrentlyNotSupportError: 如果当前服务提供者不支持指定模型则抛出异常。
            CompletionRequestError: 如果完成请求发生错误则抛出异常。
            ValueError: 如果发生值错误则抛出异常。
            InternalServerError: 如果发生内部服务器错误则抛出异常。
        """
        app_id = str(app_id)

        # 获取应用信息
        app_model = _get_app(app_id, 'completion')

        parser = reqparse.RequestParser()
        parser.add_argument('inputs', type=dict, required=True, location='json')
        parser.add_argument('query', type=str, location='json', default='')
        parser.add_argument('files', type=list, required=False, location='json')
        parser.add_argument('model_config', type=dict, required=True, location='json')
        parser.add_argument('response_mode', type=str, choices=['blocking', 'streaming'], location='json')
        parser.add_argument('retriever_from', type=str, required=False, default='dev', location='json')
        args = parser.parse_args()

        streaming = args['response_mode'] != 'blocking'
        args['auto_generate_name'] = False

        account = flask_login.current_user

        try:
            # 调用完成服务
            response = CompletionService.completion(
                app_model=app_model,
                user=account,
                args=args,
                invoke_from=InvokeFrom.DEBUGGER,
                streaming=streaming,
                is_model_config_override=True
            )

            # 返回紧凑的响应数据
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


class CompletionMessageStopApi(Resource):
    """
    完成消息停止接口的API类。
    
    该类用于处理停止特定任务的请求。
    
    方法:
    - post: 发送停止任务的消息。
    
    参数:
    - app_id: 应用的唯一标识符。
    - task_id: 任务的唯一标识符。
    
    返回值:
    - 一个包含结果信息的字典和HTTP状态码200。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    def post(self, app_id, task_id):
        app_id = str(app_id)  # 确保app_id为字符串格式

        # 获取应用信息
        _get_app(app_id, 'completion')

        account = flask_login.current_user  # 获取当前登录的用户账户

        # 设置停止标志以停止指定任务
        ApplicationQueueManager.set_stop_flag(task_id, InvokeFrom.DEBUGGER, account.id)

        return {'result': 'success'}, 200  # 返回成功消息和状态码


class ChatMessageApi(Resource):
    """
    处理聊天消息的API接口。

    Attributes:
        Resource: 父类，提供RESTful API资源的基本框架。
    """

    @setup_required
    @login_required
    @account_initialization_required
    def post(self, app_id):
        """
        发送聊天消息。

        需要用户登录和应用设置完成。处理用户提交的聊天请求，包括消息内容、查询、文件等，并返回聊天回复。

        Parameters:
            app_id (int): 应用的ID，需转换为字符串格式。

        Returns:
            返回经过压缩的响应数据。

        Raises:
            NotFound: 对话不存在时抛出。
            ConversationCompletedError: 对话已完成时抛出。
            AppUnavailableError: 应用配置错误时抛出。
            ProviderNotInitializeError: 服务提供者未初始化时抛出。
            ProviderQuotaExceededError: 服务提供者配额超出时抛出。
            ProviderModelCurrentlyNotSupportError: 当前服务提供者模型不支持时抛出。
            CompletionRequestError: 完成请求出错时抛出。
            ValueError: 值错误时抛出。
            InternalServerError: 内部服务器错误时抛出。
        """
        app_id = str(app_id)

        # 获取应用信息
        app_model = _get_app(app_id, 'chat')

        parser = reqparse.RequestParser()
        # 解析请求参数
        parser.add_argument('inputs', type=dict, required=True, location='json')
        parser.add_argument('query', type=str, required=True, location='json')
        parser.add_argument('files', type=list, required=False, location='json')
        parser.add_argument('model_config', type=dict, required=True, location='json')
        parser.add_argument('conversation_id', type=uuid_value, location='json')
        parser.add_argument('response_mode', type=str, choices=['blocking', 'streaming'], location='json')
        parser.add_argument('retriever_from', type=str, required=False, default='dev', location='json')
        args = parser.parse_args()

        streaming = args['response_mode'] != 'blocking'
        args['auto_generate_name'] = False

        account = flask_login.current_user

        try:
            # 调用完成服务，处理聊天请求
            response = CompletionService.completion(
                app_model=app_model,
                user=account,
                args=args,
                invoke_from=InvokeFrom.DEBUGGER,
                streaming=streaming,
                is_model_config_override=True
            )

            # 返回压缩后的响应
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


def compact_response(response: Union[dict, Generator]) -> Response:
    if isinstance(response, dict):
        return Response(response=json.dumps(response), status=200, mimetype='application/json')
    else:
        def generate() -> Generator:
            yield from response

        return Response(stream_with_context(generate()), status=200,
                        mimetype='text/event-stream')


class ChatMessageStopApi(Resource):
    """
    停止聊天消息任务的API接口类。
    
    方法:
    post: 停止指定的应用任务。
    
    参数:
    app_id: 应用的ID，需要转换为字符串格式。
    task_id: 任务的ID，用于标识要停止的任务。
    
    返回值:
    返回一个包含结果信息的字典和HTTP状态码200。
    """
    @setup_required
    @login_required
    @account_initialization_required
    def post(self, app_id, task_id):
        app_id = str(app_id)  # 将app_id转换为字符串格式

        # 获取应用信息
        _get_app(app_id, 'chat')

        account = flask_login.current_user  # 获取当前登录的用户账户

        # 为指定任务设置停止标志
        ApplicationQueueManager.set_stop_flag(task_id, InvokeFrom.DEBUGGER, account.id)

        return {'result': 'success'}, 200  # 返回成功标志

api.add_resource(CompletionMessageApi, '/apps/<uuid:app_id>/completion-messages')
api.add_resource(CompletionMessageStopApi, '/apps/<uuid:app_id>/completion-messages/<string:task_id>/stop')
api.add_resource(ChatMessageApi, '/apps/<uuid:app_id>/chat-messages')
api.add_resource(ChatMessageStopApi, '/apps/<uuid:app_id>/chat-messages/<string:task_id>/stop')
