import flask_restful
from flask import request
from flask_login import current_user
from flask_restful import Resource, marshal, marshal_with, reqparse
from werkzeug.exceptions import Forbidden, NotFound

import services
from configs import dify_config
from controllers.console import api
from controllers.console.apikey import api_key_fields, api_key_list
from controllers.console.app.error import ProviderNotInitializeError
from controllers.console.datasets.error import DatasetInUseError, DatasetNameDuplicateError, IndexingEstimateError
from controllers.console.setup import setup_required
from controllers.console.wraps import account_initialization_required
from core.errors.error import LLMBadRequestError, ProviderTokenNotInitError
from core.indexing_runner import IndexingRunner
from core.model_runtime.entities.model_entities import ModelType
from core.provider_manager import ProviderManager
from core.rag.datasource.vdb.vector_type import VectorType
from core.rag.extractor.entity.extract_setting import ExtractSetting
from core.rag.retrieval.retrival_methods import RetrievalMethod
from extensions.ext_database import db
from fields.app_fields import related_app_list
from fields.dataset_fields import dataset_detail_fields, dataset_query_detail_fields
from fields.document_fields import document_status_fields
from libs.login import login_required
from models.dataset import Dataset, DatasetPermissionEnum, Document, DocumentSegment
from models.model import ApiToken, UploadFile
from services.dataset_service import DatasetPermissionService, DatasetService, DocumentService


def _validate_name(name):
    """
    验证给定的名字是否符合要求。

    参数:
    name: 字符串，要验证的名字。

    返回值:
    验证通过后返回原始名字。

    异常:
    ValueError: 如果名字为空、长度小于1或大于40个字符，则抛出此异常。
    """
    if not name or len(name) < 1 or len(name) > 40:
        raise ValueError('Name must be between 1 to 40 characters.')
    return name


def _validate_description_length(description):
    """
    验证给定描述的长度是否符合要求。

    参数:
    description: 字符串，要验证的描述信息。

    返回值:
    验证通过后返回原始描述信息。

    异常:
    ValueError: 如果描述信息长度超过400个字符，则抛出此异常。
    """
    if len(description) > 400:
        raise ValueError('Description cannot exceed 400 characters.')
    return description


class DatasetListApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        """
        处理GET请求，获取数据集信息。
        
        从请求参数中获取分页信息、指定数据集ID列表、供应商信息等，并根据这些信息查询相应的数据集。
        如果指定了数据集ID，则直接获取这些数据集的信息；否则，根据页码、每页数量、供应商等条件进行查询。
        还会检查相关的文本嵌入模型配置，以确定哪些数据集配备了可用的嵌入模型。
        
        返回值:
            - response: 包含数据集信息的响应字典，包括数据列表、是否有更多数据、每页数量、总数量和当前页码。
            - 200: HTTP状态码，表示请求成功。
        """
        
        # 从请求中获取页码、每页数量、数据集ID和供应商信息
        page = request.args.get('page', default=1, type=int)
        limit = request.args.get('limit', default=20, type=int)
        ids = request.args.getlist('ids')
        provider = request.args.get('provider', default="vendor")
        search = request.args.get('keyword', default=None, type=str)
        tag_ids = request.args.getlist('tag_ids')

        if ids:
            datasets, total = DatasetService.get_datasets_by_ids(ids, current_user.current_tenant_id)
        else:
            datasets, total = DatasetService.get_datasets(page, limit, provider,
                                                          current_user.current_tenant_id, current_user, search, tag_ids)

        # check embedding setting
        provider_manager = ProviderManager()
        configurations = provider_manager.get_configurations(
            tenant_id=current_user.current_tenant_id
        )

        # 筛选出文本嵌入模型，并收集其名称
        embedding_models = configurations.get_models(
            model_type=ModelType.TEXT_EMBEDDING,
            only_active=True
        )

        model_names = []
        for embedding_model in embedding_models:
            model_names.append(f"{embedding_model.model}:{embedding_model.provider.provider}")
        
        # 对查询到的数据集进行格式化，并根据嵌入模型的配置，标记哪些数据集的嵌入模型可用
        data = marshal(datasets, dataset_detail_fields)
        for item in data:
            if item['indexing_technique'] == 'high_quality':
                item_model = f"{item['embedding_model']}:{item['embedding_model_provider']}"
                if item_model in model_names:
                    item['embedding_available'] = True
                else:
                    item['embedding_available'] = False
            else:
                item['embedding_available'] = True

            if item.get('permission') == 'partial_members':
                part_users_list = DatasetPermissionService.get_dataset_partial_member_list(item['id'])
                item.update({'partial_member_list': part_users_list})
            else:
                item.update({'partial_member_list': []})

        response = {
            'data': data,
            'has_more': len(datasets) == limit,
            'limit': limit,
            'total': total,
            'page': page
        }
        return response, 200

    @setup_required
    @login_required
    @account_initialization_required
    def post(self):
        """
        创建一个新的数据集。
        
        要求用户具有管理员或所有者角色。
        
        参数:
        - name: 数据集名称，必填，长度1到40个字符。
        - indexing_technique: 索引技术类型，可选，必须在预定义的索引技术列表中。

        返回值:
        - 创建成功的数据集详情，HTTP状态码201。
        
        抛出异常:
        - Forbidden: 当前用户不是管理员或所有者。
        - DatasetNameDuplicateError: 数据集名称重复。
        """

        # 初始化请求参数解析器
        parser = reqparse.RequestParser()
        # 添加数据集名称参数，必填，长度限制，类型验证
        parser.add_argument('name', nullable=False, required=True,
                            help='type is required. Name must be between 1 to 40 characters.',
                            type=_validate_name)
        # 添加索引技术参数，可选，类型限制，从请求JSON中获取
        parser.add_argument('indexing_technique', type=str, location='json',
                            choices=Dataset.INDEXING_TECHNIQUE_LIST,
                            nullable=True,
                            help='Invalid indexing technique.')
        args = parser.parse_args()

        # The role of the current user in the ta table must be admin, owner, or editor, or dataset_operator
        if not current_user.is_dataset_editor:
            raise Forbidden()

        try:
            # 尝试创建空数据集
            dataset = DatasetService.create_empty_dataset(
                tenant_id=current_user.current_tenant_id,
                name=args['name'],
                indexing_technique=args['indexing_technique'],
                account=current_user
            )
        except services.errors.dataset.DatasetNameDuplicateError:
            # 数据集名称重复时抛出异常
            raise DatasetNameDuplicateError()

        # 返回创建成功的数据集信息
        return marshal(dataset, dataset_detail_fields), 201


class DatasetApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def get(self, dataset_id):
        """
        根据数据集ID获取数据集详情。
        
        参数:
        - dataset_id: 数据集的唯一标识符。
        
        返回值:
        - 一个元组，包含数据集的详细信息（经过格式化）和HTTP状态码200。
        - 如果数据集不存在或用户无权限访问，则抛出相应的异常。
        """
        dataset_id_str = str(dataset_id)  # 将数据集ID转换为字符串
        dataset = DatasetService.get_dataset(dataset_id_str)  # 根据ID获取数据集
        if dataset is None:  # 如果数据集不存在，则抛出未找到异常
            raise NotFound("Dataset not found.")
        try:
            # 检查当前用户是否有访问数据集的权限
            DatasetService.check_dataset_permission(
                dataset, current_user)
        except services.errors.account.NoPermissionError as e:  # 如果无权限，则抛出禁止访问异常
            raise Forbidden(str(e))
        data = marshal(dataset, dataset_detail_fields)
        if data.get('permission') == 'partial_members':
            part_users_list = DatasetPermissionService.get_dataset_partial_member_list(dataset_id_str)
            data.update({'partial_member_list': part_users_list})

        # check embedding setting
        provider_manager = ProviderManager()
        configurations = provider_manager.get_configurations(
            tenant_id=current_user.current_tenant_id
        )

        # 获取当前租户的所有文本嵌入模型配置
        embedding_models = configurations.get_models(
            model_type=ModelType.TEXT_EMBEDDING,
            only_active=True
        )

        model_names = []
        for embedding_model in embedding_models:
            model_names.append(f"{embedding_model.model}:{embedding_model.provider.provider}")  # 构建模型名称列表

        # 根据索引技术类型检查嵌入是否可用
        if data['indexing_technique'] == 'high_quality':
            item_model = f"{data['embedding_model']}:{data['embedding_model_provider']}"
            if item_model in model_names:  # 如果数据集使用的嵌入模型在可用模型列表中，则嵌入可用
                data['embedding_available'] = True
            else:  # 否则，嵌入不可用
                data['embedding_available'] = False
        else:  # 如果索引技术不是高质索引，则默认嵌入可用
            data['embedding_available'] = True

        if data.get('permission') == 'partial_members':
            part_users_list = DatasetPermissionService.get_dataset_partial_member_list(dataset_id_str)
            data.update({'partial_member_list': part_users_list})

        return data, 200

    @setup_required
    @login_required
    @account_initialization_required
    def patch(self, dataset_id):
        """
        更新数据集的信息。
        
        参数:
        - dataset_id: 数据集的唯一标识符，可以是整数或字符串。
        
        返回值:
        - 一个包含更新后数据集信息的JSON对象，以及HTTP状态码200。
        
        抛出的异常:
        - NotFound: 如果指定的数据集不存在。
        - Forbidden: 如果当前用户没有权限更新数据集。
        """

        dataset_id_str = str(dataset_id)  # 将dataset_id转换为字符串
        dataset = DatasetService.get_dataset(dataset_id_str)  # 根据ID获取数据集
        if dataset is None:
            raise NotFound("Dataset not found.")

        parser = reqparse.RequestParser()  # 初始化请求参数解析器
        # 添加必要的参数解析规则
        parser.add_argument('name', nullable=False,
                            help='type is required. Name must be between 1 to 40 characters.',
                            type=_validate_name)
        parser.add_argument('description',
                            location='json', store_missing=False,
                            type=_validate_description_length)
        parser.add_argument('indexing_technique', type=str, location='json',
                            choices=Dataset.INDEXING_TECHNIQUE_LIST,
                            nullable=True,
                            help='Invalid indexing technique.')
        parser.add_argument('permission', type=str, location='json', choices=(
            DatasetPermissionEnum.ONLY_ME, DatasetPermissionEnum.ALL_TEAM, DatasetPermissionEnum.PARTIAL_TEAM), help='Invalid permission.'
                            )
        parser.add_argument('embedding_model', type=str,
                            location='json', help='Invalid embedding model.')
        parser.add_argument('embedding_model_provider', type=str,
                            location='json', help='Invalid embedding model provider.')
        parser.add_argument('retrieval_model', type=dict, location='json', help='Invalid retrieval model.')
        parser.add_argument('partial_member_list', type=list, location='json', help='Invalid parent user list.')
        args = parser.parse_args()
        data = request.get_json()

        # check embedding model setting
        if data.get('indexing_technique') == 'high_quality':
            DatasetService.check_embedding_model_setting(dataset.tenant_id,
                                                         data.get('embedding_model_provider'),
                                                         data.get('embedding_model')
                                                         )

        # The role of the current user in the ta table must be admin, owner, editor, or dataset_operator
        DatasetPermissionService.check_permission(
            current_user, dataset, data.get('permission'), data.get('partial_member_list')
        )

        dataset = DatasetService.update_dataset(
            dataset_id_str, args, current_user)  # 更新数据集

        if dataset is None:
            raise NotFound("Dataset not found.")

        result_data = marshal(dataset, dataset_detail_fields)
        tenant_id = current_user.current_tenant_id

        if data.get('partial_member_list') and data.get('permission') == 'partial_members':
            DatasetPermissionService.update_partial_member_list(
                tenant_id, dataset_id_str, data.get('partial_member_list')
            )
        # clear partial member list when permission is only_me or all_team_members
        elif data.get('permission') == DatasetPermissionEnum.ONLY_ME or data.get('permission') == DatasetPermissionEnum.ALL_TEAM:
            DatasetPermissionService.clear_partial_member_list(dataset_id_str)

        partial_member_list = DatasetPermissionService.get_dataset_partial_member_list(dataset_id_str)
        result_data.update({'partial_member_list': partial_member_list})

        return result_data, 200

    @setup_required
    @login_required
    @account_initialization_required
    def delete(self, dataset_id):
        """
        删除指定的数据集。

        参数:
        - dataset_id: 数据集的ID，可以是整数或字符串。

        返回值:
        - 当数据集成功被删除时，返回一个包含结果信息的字典和HTTP状态码204；
        - 当删除操作失败或数据集不存在时，抛出相应的异常。

        异常:
        - Forbidden: 当前用户没有权限删除数据集（不是管理员或所有者）。
        - NotFound: 数据集不存在。
        """
        dataset_id_str = str(dataset_id)

        # The role of the current user in the ta table must be admin, owner, or editor
        if not current_user.is_editor or current_user.is_dataset_operator:
            raise Forbidden()

        try:
            if DatasetService.delete_dataset(dataset_id_str, current_user):
                DatasetPermissionService.clear_partial_member_list(dataset_id_str)
                return {'result': 'success'}, 204
            else:
                raise NotFound("Dataset not found.")
        except services.errors.dataset.DatasetInUseError:
            raise DatasetInUseError()

class DatasetUseCheckApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def get(self, dataset_id):
        dataset_id_str = str(dataset_id)

        dataset_is_using = DatasetService.dataset_use_check(dataset_id_str)
        return {'is_using': dataset_is_using}, 200

class DatasetQueryApi(Resource):
    """
    数据集查询接口API类，提供获取特定数据集的查询历史的功能。
    
    继承自Resource，用以定义API资源。
    """

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, dataset_id):
        """
        获取指定数据集的查询历史。
        
        参数:
        - dataset_id: 数据集的唯一标识符。
        
        返回值:
        - 一个包含查询历史信息的字典，以及HTTP状态码200。
        
        异常:
        - NotFound: 如果数据集不存在。
        - Forbidden: 如果当前用户没有权限访问该数据集。
        """
        # 将传入的dataset_id转换为字符串类型
        dataset_id_str = str(dataset_id)
        # 尝试根据dataset_id获取数据集信息
        dataset = DatasetService.get_dataset(dataset_id_str)
        if dataset is None:
            # 如果数据集不存在，抛出异常
            raise NotFound("Dataset not found.")

        try:
            # 检查当前用户是否有访问该数据集的权限
            DatasetService.check_dataset_permission(dataset, current_user)
        except services.errors.account.NoPermissionError as e:
            # 如果无权限，抛出异常
            raise Forbidden(str(e))

        # 从请求参数中获取页码和每页数量，默认值分别为1和20
        page = request.args.get('page', default=1, type=int)
        limit = request.args.get('limit', default=20, type=int)

        # 获取指定数据集的查询历史，以及总查询次数
        dataset_queries, total = DatasetService.get_dataset_queries(
            dataset_id=dataset.id,
            page=page,
            per_page=limit
        )

        # 构建并返回查询历史的响应信息
        response = {
            'data': marshal(dataset_queries, dataset_query_detail_fields),  # 使用字段映射序列化查询结果
            'has_more': len(dataset_queries) == limit,  # 标记是否还有更多查询历史
            'limit': limit,  # 返回每页数量
            'total': total,  # 返回总查询次数
            'page': page  # 返回当前页码
        }
        return response, 200


