import logging

from flask_restful import reqparse
from werkzeug.exceptions import InternalServerError

from controllers.console import api
from controllers.console.app.error import (
    CompletionRequestError,
    ProviderModelCurrentlyNotSupportError,
    ProviderNotInitializeError,
    ProviderQuotaExceededError,
)
from controllers.console.explore.error import NotWorkflowAppError
from controllers.console.explore.wraps import InstalledAppResource
from core.app.apps.base_app_queue_manager import AppQueueManager
from core.app.entities.app_invoke_entities import InvokeFrom
from core.errors.error import ModelCurrentlyNotSupportError, ProviderTokenNotInitError, QuotaExceededError
from core.model_runtime.errors.invoke import InvokeError
from libs import helper
from libs.login import current_user
from models.model import AppMode, InstalledApp
from services.app_generate_service import AppGenerateService

logger = logging.getLogger(__name__)


class InstalledAppWorkflowRunApi(InstalledAppResource):
    def post(self, installed_app: InstalledApp):
        """
        执行工作流
        
        参数:
        - installed_app: 已安装的应用对象
        
        返回值:
        - 返回工作流执行的响应数据
        
        异常:
        - NotWorkflowAppError: 如果应用不是工作流类型则抛出异常
        - ProviderNotInitializeError: 如果服务提供商未初始化则抛出异常
        - ProviderQuotaExceededError: 如果达到服务提供商的配额限制则抛出异常
        - ProviderModelCurrentlyNotSupportError: 如果当前服务提供商不支持某种模型则抛出异常
        - CompletionRequestError: 如果执行过程中发生错误则抛出异常
        - ValueError: 如果输入值无效则抛出ValueError异常
        - InternalServerError: 如果发生内部服务器错误则抛出异常
        """

        # 获取应用模型和应用模式
        app_model = installed_app.app
        app_mode = AppMode.value_of(app_model.mode)
        
        # 检查应用模式是否为工作流模式
        if app_mode != AppMode.WORKFLOW:
            raise NotWorkflowAppError()

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('inputs', type=dict, required=True, nullable=False, location='json')
        parser.add_argument('files', type=list, required=False, location='json')
        args = parser.parse_args()

        try:
            # 调用服务生成工作流执行的响应
            response = AppGenerateService.generate(
                app_model=app_model,
                user=current_user,
                args=args,
                invoke_from=InvokeFrom.EXPLORE,
                streaming=True
            )

            # 返回压缩后的生成响应
            return helper.compact_generate_response(response)
        except ProviderTokenNotInitError as ex:
            # 提供商未初始化异常处理
            raise ProviderNotInitializeError(ex.description)
        except QuotaExceededError:
            # 配额超过异常处理
            raise ProviderQuotaExceededError()
        except ModelCurrentlyNotSupportError:
            # 当前模型不支持异常处理
            raise ProviderModelCurrentlyNotSupportError()
        except InvokeError as e:
            # 执行错误异常处理
            raise CompletionRequestError(e.description)
        except ValueError as e:
            # 输入值错误异常处理
            raise e
        except Exception as e:
            # 其他内部服务器错误异常处理
            logging.exception("internal server error.")
            raise InternalServerError()

class InstalledAppWorkflowTaskStopApi(InstalledAppResource):
    def post(self, installed_app: InstalledApp, task_id: str):
        """
        停止工作流任务
        
        参数:
        - installed_app: 已安装的应用对象，用来获取应用相关信息
        - task_id: 任务的唯一标识符，用来指定要停止的任务
        
        返回值:
        - 一个包含结果信息的字典，例如 {"result": "success"}
        """
        # 获取应用模型并判断应用模式是否为工作流模式
        app_model = installed_app.app
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode != AppMode.WORKFLOW:
            # 如果应用模式不是工作流模式，则抛出异常
            raise NotWorkflowAppError()

        # 设置停止标志，通知任务管理系统停止指定的任务
        AppQueueManager.set_stop_flag(task_id, InvokeFrom.EXPLORE, current_user.id)

        # 返回操作成功的标志
        return {
            "result": "success"
        }


api.add_resource(InstalledAppWorkflowRunApi, '/installed-apps/<uuid:installed_app_id>/workflows/run')
api.add_resource(InstalledAppWorkflowTaskStopApi, '/installed-apps/<uuid:installed_app_id>/workflows/tasks/<string:task_id>/stop')
