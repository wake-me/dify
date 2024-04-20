import logging

from flask_login import current_user
from flask_restful import Resource, marshal, reqparse
from werkzeug.exceptions import Forbidden, InternalServerError, NotFound

import services
from controllers.console import api
from controllers.console.app.error import (
    CompletionRequestError,
    ProviderModelCurrentlyNotSupportError,
    ProviderNotInitializeError,
    ProviderQuotaExceededError,
)
from controllers.console.datasets.error import DatasetNotInitializedError
from controllers.console.setup import setup_required
from controllers.console.wraps import account_initialization_required
from core.errors.error import (
    LLMBadRequestError,
    ModelCurrentlyNotSupportError,
    ProviderTokenNotInitError,
    QuotaExceededError,
)
from core.model_runtime.errors.invoke import InvokeError
from fields.hit_testing_fields import hit_testing_record_fields
from libs.login import login_required
from services.dataset_service import DatasetService
from services.hit_testing_service import HitTestingService


class HitTestingApi(Resource):
    """
    实现对点击测试API的处理。

    要求用户登录、账户初始化且设置好数据集后才能进行点击测试。
    """

    @setup_required
    @login_required
    @account_initialization_required
    def post(self, dataset_id):
        """
        发起点击测试。

        参数:
        - dataset_id: 数据集的ID，必须是整数。

        返回值:
        - 一个包含查询结果和记录的字典。

        抛出的异常:
        - NotFound: 数据集未找到。
        - Forbidden: 用户没有访问数据集的权限。
        - HighQualityDatasetOnlyError: 仅支持高质量数据集进行点击测试。
        - DatasetNotInitializedError: 数据集未初始化。
        - ProviderNotInitializeError: 提供者未初始化。
        - ProviderQuotaExceededError: 提供者配额超过限制。
        - ProviderModelCurrentlyNotSupportError: 提供者当前不支持的模型。
        - LLMBadRequestError: 没有可用的嵌入模型或重排模型。
        - CompletionRequestError: 完成请求时发生错误。
        - ValueError: 价值错误。
        - InternalServerError: 内部服务错误。
        """
        dataset_id_str = str(dataset_id)

        # 尝试获取数据集，如果不存在则抛出异常
        dataset = DatasetService.get_dataset(dataset_id_str)
        if dataset is None:
            raise NotFound("Dataset not found.")

        # 检查用户是否有访问数据集的权限
        try:
            DatasetService.check_dataset_permission(dataset, current_user)
        except services.errors.account.NoPermissionError as e:
            raise Forbidden(str(e))

        parser = reqparse.RequestParser()
        parser.add_argument('query', type=str, location='json')
        parser.add_argument('retrieval_model', type=dict, required=False, location='json')
        args = parser.parse_args()

        # 参数合法性检查
        HitTestingService.hit_testing_args_check(args)

        try:
            # 执行点击测试并返回结果
            response = HitTestingService.retrieve(
                dataset=dataset,
                query=args['query'],
                account=current_user,
                retrieval_model=args['retrieval_model'],
                limit=10
            )

            # 部分结果字段进行序列化后返回
            return {"query": response['query'], 'records': marshal(response['records'], hit_testing_record_fields)}
        except services.errors.index.IndexNotInitializedError:
            raise DatasetNotInitializedError()
        except ProviderTokenNotInitError as ex:
            raise ProviderNotInitializeError(ex.description)
        except QuotaExceededError:
            raise ProviderQuotaExceededError()
        except ModelCurrentlyNotSupportError:
            raise ProviderModelCurrentlyNotSupportError()
        except LLMBadRequestError:
            # 提供者配置错误，无可用模型
            raise ProviderNotInitializeError(
                "No Embedding Model or Reranking Model available. Please configure a valid provider "
                "in the Settings -> Model Provider.")
        except InvokeError as e:
            raise CompletionRequestError(e.description)
        except ValueError as e:
            raise ValueError(str(e))
        except Exception as e:
            # 记录未处理的异常
            logging.exception("Hit testing failed.")
            raise InternalServerError(str(e))


api.add_resource(HitTestingApi, '/datasets/<uuid:dataset_id>/hit-testing')
