import json
import logging
from collections.abc import Generator
from typing import Union

from flask import Response, stream_with_context
from flask_restful import Resource, reqparse
from werkzeug.exceptions import InternalServerError, NotFound

import services
from controllers.service_api import api
from controllers.service_api.app.error import (
    AppUnavailableError,
    CompletionRequestError,
    ConversationCompletedError,
    NotChatAppError,
    ProviderModelCurrentlyNotSupportError,
    ProviderNotInitializeError,
    ProviderQuotaExceededError,
)
from controllers.service_api.wraps import FetchUserArg, WhereisUserArg, validate_app_token
from core.application_queue_manager import ApplicationQueueManager
from core.entities.application_entities import InvokeFrom
from core.errors.error import ModelCurrentlyNotSupportError, ProviderTokenNotInitError, QuotaExceededError
from core.model_runtime.errors.invoke import InvokeError
from libs.helper import uuid_value
from models.model import App, EndUser
from services.completion_service import CompletionService


class CompletionApi(Resource):
    """
    完成API接口类，用于处理与代码完成相关的请求。
    
    Attributes:
        app_model (App): 应用模型，用于验证和提供应用的详细信息。
        end_user (EndUser): 终端用户信息，用于授权和个性化服务。
    """
    
    @validate_app_token(fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.JSON, required=True))
    def post(self, app_model: App, end_user: EndUser):
        """
        处理提交的代码完成请求。
        
        Args:
            app_model (App): 代表一个应用的模型实例。
            end_user (EndUser): 代表发起请求的终端用户。
            
        Returns:
            返回一个压缩后的响应，具体取决于服务的响应模式。
            
        Raises:
            AppUnavailableError: 如果应用未启用或配置错误。
            NotFound: 如果对话不存在。
            ConversationCompletedError: 如果对话已经完成。
            AppUnavailableError: 如果应用模型配置损坏。
            ProviderNotInitializeError: 如果服务提供者未初始化。
            ProviderQuotaExceededError: 如果配额超出。
            ProviderModelCurrentlyNotSupportError: 如果模型当前不被支持。
            CompletionRequestError: 如果完成请求发生错误。
            ValueError: 如果值无效。
            InternalServerError: 如果发生内部服务器错误。
        """
        
        # 验证应用是否为完成模式
        if app_model.mode != 'completion':
            raise AppUnavailableError()

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('inputs', type=dict, required=True, location='json')
        parser.add_argument('query', type=str, location='json', default='')
        parser.add_argument('files', type=list, required=False, location='json')
        parser.add_argument('response_mode', type=str, choices=['blocking', 'streaming'], location='json')
        parser.add_argument('retriever_from', type=str, required=False, default='dev', location='json')

        args = parser.parse_args()

        # 判断响应模式是否为流式
        streaming = args['response_mode'] == 'streaming'

        # 设置自动生成名称为False
        args['auto_generate_name'] = False

        try:
            # 调用完成服务
            response = CompletionService.completion(
                app_model=app_model,
                user=end_user,
                args=args,
                invoke_from=InvokeFrom.SERVICE_API,
                streaming=streaming,
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

class CompletionStopApi(Resource):
    """
    完成停止API接口类，用于通过POST请求停止指定任务。
    
    参数:
    - app_model: App 类型，表示应用模型，用于验证应用状态。
    - end_user: EndUser 类型，表示请求的终端用户。
    - task_id: 字符串，指定需要停止的任务ID。
    
    返回值:
    - 一个包含结果信息的字典和HTTP状态码200，表示成功停止任务。
    
    异常:
    - 如果应用模式不是'completion'，会抛出AppUnavailableError异常。
    """
    
    @validate_app_token(fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.JSON, required=True))
    def post(self, app_model: App, end_user: EndUser, task_id):
        # 验证应用是否处于完成模式
        if app_model.mode != 'completion':
            raise AppUnavailableError()

        # 设置任务停止标志
        ApplicationQueueManager.set_stop_flag(task_id, InvokeFrom.SERVICE_API, end_user.id)

        return {'result': 'success'}, 200