class DatasetIndexingEstimateApi(Resource):
    """
    提供对数据集索引估计的API接口。
    
    要求用户登录且账户已初始化，需要提供包括信息列表、处理规则、索引技术等参数。
    根据提供的信息类型（如上传文件或Notion导入），计算索引预估信息。
    """

    @setup_required
    @login_required
    @account_initialization_required
    def post(self):
        """
        处理POST请求，进行索引估计。
        
        参数:
        - info_list: 信息列表，包括数据源类型和相应的详细信息。
        - process_rule: 处理规则，定义如何处理文档。
        - indexing_technique: 索引技术，选择用于索引的特定技术。
        - doc_form: 文档形式，默认为"text_model"。
        - dataset_id: 数据集ID，可选。
        - doc_language: 文档语言，默认为"English"。
        
        返回:
        - response: 索引估计的响应信息。
        - 200: HTTP状态码，表示成功。
        """
        parser = reqparse.RequestParser()
        # 解析请求参数
        parser.add_argument('info_list', type=dict, required=True, nullable=True, location='json')
        parser.add_argument('process_rule', type=dict, required=True, nullable=True, location='json')
        parser.add_argument('indexing_technique', type=str, required=True,
                            choices=Dataset.INDEXING_TECHNIQUE_LIST,
                            nullable=True, location='json')
        parser.add_argument('doc_form', type=str, default='text_model', required=False, nullable=False, location='json')
        parser.add_argument('dataset_id', type=str, required=False, nullable=False, location='json')
        parser.add_argument('doc_language', type=str, default='English', required=False, nullable=False,
                            location='json')
        args = parser.parse_args()
        # 验证参数
        DocumentService.estimate_args_validate(args)
        
        extract_settings = []
        # 根据数据源类型处理提取设置
        if args['info_list']['data_source_type'] == 'upload_file':
            # 处理上传文件类型的数据源
            file_ids = args['info_list']['file_info_list']['file_ids']
            file_details = db.session.query(UploadFile).filter(
                UploadFile.tenant_id == current_user.current_tenant_id,
                UploadFile.id.in_(file_ids)
            ).all()
            
            if file_details is None:
                raise NotFound("File not found.")
            
            for file_detail in file_details:
                extract_setting = ExtractSetting(
                    datasource_type="upload_file",
                    upload_file=file_detail,
                    document_model=args['doc_form']
                )
                extract_settings.append(extract_setting)
        elif args['info_list']['data_source_type'] == 'notion_import':
            # 处理Notion导入类型的数据源
            notion_info_list = args['info_list']['notion_info_list']
            for notion_info in notion_info_list:
                workspace_id = notion_info['workspace_id']
                for page in notion_info['pages']:
                    extract_setting = ExtractSetting(
                        datasource_type="notion_import",
                        notion_info={
                            "notion_workspace_id": workspace_id,
                            "notion_obj_id": page['page_id'],
                            "notion_page_type": page['type'],
                            "tenant_id": current_user.current_tenant_id
                        },
                        document_model=args['doc_form']
                    )
                    extract_settings.append(extract_setting)
        elif args['info_list']['data_source_type'] == 'website_crawl':
            website_info_list = args['info_list']['website_info_list']
            for url in website_info_list['urls']:
                extract_setting = ExtractSetting(
                    datasource_type="website_crawl",
                    website_info={
                        "provider": website_info_list['provider'],
                        "job_id": website_info_list['job_id'],
                        "url": url,
                        "tenant_id": current_user.current_tenant_id,
                        "mode": 'crawl',
                        "only_main_content": website_info_list['only_main_content']
                    },
                    document_model=args['doc_form']
                )
                extract_settings.append(extract_setting)
        else:
            raise ValueError('Data source type not support')
        
        indexing_runner = IndexingRunner()
        try:
            # 执行索引估计
            response = indexing_runner.indexing_estimate(current_user.current_tenant_id, extract_settings,
                                                         args['process_rule'], args['doc_form'],
                                                         args['doc_language'], args['dataset_id'],
                                                         args['indexing_technique'])
        except LLMBadRequestError:
            # 处理无效请求错误
            raise ProviderNotInitializeError(
                "No Embedding Model available. Please configure a valid provider "
                "in the Settings -> Model Provider.")
        except ProviderTokenNotInitError as ex:
            # 处理提供商令牌未初始化错误
            raise ProviderNotInitializeError(ex.description)
        except Exception as e:
            raise IndexingEstimateError(str(e))

        return response, 200


