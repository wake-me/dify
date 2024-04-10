import logging

from flask_restful import Resource, reqparse
from werkzeug.exceptions import InternalServerError

from controllers.service_api import api
from controllers.service_api.app.error import (
    CompletionRequestError,
    NotWorkflowAppError,
    ProviderModelCurrentlyNotSupportError,
    ProviderNotInitializeError,
    ProviderQuotaExceededError,
)
from controllers.service_api.wraps import FetchUserArg, WhereisUserArg, validate_app_token
from core.app.apps.base_app_queue_manager import AppQueueManager
from core.app.entities.app_invoke_entities import InvokeFrom
from core.errors.error import ModelCurrentlyNotSupportError, ProviderTokenNotInitError, QuotaExceededError
from core.model_runtime.errors.invoke import InvokeError
from libs import helper
from models.model import App, AppMode, EndUser
from services.app_generate_service import AppGenerateService

logger = logging.getLogger(__name__)


class WorkflowRunApi(Resource):
    @validate_app_token(fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.JSON, required=True))
    def post(self, app_model: App, end_user: EndUser):
        """
        执行工作流
        :param app_model: 应用模型，代表一个具体的应用配置。
        :param end_user: 终端用户，标识执行工作流的用户。
        :return: 返回工作流执行的响应结果。
        """
        # 检查应用模式是否为工作流模式
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode != AppMode.WORKFLOW:
            raise NotWorkflowAppError()

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('inputs', type=dict, required=True, nullable=False, location='json')
        parser.add_argument('files', type=list, required=False, location='json')
        parser.add_argument('response_mode', type=str, choices=['blocking', 'streaming'], location='json')
        args = parser.parse_args()

        # 判断响应模式是否为流式
        streaming = args.get('response_mode') == 'streaming'

        try:
            # 生成工作流执行的响应
            response = AppGenerateService.generate(
                app_model=app_model,
                user=end_user,
                args=args,
                invoke_from=InvokeFrom.SERVICE_API,
                streaming=streaming
            )

            return helper.compact_generate_response(response)
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


class WorkflowTaskStopApi(Resource):
    @validate_app_token(fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.JSON, required=True))
    def post(self, app_model: App, end_user: EndUser, task_id: str):
        """
        停止工作流任务
        :param app_model: 应用模型，代表一个具体的应用配置。
        :param end_user: 终端用户，标识请求的用户。
        :param task_id: 任务ID，标识需要停止的工作流任务。
        :return: 返回停止操作的结果。
        """
        # 检查应用模式是否为工作流模式
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode != AppMode.WORKFLOW:
            raise NotWorkflowAppError()

        # 设置任务停止标志
        AppQueueManager.set_stop_flag(task_id, InvokeFrom.SERVICE_API, end_user.id)

        return {
            "result": "success"
        }

api.add_resource(WorkflowRunApi, '/workflows/run')
api.add_resource(WorkflowTaskStopApi, '/workflows/tasks/<string:task_id>/stop')