class ChatApi(Resource):
    """
    聊天API接口类，用于处理聊天相关的API请求。

    Attributes:
        Resource: 父类，提供RESTful资源的基本方法。
    """

    @validate_app_token(fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.JSON, required=True))
    def post(self, app_model: App, end_user: EndUser):
        """
        处理聊天请求，根据提供的应用模型和终端用户信息，完成特定的聊天任务。

        Args:
            app_model: App 类型，代表应用模型，用于确定聊天的模式和配置。
            end_user: EndUser 类型，代表发起聊天请求的终端用户。

        Returns:
            返回聊天响应结果，格式化后的响应数据。

        Raises:
            NotChatAppError: 如果应用模型不是聊天模式，则抛出异常。
            NotFound: 如果对话不存在，则抛出异常。
            ConversationCompletedError: 如果对话已经完成，则抛出异常。
            AppUnavailableError: 如果应用模型配置错误，则抛出异常。
            ProviderNotInitializeError: 如果服务提供者未初始化，则抛出异常。
            ProviderQuotaExceededError: 如果达到服务提供者的配额限制，则抛出异常。
            ProviderModelCurrentlyNotSupportError: 如果当前服务提供者不支持指定模型，则抛出异常。
            CompletionRequestError: 如果完成请求发生错误，则抛出异常。
            InternalServerError: 如果发生内部服务器错误，则抛出异常。
        """

        # 检查应用模型是否为聊天模式
        if app_model.mode != 'chat':
            raise NotChatAppError()

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('inputs', type=dict, required=True, location='json')
        parser.add_argument('query', type=str, required=True, location='json')
        parser.add_argument('files', type=list, required=False, location='json')
        parser.add_argument('response_mode', type=str, choices=['blocking', 'streaming'], location='json')
        parser.add_argument('conversation_id', type=uuid_value, location='json')
        parser.add_argument('retriever_from', type=str, required=False, default='dev', location='json')
        parser.add_argument('auto_generate_name', type=bool, required=False, default=True, location='json')

        args = parser.parse_args()

        # 判断响应模式是否为流式
        streaming = args['response_mode'] == 'streaming'

        try:
            # 调用完成服务，获取聊天响应
            response = CompletionService.completion(
                app_model=app_model,
                user=end_user,
                args=args,
                invoke_from=InvokeFrom.SERVICE_API,
                streaming=streaming
            )

            # 返回紧凑格式的聊天响应
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

class ChatStopApi(Resource):
    """
    停止聊天API的类，用于处理停止聊天任务的请求。
    
    方法:
    - post: 停止指定聊天任务。
    
    参数:
    - app_model: 应用模型，包含应用的相关信息。
    - end_user: 终端用户信息。
    - task_id: 任务ID，标识需要停止的聊天任务。
    
    返回值:
    - 一个包含结果信息的字典和HTTP状态码200，表示成功停止聊天任务。
    """
    
    @validate_app_token(fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.JSON, required=True))
    def post(self, app_model: App, end_user: EndUser, task_id):
        """
        处理停止聊天任务的POST请求。
        
        参数:
        - app_model: 应用模型，包含应用的相关信息。
        - end_user: 终端用户信息。
        - task_id: 任务ID，标识需要停止的聊天任务。
        
        返回值:
        - 一个包含结果信息的字典和HTTP状态码200，表示成功停止聊天任务。
        """
        # 检查应用模式是否为聊天模式
        if app_model.mode != 'chat':
            raise NotChatAppError()

        # 设置停止标志，以停止指定的任务
        ApplicationQueueManager.set_stop_flag(task_id, InvokeFrom.SERVICE_API, end_user.id)

        return {'result': 'success'}, 200


def compact_response(response: Union[dict, Generator]) -> Response:
    if isinstance(response, dict):
        return Response(response=json.dumps(response), status=200, mimetype='application/json')
    else:
        def generate() -> Generator:
            yield from response

        return Response(stream_with_context(generate()), status=200,
                        mimetype='text/event-stream')


api.add_resource(CompletionApi, '/completion-messages')
api.add_resource(CompletionStopApi, '/completion-messages/<string:task_id>/stop')
api.add_resource(ChatApi, '/chat-messages')
api.add_resource(ChatStopApi, '/chat-messages/<string:task_id>/stop')