class DatasetRelatedAppListApi(Resource):
    """
    与数据集相关的应用列表API
    此类提供了一个接口，用于获取指定数据集关联的应用列表
    """

    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(related_app_list)
    def get(self, dataset_id):
        """
        获取指定数据集关联的应用列表
        
        参数:
        - dataset_id: 数据集的ID，整数
        
        返回值:
        - 一个包含关联应用信息的字典，以及HTTP状态码200
        字典格式如下:
        {
            'data': related_apps,  # 关联的应用列表
            'total': len(related_apps)  # 关联应用的总数
        }
        
        异常:
        - NotFound: 数据集不存在时抛出
        - Forbidden: 用户没有数据集的访问权限时抛出
        """
        dataset_id_str = str(dataset_id)  # 将数据集ID转换为字符串
        dataset = DatasetService.get_dataset(dataset_id_str)  # 根据ID获取数据集
        if dataset is None:
            raise NotFound("Dataset not found.")  # 如果数据集不存在，抛出异常

        # 检查当前用户是否有访问该数据集的权限
        try:
            DatasetService.check_dataset_permission(dataset, current_user)
        except services.errors.account.NoPermissionError as e:
            raise Forbidden(str(e))  # 如果无权限，抛出异常

        app_dataset_joins = DatasetService.get_related_apps(dataset.id)  # 获取数据集关联的应用关系

        related_apps = []  # 初始化关联应用列表
        for app_dataset_join in app_dataset_joins:
            app_model = app_dataset_join.app
            if app_model:
                related_apps.append(app_model)  # 将有效的应用模型添加到列表

        return {
            'data': related_apps,
            'total': len(related_apps)
        }, 200  # 返回关联应用列表及总数

class DatasetIndexingStatusApi(Resource):
    """
    数据集索引状态API，用于获取特定数据集的索引状态。

    Attributes:
        Resource: Flask-RESTful提供的资源类，用于处理RESTful API请求。
    """

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, dataset_id):
        """
        获取指定数据集的索引状态。

        Args:
            dataset_id (int): 数据集的唯一标识符。

        Returns:
            dict: 包含数据集文档状态信息的字典。
        """
        dataset_id = str(dataset_id)  # 将传入的dataset_id转换为字符串格式
        # 从数据库中查询与当前用户和指定数据集相关的文档
        documents = db.session.query(Document).filter(
            Document.dataset_id == dataset_id,
            Document.tenant_id == current_user.current_tenant_id
        ).all()
        
        documents_status = []  # 用于存储文档状态信息的列表
        
        # 遍历查询到的文档，计算每个文档完成和总共的片段数
        for document in documents:
            # 计算已完成的片段数
            completed_segments = DocumentSegment.query.filter(DocumentSegment.completed_at.isnot(None),
                                                              DocumentSegment.document_id == str(document.id),
                                                              DocumentSegment.status != 're_segment').count()
            # 计算总共的片段数
            total_segments = DocumentSegment.query.filter(DocumentSegment.document_id == str(document.id),
                                                          DocumentSegment.status != 're_segment').count()
            document.completed_segments = completed_segments  # 将已完成片段数赋值给文档对象
            document.total_segments = total_segments  # 将总片段数赋值给文档对象
            # 将文档状态信息进行封装，并添加到documents_status列表中
            documents_status.append(marshal(document, document_status_fields))
        
        # 将文档状态信息列表封装到data字典中，并返回
        data = {
            'data': documents_status
        }
        return data


