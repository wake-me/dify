from flask import request
from flask_restful import marshal, reqparse

import services.dataset_service
from controllers.service_api import api
from controllers.service_api.dataset.error import DatasetNameDuplicateError
from controllers.service_api.wraps import DatasetApiResource
from core.model_runtime.entities.model_entities import ModelType
from core.provider_manager import ProviderManager
from fields.dataset_fields import dataset_detail_fields
from libs.login import current_user
from models.dataset import Dataset
from services.dataset_service import DatasetService


def _validate_name(name):
    """
    验证提供的名称是否符合特定要求。

    参数:
    name: 字符串，待验证的名称。

    返回值:
    验证通过的名称字符串。

    异常:
    ValueError: 如果名称长度不在1到40个字符之间。
    """
    # 检查名称是否为空，长度是否超出限制
    if not name or len(name) < 1 or len(name) > 40:
        raise ValueError('Name must be between 1 to 40 characters.')
    return name


class DatasetApi(DatasetApiResource):
    """Resource for get datasets."""

    def get(self, tenant_id):
        """
        根据提供的租户ID，获取数据集列表。
        
        参数:
        - self: 方法对象
        - tenant_id: 租户ID，用于获取特定租户的数据集。
        
        返回值:
        - response: 包含数据集信息的响应字典，包括数据、是否还有更多数据、限制数、总数据数和页码。
        - 200: HTTP状态码，表示成功。
        """
        
        # 获取请求参数
        page = request.args.get('page', default=1, type=int)
        limit = request.args.get('limit', default=20, type=int)
        provider = request.args.get('provider', default="vendor")
        search = request.args.get('keyword', default=None, type=str)
        tag_ids = request.args.getlist('tag_ids')

        datasets, total = DatasetService.get_datasets(page, limit, provider,
                                                      tenant_id, current_user, search, tag_ids)
        # check embedding setting
        provider_manager = ProviderManager()
        configurations = provider_manager.get_configurations(
            tenant_id=current_user.current_tenant_id
        )

        # 获取文本嵌入模型配置
        embedding_models = configurations.get_models(
            model_type=ModelType.TEXT_EMBEDDING,
            only_active=True
        )

        model_names = []
        for embedding_model in embedding_models:
            model_names.append(f"{embedding_model.model}:{embedding_model.provider.provider}")
        
        # 使用字段列表对数据集进行格式化
        data = marshal(datasets, dataset_detail_fields)
        for item in data:
            # 根据索引技术类型判断嵌入模型是否可用
            if item['indexing_technique'] == 'high_quality':
                item_model = f"{item['embedding_model']}:{item['embedding_model_provider']}"
                if item_model in model_names:
                    item['embedding_available'] = True
                else:
                    item['embedding_available'] = False
            else:
                item['embedding_available'] = True
                
        # 构建并返回响应
        response = {
            'data': data,
            'has_more': len(datasets) == limit,
            'limit': limit,
            'total': total,
            'page': page
        }
        return response, 200

    """Resource for datasets."""

    def post(self, tenant_id):
        """
        创建一个新的数据集。
        
        参数:
        - tenant_id: 租户ID，用于标识数据集所属的租户。
        
        返回值:
        - 200: 成功创建数据集时返回的数据集详情。
        - 其他: 在创建过程中遇到错误时返回的相应错误信息。
        """
        # 初始化请求解析器，并设置数据集名称的参数
        parser = reqparse.RequestParser()
        parser.add_argument('name', nullable=False, required=True,
                            help='type is required. Name must be between 1 to 40 characters.',
                            type=_validate_name)
        # 设置索引技术的参数
        parser.add_argument('indexing_technique', type=str, location='json',
                            choices=Dataset.INDEXING_TECHNIQUE_LIST,
                            help='Invalid indexing technique.')
        args = parser.parse_args()

        try:
            # 尝试创建一个空的数据集
            dataset = DatasetService.create_empty_dataset(
                tenant_id=tenant_id,
                name=args['name'],
                indexing_technique=args['indexing_technique'],
                account=current_user
            )
        except services.errors.dataset.DatasetNameDuplicateError:
            # 如果遇到数据集名称重复的错误，则抛出该异常
            raise DatasetNameDuplicateError()

        # 返回成功创建的数据集详情
        return marshal(dataset, dataset_detail_fields), 200


api.add_resource(DatasetApi, '/datasets')