class DatasetApiKeyApi(Resource):
    # DatasetApiKeyApi类：处理数据集API密钥的请求
    
    max_keys = 10  # 允许的最大API密钥数量
    token_prefix = 'dataset-'  # API密钥的前缀
    resource_type = 'dataset'  # 资源类型标识为数据集

    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(api_key_list)
    def get(self):
        """
        获取当前用户数据集资源类型的API密钥列表
        
        返回值:
            包含API密钥信息的列表: {"items": [密钥信息1, 密钥信息2, ...]}
        """
        # 从数据库查询当前用户数据集类型的API密钥
        keys = db.session.query(ApiToken). \
            filter(ApiToken.type == self.resource_type, ApiToken.tenant_id == current_user.current_tenant_id). \
            all()
        return {"items": keys}

    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(api_key_fields)
    def post(self):
        """
        为当前用户创建一个数据集API密钥
        
        返回值:
            新创建的API密钥信息: api_token, 200（HTTP状态码为200表示成功）
            
        异常:
            如果当前用户角色不是管理员或所有者，抛出Forbidden异常
            如果已达到最大API密钥数量限制，返回400错误码和相关消息
        """
        # 检查用户是否有权限创建API密钥
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        # 统计当前用户数据集类型的API密钥数量
        current_key_count = db.session.query(ApiToken). \
            filter(ApiToken.type == self.resource_type, ApiToken.tenant_id == current_user.current_tenant_id). \
            count()

        # 检查是否超过允许的最大API密钥数量
        if current_key_count >= self.max_keys:
            flask_restful.abort(
                400,
                message=f"Cannot create more than {self.max_keys} API keys for this resource type.",
                code='max_keys_exceeded'
            )

        # 生成新的API密钥
        key = ApiToken.generate_api_key(self.token_prefix, 24)
        api_token = ApiToken()
        api_token.tenant_id = current_user.current_tenant_id
        api_token.token = key
        api_token.type = self.resource_type
        db.session.add(api_token)
        db.session.commit()
        return api_token, 200


class DatasetApiDeleteApi(Resource):
    # 类 DatasetApiDeleteApi 用于处理数据集 API 的删除请求
    resource_type = 'dataset'  # 指定资源类型为数据集

    @setup_required
    @login_required
    @account_initialization_required
    def delete(self, api_key_id):
        """
        删除指定的 API 密钥
        :param api_key_id: 需要被删除的 API 密钥的ID，必须是整数或字符串
        :return: 删除成功则返回一个包含结果信息的字典和 HTTP 状态码 204，若删除失败则抛出异常
        """
        api_key_id = str(api_key_id)  # 确保 api_key_id 为字符串格式

        # 检查当前用户是否有权限删除 API 密钥（必须是管理员或所有者）
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        # 查询指定的 API 密钥是否存在
        key = db.session.query(ApiToken). \
            filter(ApiToken.tenant_id == current_user.current_tenant_id, ApiToken.type == self.resource_type,
                   ApiToken.id == api_key_id). \
            first()

        if key is None:
            # 如果指定的 API 密钥不存在，则返回 404 错误
            flask_restful.abort(404, message='API key not found')

        # 删除指定的 API 密钥并提交数据库事务
        db.session.query(ApiToken).filter(ApiToken.id == api_key_id).delete()
        db.session.commit()

        # 返回删除成功的消息
        return {'result': 'success'}, 204


class DatasetApiBaseUrlApi(Resource):
    """
    提供数据集API基础URL的类。
    
    该类继承自Resource，用于通过GET请求获取当前应用的服务API基础URL。
    不接受任何参数。
    
    返回值:
        dict: 包含一个键'api_base_url'，其值为服务API的基础URL。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        """
        处理GET请求，返回数据集API的基础URL。
        
        需要设置、登录和账户初始化才能访问。
        
        返回:
            dict: 包含服务API基础URL的字典。
        """
        # 根据应用配置获取服务API的URL，如果未配置，则使用当前请求的主机URL
        return {
            'api_base_url': (dify_config.SERVICE_API_URL if dify_config.SERVICE_API_URL
                             else request.host_url.rstrip('/')) + '/v1'
        }


class DatasetRetrievalSettingApi(Resource):
    """
    数据集检索设置API接口类，用于获取当前配置的检索方法。
    
    该接口需要用户登录、账户初始化且设置了检索相关的配置。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        vector_type = dify_config.VECTOR_STORE
        match vector_type:
            case VectorType.MILVUS | VectorType.RELYT | VectorType.PGVECTOR | VectorType.TIDB_VECTOR | VectorType.CHROMA | VectorType.TENCENT:
                return {
                    'retrieval_method': [
                        RetrievalMethod.SEMANTIC_SEARCH.value
                    ]
                }
            case VectorType.QDRANT | VectorType.WEAVIATE | VectorType.OPENSEARCH | VectorType.ANALYTICDB | VectorType.MYSCALE | VectorType.ORACLE | VectorType.ELASTICSEARCH:
                return {
                    'retrieval_method': [
                        RetrievalMethod.SEMANTIC_SEARCH.value,
                        RetrievalMethod.FULL_TEXT_SEARCH.value,
                        RetrievalMethod.HYBRID_SEARCH.value,
                    ]
                }
            case _:
                raise ValueError(f"Unsupported vector db type {vector_type}.")


class DatasetRetrievalSettingMockApi(Resource):
    """
    数据集检索设置模拟API类，用于提供检索方法的配置信息。
    
    方法:
    - get: 根据向量数据库类型获取相应的检索方法配置。
    
    参数:
    - vector_type: 字符串，指定使用的向量数据库类型。
    
    返回值:
    - 一个字典，包含支持的检索方法列表。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    def get(self, vector_type):
        match vector_type:
            case VectorType.MILVUS | VectorType.RELYT | VectorType.TIDB_VECTOR | VectorType.CHROMA | VectorType.TENCENT | VectorType.PGVECTO_RS:
                return {
                    'retrieval_method': [
                        RetrievalMethod.SEMANTIC_SEARCH.value
                    ]
                }
            case VectorType.QDRANT | VectorType.WEAVIATE | VectorType.OPENSEARCH | VectorType.ANALYTICDB | VectorType.MYSCALE | VectorType.ORACLE | VectorType.ELASTICSEARCH | VectorType.PGVECTOR:
                return {
                    'retrieval_method': [
                        RetrievalMethod.SEMANTIC_SEARCH.value,
                        RetrievalMethod.FULL_TEXT_SEARCH.value,
                        RetrievalMethod.HYBRID_SEARCH.value,
                    ]
                }
            case _:
                raise ValueError(f"Unsupported vector db type {vector_type}.")



class DatasetErrorDocs(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def get(self, dataset_id):
        dataset_id_str = str(dataset_id)
        dataset = DatasetService.get_dataset(dataset_id_str)
        if dataset is None:
            raise NotFound("Dataset not found.")
        results = DocumentService.get_error_documents_by_dataset_id(dataset_id_str)

        return {
            'data': [marshal(item, document_status_fields) for item in results],
            'total': len(results)
        }, 200


class DatasetPermissionUserListApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def get(self, dataset_id):
        dataset_id_str = str(dataset_id)
        dataset = DatasetService.get_dataset(dataset_id_str)
        if dataset is None:
            raise NotFound("Dataset not found.")
        try:
            DatasetService.check_dataset_permission(dataset, current_user)
        except services.errors.account.NoPermissionError as e:
            raise Forbidden(str(e))

        partial_members_list = DatasetPermissionService.get_dataset_partial_member_list(dataset_id_str)

        return {
            'data': partial_members_list,
        }, 200


api.add_resource(DatasetListApi, '/datasets')
api.add_resource(DatasetApi, '/datasets/<uuid:dataset_id>')
api.add_resource(DatasetUseCheckApi, '/datasets/<uuid:dataset_id>/use-check')
api.add_resource(DatasetQueryApi, '/datasets/<uuid:dataset_id>/queries')
api.add_resource(DatasetErrorDocs, '/datasets/<uuid:dataset_id>/error-docs')
api.add_resource(DatasetIndexingEstimateApi, '/datasets/indexing-estimate')
api.add_resource(DatasetRelatedAppListApi, '/datasets/<uuid:dataset_id>/related-apps')
api.add_resource(DatasetIndexingStatusApi, '/datasets/<uuid:dataset_id>/indexing-status')
api.add_resource(DatasetApiKeyApi, '/datasets/api-keys')
api.add_resource(DatasetApiDeleteApi, '/datasets/api-keys/<uuid:api_key_id>')
api.add_resource(DatasetApiBaseUrlApi, '/datasets/api-base-info')
api.add_resource(DatasetRetrievalSettingApi, '/datasets/retrieval-setting')
api.add_resource(DatasetRetrievalSettingMockApi, '/datasets/retrieval-setting/<string:vector_type>')
api.add_resource(DatasetPermissionUserListApi, '/datasets/<uuid:dataset_id>/permission-part-users')
