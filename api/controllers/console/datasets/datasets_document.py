import logging
from argparse import ArgumentTypeError
from datetime import datetime, timezone

from flask import request
from flask_login import current_user
from flask_restful import Resource, fields, marshal, marshal_with, reqparse
from sqlalchemy import asc, desc
from transformers.hf_argparser import string_to_bool
from werkzeug.exceptions import Forbidden, NotFound

import services
from controllers.console import api
from controllers.console.app.error import (
    ProviderModelCurrentlyNotSupportError,
    ProviderNotInitializeError,
    ProviderQuotaExceededError,
)
from controllers.console.datasets.error import (
    ArchivedDocumentImmutableError,
    DocumentAlreadyFinishedError,
    DocumentIndexingError,
    InvalidActionError,
    InvalidMetadataError,
)
from controllers.console.setup import setup_required
from controllers.console.wraps import account_initialization_required, cloud_edition_billing_resource_check
from core.errors.error import (
    LLMBadRequestError,
    ModelCurrentlyNotSupportError,
    ProviderTokenNotInitError,
    QuotaExceededError,
)
from core.indexing_runner import IndexingRunner
from core.model_manager import ModelManager
from core.model_runtime.entities.model_entities import ModelType
from core.model_runtime.errors.invoke import InvokeAuthorizationError
from core.rag.extractor.entity.extract_setting import ExtractSetting
from extensions.ext_database import db
from extensions.ext_redis import redis_client
from fields.document_fields import (
    dataset_and_document_fields,
    document_fields,
    document_status_fields,
    document_with_segments_fields,
)
from libs.login import login_required
from models.dataset import Dataset, DatasetProcessRule, Document, DocumentSegment
from models.model import UploadFile
from services.dataset_service import DatasetService, DocumentService
from tasks.add_document_to_index_task import add_document_to_index_task
from tasks.remove_document_from_index_task import remove_document_from_index_task


class DocumentResource(Resource):
    """
    文档资源类，提供文档的检索服务。
    """
    
    def get_document(self, dataset_id: str, document_id: str) -> Document:
        """
        获取指定数据集中的文档。
        
        参数:
        - dataset_id: 数据集的唯一标识符。
        - document_id: 文档的唯一标识符。
        
        返回值:
        - Document: 找到的文档对象。
        
        异常:
        - NotFound: 当指定的数据集或文档不存在时抛出。
        - Forbidden: 当用户没有权限访问数据集或文档时抛出。
        """
        # 根据dataset_id获取数据集
        dataset = DatasetService.get_dataset(dataset_id)
        if not dataset:
            raise NotFound('Dataset not found.')

        # 检查用户是否有权限访问该数据集
        try:
            DatasetService.check_dataset_permission(dataset, current_user)
        except services.errors.account.NoPermissionError as e:
            raise Forbidden(str(e))

        # 根据dataset_id和document_id获取文档
        document = DocumentService.get_document(dataset_id, document_id)

        if not document:
            raise NotFound('Document not found.')

        # 检查用户是否有权限访问该文档
        if document.tenant_id != current_user.current_tenant_id:
            raise Forbidden('No permission.')

        return document

    def get_batch_documents(self, dataset_id: str, batch: str) -> list[Document]:
        """
        批量获取文档。
        
        参数:
        - dataset_id: 数据集的唯一标识符。
        - batch: 文档批次标识。
        
        返回值:
        - list[Document]: 找到的文档对象列表。
        
        异常:
        - NotFound: 当指定的数据集或文档批次不存在时抛出。
        """
        # 根据dataset_id获取数据集
        dataset = DatasetService.get_dataset(dataset_id)
        if not dataset:
            raise NotFound('Dataset not found.')

        # 检查用户是否有权限访问该数据集
        try:
            DatasetService.check_dataset_permission(dataset, current_user)
        except services.errors.account.NoPermissionError as e:
            raise Forbidden(str(e))

        # 根据dataset_id和batch获取文档批次
        documents = DocumentService.get_batch_documents(dataset_id, batch)

        if not documents:
            raise NotFound('Documents not found.')

        return documents

class GetProcessRuleApi(Resource):
    """
    获取处理规则的API接口类。
    
    该类提供了一个GET方法，用于根据文档ID获取处理规则，包括默认规则和特定文档数据集的最新处理规则。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        """
        获取处理规则的GET方法。
        
        需要用户登录、账号初始化和设置完成后才能访问。
        
        参数:
        - 无
        
        返回值:
        - 一个包含模式(mode)和规则(rules)的字典。
        
        错误:
        - 如果文档ID不存在，返回404错误。
        - 如果数据集未找到，返回404错误。
        - 如果用户对数据集没有权限，返回403错误。
        """
        req_data = request.args  # 获取请求参数

        document_id = req_data.get('document_id')  # 尝试从请求参数中获取文档ID

        # 获取默认规则
        mode = DocumentService.DEFAULT_RULES['mode']
        rules = DocumentService.DEFAULT_RULES['rules']
        if document_id:
            # 根据文档ID获取最新的处理规则
            document = Document.query.get_or_404(document_id)  # 根据文档ID查询文档，如果不存在则返回404错误

            dataset = DatasetService.get_dataset(document.dataset_id)  # 根据文档获取对应的数据集

            if not dataset:
                raise NotFound('Dataset not found.')  # 如果数据集未找到，抛出404错误

            try:
                DatasetService.check_dataset_permission(dataset, current_user)  # 检查当前用户是否有该数据集的权限
            except services.errors.account.NoPermissionError as e:
                raise Forbidden(str(e))  # 如果无权限，抛出403错误

            # 查询数据集的最新处理规则
            dataset_process_rule = db.session.query(DatasetProcessRule). \
                filter(DatasetProcessRule.dataset_id == document.dataset_id). \
                order_by(DatasetProcessRule.created_at.desc()). \
                limit(1). \
                one_or_none()  # 查询并获取最新的处理规则
            if dataset_process_rule:
                # 如果找到处理规则，则使用该规则的模式和规则
                mode = dataset_process_rule.mode
                rules = dataset_process_rule.rules_dict

        return {
            'mode': mode,
            'rules': rules
        }  # 返回模式和规则的字典


class DatasetDocumentListApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def get(self, dataset_id):
        """
        根据数据集ID获取文档列表。

        参数:
        - dataset_id: 数据集的唯一标识符，整数或字符串。

        返回值:
        - 一个包含文档信息的字典，包括文档数据、是否有更多页、每页限制、总条数和当前页码。
        """

        # 将dataset_id转换为字符串类型，确保一致性
        dataset_id = str(dataset_id)
        # 从请求参数中获取页码和每页限制，默认值分别为1和20
        page = request.args.get('page', default=1, type=int)
        limit = request.args.get('limit', default=20, type=int)
        # 获取搜索关键字、排序方式和是否获取详细信息的参数
        search = request.args.get('keyword', default=None, type=str)
        sort = request.args.get('sort', default='-created_at', type=str)
        # "yes", "true", "t", "y", "1" convert to True, while others convert to False.
        try:
            fetch = string_to_bool(request.args.get('fetch', default='false'))
        except (ArgumentTypeError, ValueError, Exception) as e:
            fetch = False
        dataset = DatasetService.get_dataset(dataset_id)
        # 如果数据集不存在，则抛出未找到的异常
        if not dataset:
            raise NotFound('Dataset not found.')

        try:
            # 检查当前用户是否有访问该数据集的权限
            DatasetService.check_dataset_permission(dataset, current_user)
        except services.errors.account.NoPermissionError as e:
            # 如果无权限，则抛出禁止访问的异常
            raise Forbidden(str(e))

        # 构建初始的文档查询
        query = Document.query.filter_by(
            dataset_id=str(dataset_id), tenant_id=current_user.current_tenant_id)

        # 如果存在搜索关键字，则对文档名称进行模糊搜索
        if search:
            search = f'%{search}%'
            query = query.filter(Document.name.like(search))

        # 处理排序逻辑
        if sort.startswith('-'):
            sort_logic = desc
            sort = sort[1:]
        else:
            sort_logic = asc

        # 根据不同的排序字段进行查询调整
        if sort == 'hit_count':
            # 对于点击量排序，需要进行子查询以计算总点击量
            sub_query = db.select(DocumentSegment.document_id,
                                db.func.sum(DocumentSegment.hit_count).label("total_hit_count")) \
                .group_by(DocumentSegment.document_id) \
                .subquery()

            query = query.outerjoin(sub_query, sub_query.c.document_id == Document.id) \
                .order_by(sort_logic(db.func.coalesce(sub_query.c.total_hit_count, 0)))
        elif sort == 'created_at':
            # 对于创建时间排序，直接按照时间排序
            query = query.order_by(sort_logic(Document.created_at))
        else:
            # 默认按照创建时间降序排序
            query = query.order_by(desc(Document.created_at))

        # 进行分页查询，并获取当前页的文档列表
        paginated_documents = query.paginate(
            page=page, per_page=limit, max_per_page=100, error_out=False)
        documents = paginated_documents.items

        # 如果需要获取详细信息，则计算每个文档的完成段数和总段数
        if fetch:
            for document in documents:
                completed_segments = DocumentSegment.query.filter(DocumentSegment.completed_at.isnot(None),
                                                                DocumentSegment.document_id == str(document.id),
                                                                DocumentSegment.status != 're_segment').count()
                total_segments = DocumentSegment.query.filter(DocumentSegment.document_id == str(document.id),
                                                            DocumentSegment.status != 're_segment').count()
                document.completed_segments = completed_segments
                document.total_segments = total_segments
            # 使用指定的字段列表对文档列表进行序列化
            data = marshal(documents, document_with_segments_fields)
        else:
            # 如果不需要详细信息，则使用简化的字段列表进行序列化
            data = marshal(documents, document_fields)
        response = {
            'data': data,
            'has_more': len(documents) == limit,
            'limit': limit,
            'total': paginated_documents.total,
            'page': page
        }

        return response

    documents_and_batch_fields = {
        'documents': fields.List(fields.Nested(document_fields)),
        'batch': fields.String
    }

    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(documents_and_batch_fields)
    @cloud_edition_billing_resource_check('vector_space')
    def post(self, dataset_id):
        """
        根据提供的数据集ID，创建一个新的文档。
        
        参数:
        - dataset_id: 数据集的唯一标识符，将被转换为字符串格式。
        
        返回值:
        - 一个包含创建的文档信息和批处理信息的字典。
        
        抛出:
        - NotFound: 如果指定的数据集未找到。
        - Forbidden: 如果当前用户没有权限创建文档。
        - ValueError: 如果缺少必需的参数。
        - ProviderNotInitializeError: 如果数据提供者未初始化。
        - ProviderQuotaExceededError: 如果达到了数据提供者的配额限制。
        - ProviderModelCurrentlyNotSupportError: 如果当前不支持指定的模型。
        """

        dataset_id = str(dataset_id)

        dataset = DatasetService.get_dataset(dataset_id)

        if not dataset:
            raise NotFound('Dataset not found.')

        # 检查当前用户是否具有在ta表中为管理员或所有者的角色
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        try:
            DatasetService.check_dataset_permission(dataset, current_user)
        except services.errors.account.NoPermissionError as e:
            raise Forbidden(str(e))

        parser = reqparse.RequestParser()
        # 定义请求参数
        parser.add_argument('indexing_technique', type=str, choices=Dataset.INDEXING_TECHNIQUE_LIST, nullable=False,
                            location='json')
        parser.add_argument('data_source', type=dict, required=False, location='json')
        parser.add_argument('process_rule', type=dict, required=False, location='json')
        parser.add_argument('duplicate', type=bool, default=True, nullable=False, location='json')
        parser.add_argument('original_document_id', type=str, required=False, location='json')
        parser.add_argument('doc_form', type=str, default='text_model', required=False, nullable=False, location='json')
        parser.add_argument('doc_language', type=str, default='English', required=False, nullable=False,
                            location='json')
        parser.add_argument('retrieval_model', type=dict, required=False, nullable=False,
                            location='json')
        args = parser.parse_args()

        # 确保如果数据集没有指定索引技术，请求参数中必须包含索引技术
        if not dataset.indexing_technique and not args['indexing_technique']:
            raise ValueError('indexing_technique is required.')

        # 验证请求参数
        DocumentService.document_create_args_validate(args)

        try:
            # 保存文档并返回创建的文档信息和批处理信息
            documents, batch = DocumentService.save_document_with_dataset_id(dataset, args, current_user)
        except ProviderTokenNotInitError as ex:
            raise ProviderNotInitializeError(ex.description)
        except QuotaExceededError:
            raise ProviderQuotaExceededError()
        except ModelCurrentlyNotSupportError:
            raise ProviderModelCurrentlyNotSupportError()

        return {
            'documents': documents,
            'batch': batch
        }


class DatasetInitApi(Resource):
    """
    数据集初始化API接口类
    """

    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(dataset_and_document_fields)
    @cloud_edition_billing_resource_check('vector_space')
    def post(self):
        """
        创建一个新的数据集并上传文档。
        
        要求用户已登录、账号已初始化，且满足云版本的资源检查条件。用户必须是管理员或所有者。
        
        参数:
        - indexing_technique: 索引技术类型，必须是预定义列表中的值。
        - data_source: 数据源信息，为一个字典。
        - process_rule: 处理规则，为一个字典。
        - doc_form: 文档形式，默认为'text_model'。
        - doc_language: 文档语言，默认为'English'。
        - retrieval_model: 检索模型配置，为一个字典。
        
        返回:
        - 'dataset': 创建的数据集信息。
        - 'documents': 上传的文档信息。
        - 'batch': 批处理信息。
        
        抛出:
        - Forbidden: 如果当前用户不是管理员或所有者。
        - ProviderNotInitializeError: 如果提供者未初始化。
        - ProviderQuotaExceededError: 如果达到提供者的配额限制。
        - ProviderModelCurrentlyNotSupportError: 如果当前模型不被支持。
        """
        # 检查当前用户是否具有管理员或所有者角色
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('indexing_technique', type=str, choices=Dataset.INDEXING_TECHNIQUE_LIST, required=True,
                            nullable=False, location='json')
        parser.add_argument('data_source', type=dict, required=True, nullable=True, location='json')
        parser.add_argument('process_rule', type=dict, required=True, nullable=True, location='json')
        parser.add_argument('doc_form', type=str, default='text_model', required=False, nullable=False, location='json')
        parser.add_argument('doc_language', type=str, default='English', required=False, nullable=False,
                            location='json')
        parser.add_argument('retrieval_model', type=dict, required=False, nullable=False,
                            location='json')
        args = parser.parse_args()

        # 针对高质索引技术，检查模型是否已配置
        if args['indexing_technique'] == 'high_quality':
            try:
                model_manager = ModelManager()
                model_manager.get_default_model_instance(
                    tenant_id=current_user.current_tenant_id,
                    model_type=ModelType.TEXT_EMBEDDING
                )
            except InvokeAuthorizationError:
                raise ProviderNotInitializeError(
                    "No Embedding Model available. Please configure a valid provider "
                    "in the Settings -> Model Provider.")
            except ProviderTokenNotInitError as ex:
                raise ProviderNotInitializeError(ex.description)

        # 验证解析后的参数
        DocumentService.document_create_args_validate(args)

        try:
            # 保存文档，不基于数据集ID
            dataset, documents, batch = DocumentService.save_document_without_dataset_id(
                tenant_id=current_user.current_tenant_id,
                document_data=args,
                account=current_user
            )
        except ProviderTokenNotInitError as ex:
            raise ProviderNotInitializeError(ex.description)
        except QuotaExceededError:
            raise ProviderQuotaExceededError()
        except ModelCurrentlyNotSupportError:
            raise ProviderModelCurrentlyNotSupportError()

        # 构建并返回响应
        response = {
            'dataset': dataset,
            'documents': documents,
            'batch': batch
        }

        return response


class DocumentIndexingEstimateApi(DocumentResource):
    """
    文档索引估计API，提供文档索引费用估计功能。
    
    Attributes:
        Inherits attributes from DocumentResource
    """

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, dataset_id, document_id):
        """
        获取文档索引估计信息。
        
        Args:
            dataset_id (int): 数据集ID，将被转换为字符串格式。
            document_id (int): 文档ID，将被转换为字符串格式。
        
        Returns:
            dict: 包含索引估计信息的字典，如令牌数量、总价格、货币单位、总段数和预览信息等。
        
        Raises:
            DocumentAlreadyFinishedError: 如果文档的索引状态已经是"completed"或"error"。
            NotFound: 如果找不到对应的文件。
            ProviderNotInitializeError: 如果没有配置有效的嵌入模型提供者。
        """
        dataset_id = str(dataset_id)
        document_id = str(document_id)
        document = self.get_document(dataset_id, document_id)

        # 检查文档索引状态，若已完成或出错，则抛出异常
        if document.indexing_status in ['completed', 'error']:
            raise DocumentAlreadyFinishedError()

        data_process_rule = document.dataset_process_rule
        data_process_rule_dict = data_process_rule.to_dict()

        # 初始化响应信息
        response = {
            "tokens": 0,
            "total_price": 0,
            "currency": "USD",
            "total_segments": 0,
            "preview": []
        }

        # 如果文档数据源类型为上传文件
        if document.data_source_type == 'upload_file':
            data_source_info = document.data_source_info_dict
            # 检查并获取上传文件ID
            if data_source_info and 'upload_file_id' in data_source_info:
                file_id = data_source_info['upload_file_id']

                # 根据文件ID查询文件信息
                file = db.session.query(UploadFile).filter(
                    UploadFile.tenant_id == document.tenant_id,
                    UploadFile.id == file_id
                ).first()

                # 如果找不到文件，抛出异常
                if not file:
                    raise NotFound('File not found.')

                # 配置数据提取设置和索引运行器
                extract_setting = ExtractSetting(
                    datasource_type="upload_file",
                    upload_file=file,
                    document_model=document.doc_form
                )

                indexing_runner = IndexingRunner()

                try:
                    # 执行索引估计，并更新响应信息
                    response = indexing_runner.indexing_estimate(current_user.current_tenant_id, [extract_setting],
                                                                 data_process_rule_dict, document.doc_form,
                                                                 'English', dataset_id)
                except LLMBadRequestError:
                    # 如果没有可用的嵌入模型，抛出异常
                    raise ProviderNotInitializeError(
                        "No Embedding Model available. Please configure a valid provider "
                        "in the Settings -> Model Provider.")
                except ProviderTokenNotInitError as ex:
                    # 如果提供者令牌未初始化，抛出异常
                    raise ProviderNotInitializeError(ex.description)

        return response

class DocumentBatchIndexingEstimateApi(DocumentResource):
    """
    处理文档批量索引估计的API请求。

    Attributes:
        - 继承自DocumentResource，包含与文档相关的资源操作。
    """

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, dataset_id, batch):
        """
        获取给定数据集和批次的索引估计信息。

        Args:
            - dataset_id (int): 数据集的ID，将被转换为字符串。
            - batch (int): 批次的ID，将被转换为字符串。

        Returns:
            - dict: 包含索引估计的响应信息，如token数量、总价格、货币单位、总段数和预览信息等。

        Raises:
            - NotFound: 如果指定的数据集不存在。
            - DocumentAlreadyFinishedError: 如果文档的索引状态已经是完成或错误。
            - ProviderNotInitializeError: 如果没有配置有效的嵌入模型提供者。
            - ValueError: 如果数据源类型不支持。
        """
        # 校验请求所需的设置和用户登录状态
        dataset_id = str(dataset_id)
        batch = str(batch)
        documents = self.get_batch_documents(dataset_id, batch)
        # 初始化响应信息
        response = {
            "tokens": 0,
            "total_price": 0,
            "currency": "USD",
            "total_segments": 0,
            "preview": []
        }
        if not documents:
            return response
        # 获取第一个文档的数据处理规则，并转换为字典格式
        data_process_rule = documents[0].dataset_process_rule
        data_process_rule_dict = data_process_rule.to_dict()
        info_list = []
        extract_settings = []
        for document in documents:
            # 如果文档的索引状态已经是完成或错误，抛出异常
            if document.indexing_status in ['completed', 'error']:
                raise DocumentAlreadyFinishedError()
            # 格式化文档文件信息
            data_source_info = document.data_source_info_dict
            if data_source_info and 'upload_file_id' in data_source_info:
                file_id = data_source_info['upload_file_id']
                info_list.append(file_id)
            # 格式化文档Notion信息
            elif data_source_info and 'notion_workspace_id' in data_source_info and 'notion_page_id' in data_source_info:
                pages = []
                page = {
                    'page_id': data_source_info['notion_page_id'],
                    'type': data_source_info['type']
                }
                pages.append(page)
                notion_info = {
                    'workspace_id': data_source_info['notion_workspace_id'],
                    'pages': pages
                }
                info_list.append(notion_info)
            
            # 根据文档的数据源类型，准备提取设置
            if document.data_source_type == 'upload_file':
                file_id = data_source_info['upload_file_id']
                # 查询对应的上传文件信息
                file_detail = db.session.query(UploadFile).filter(
                    UploadFile.tenant_id == current_user.current_tenant_id,
                    UploadFile.id == file_id
                ).first()
                if file_detail is None:
                    raise NotFound("File not found.")
                # 为上传文件类型的文档创建提取设置
                extract_setting = ExtractSetting(
                    datasource_type="upload_file",
                    upload_file=file_detail,
                    document_model=document.doc_form
                )
                extract_settings.append(extract_setting)

            elif document.data_source_type == 'notion_import':
                # 为Notion导入类型的文档创建提取设置
                extract_setting = ExtractSetting(
                    datasource_type="notion_import",
                    notion_info={
                        "notion_workspace_id": data_source_info['notion_workspace_id'],
                        "notion_obj_id": data_source_info['notion_page_id'],
                        "notion_page_type": data_source_info['type'],
                        "tenant_id": current_user.current_tenant_id
                    },
                    document_model=document.doc_form
                )
                extract_settings.append(extract_setting)

            else:
                raise ValueError('Data source type not support')
            
            # 如果数据源类型不受支持，则抛出异常
            indexing_runner = IndexingRunner()
            try:
                response = indexing_runner.indexing_estimate(current_user.current_tenant_id, extract_settings,
                                                             data_process_rule_dict, document.doc_form,
                                                             'English', dataset_id)
            except LLMBadRequestError:
                # 如果请求被LLM拒绝，则抛出提供者未初始化异常
                raise ProviderNotInitializeError(
                    "No Embedding Model available. Please configure a valid provider "
                    "in the Settings -> Model Provider.")
            except ProviderTokenNotInitError as ex:
                # 如果提供者令牌未初始化，则抛出提供者未初始化异常，并附带错误描述
                raise ProviderNotInitializeError(ex.description)
        return response


class DocumentBatchIndexingStatusApi(DocumentResource):
    """
    文档批量索引状态API类，用于获取特定数据集和批次的文档索引状态。

    Attributes:
        requires setup, login, and account initialization decorators for authentication and authorization.
    """

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, dataset_id, batch):
        """
        获取指定数据集和批次的文档索引状态。

        Args:
            dataset_id (int): 数据集的ID，将被转换为字符串格式。
            batch (int): 批次的ID，将被转换为字符串格式。

        Returns:
            dict: 包含文档状态信息的字典列表。每个文档的状态包括完成的片段数、总片段数和索引状态。
        """
        dataset_id = str(dataset_id)  # 将数据集ID转换为字符串
        batch = str(batch)  # 将批次ID转换为字符串
        documents = self.get_batch_documents(dataset_id, batch)  # 获取指定批次的文档列表
        
        documents_status = []  # 初始化存储文档状态的列表
        for document in documents:  # 遍历文档
            # 计算已完成和总片段数
            completed_segments = DocumentSegment.query.filter(DocumentSegment.completed_at.isnot(None),
                                                              DocumentSegment.document_id == str(document.id),
                                                              DocumentSegment.status != 're_segment').count()
            total_segments = DocumentSegment.query.filter(DocumentSegment.document_id == str(document.id),
                                                          DocumentSegment.status != 're_segment').count()
            document.completed_segments = completed_segments  # 设置文档的已完成片段数
            document.total_segments = total_segments  # 设置文档的总片段数
            if document.is_paused:  # 如果文档暂停，则设置索引状态为'paused'
                document.indexing_status = 'paused'
            documents_status.append(marshal(document, document_status_fields))  # 将文档状态添加到列表
        
        data = {  # 准备返回的数据
            'data': documents_status
        }
        return data  # 返回文档状态数据




class DocumentIndexingStatusApi(DocumentResource):
    """
    文档索引状态API，用于获取特定文档的索引状态信息。
    
    Attributes:
        Inherits attributes from DocumentResource
    """

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, dataset_id, document_id):
        """
        获取指定数据集和文档的索引状态。
        
        Args:
            dataset_id (int): 数据集的ID。
            document_id (int): 文档的ID。
        
        Returns:
            dict: 包含文档索引状态信息的字典，如完成的段落数、总段落数和索引状态。
        """
        # 将传入的ID转换为字符串格式
        dataset_id = str(dataset_id)
        document_id = str(document_id)
        # 获取指定文档对象
        document = self.get_document(dataset_id, document_id)

        # 计算已完成的段落数量
        completed_segments = DocumentSegment.query \
            .filter(DocumentSegment.completed_at.isnot(None),
                    DocumentSegment.document_id == str(document_id),
                    DocumentSegment.status != 're_segment') \
            .count()
        # 计算总共的段落数量
        total_segments = DocumentSegment.query \
            .filter(DocumentSegment.document_id == str(document_id),
                    DocumentSegment.status != 're_segment') \
            .count()

        # 更新文档对象的完成段落数和总段落数
        document.completed_segments = completed_segments
        document.total_segments = total_segments
        # 如果文档暂停，则更新索引状态为'paused'
        if document.is_paused:
            document.indexing_status = 'paused'
        # 返回处理后的文档状态信息
        return marshal(document, document_status_fields)

class DocumentDetailApi(DocumentResource):
    # 定义文档元数据的选择选项
    METADATA_CHOICES = {'all', 'only', 'without'}

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, dataset_id, document_id):
        """
        获取指定数据集和文档的详细信息。

        参数:
        - dataset_id: 数据集的唯一标识符。
        - document_id: 文档的唯一标识符。

        返回值:
        - 一个包含文档信息的字典以及HTTP状态码200。
        
        可通过查询参数metadata来选择返回的文档信息详细程度。
        'all'返回所有信息（默认）；
        'only'返回文档的元数据；
        'without'返回除元数据外的所有信息。
        """

        # 将传入的ID转换为字符串类型
        dataset_id = str(dataset_id)
        document_id = str(document_id)
        # 获取文档对象
        document = self.get_document(dataset_id, document_id)

        # 获取metadata选项，若无效则抛出异常
        metadata = request.args.get('metadata', 'all')
        if metadata not in self.METADATA_CHOICES:
            raise InvalidMetadataError(f'Invalid metadata value: {metadata}')

        # 根据metadata选项构造返回的文档信息
        if metadata == 'only':
            # 仅返回文档的元数据
            response = {
                'id': document.id,
                'doc_type': document.doc_type,
                'doc_metadata': document.doc_metadata
            }
        elif metadata == 'without':
            # 返回除元数据外的所有信息
            process_rules = DatasetService.get_process_rules(dataset_id)  # 获取数据集处理规则
            data_source_info = document.data_source_detail_dict  # 获取数据源信息
            response = {
                # 包含文档的详细信息
                'id': document.id,
                'position': document.position,
                'data_source_type': document.data_source_type,
                'data_source_info': data_source_info,
                'dataset_process_rule_id': document.dataset_process_rule_id,
                'dataset_process_rule': process_rules,
                'name': document.name,
                'created_from': document.created_from,
                'created_by': document.created_by,
                'created_at': document.created_at.timestamp(),
                'tokens': document.tokens,
                'indexing_status': document.indexing_status,
                'completed_at': int(document.completed_at.timestamp()) if document.completed_at else None,
                'updated_at': int(document.updated_at.timestamp()) if document.updated_at else None,
                'indexing_latency': document.indexing_latency,
                'error': document.error,
                'enabled': document.enabled,
                'disabled_at': int(document.disabled_at.timestamp()) if document.disabled_at else None,
                'disabled_by': document.disabled_by,
                'archived': document.archived,
                'segment_count': document.segment_count,
                'average_segment_length': document.average_segment_length,
                'hit_count': document.hit_count,
                'display_status': document.display_status,
                'doc_form': document.doc_form
            }
        else:
            # 返回所有信息
            process_rules = DatasetService.get_process_rules(dataset_id)  # 获取数据集处理规则
            data_source_info = document.data_source_detail_dict  # 获取数据源信息
            response = {
                # 包含文档的所有信息
                'id': document.id,
                'position': document.position,
                'data_source_type': document.data_source_type,
                'data_source_info': data_source_info,
                'dataset_process_rule_id': document.dataset_process_rule_id,
                'dataset_process_rule': process_rules,
                'name': document.name,
                'created_from': document.created_from,
                'created_by': document.created_by,
                'created_at': document.created_at.timestamp(),
                'tokens': document.tokens,
                'indexing_status': document.indexing_status,
                'completed_at': int(document.completed_at.timestamp()) if document.completed_at else None,
                'updated_at': int(document.updated_at.timestamp()) if document.updated_at else None,
                'indexing_latency': document.indexing_latency,
                'error': document.error,
                'enabled': document.enabled,
                'disabled_at': int(document.disabled_at.timestamp()) if document.disabled_at else None,
                'disabled_by': document.disabled_by,
                'archived': document.archived,
                'doc_type': document.doc_type,
                'doc_metadata': document.doc_metadata,
                'segment_count': document.segment_count,
                'average_segment_length': document.average_segment_length,
                'hit_count': document.hit_count,
                'display_status': document.display_status,
                'doc_form': document.doc_form
            }

        return response, 200


class DocumentProcessingApi(DocumentResource):
    @setup_required
    @login_required
    @account_initialization_required
    def patch(self, dataset_id, document_id, action):
        """
        对指定文档进行操作（暂停或恢复）。

        参数:
        - dataset_id: 数据集的ID，将被转换为字符串格式。
        - document_id: 文档的ID，将被转换为字符串格式。
        - action: 操作类型，支持"pause"（暂停）或"resume"（恢复）。

        返回值:
        - 一个包含操作结果的消息字典，以及HTTP状态码200。

        异常:
        - 如果用户没有权限，则抛出Forbidden异常。
        - 如果文档不在可操作状态（对于"pause"，不在索引中；对于"resume"，不在暂停或错误状态），则抛出InvalidActionError异常。
        - 如果action值不是"pause"或"resume"，则抛出InvalidActionError异常。
        """

        dataset_id = str(dataset_id)
        document_id = str(document_id)
        document = self.get_document(dataset_id, document_id)

        # 检查当前用户是否有权限（必须是管理员或所有者）
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        # 根据传入的action执行相应的操作
        if action == "pause":
            # 暂停操作仅在文档处于索引状态时有效
            if document.indexing_status != "indexing":
                raise InvalidActionError('Document not in indexing state.')

            # 更新文档状态为暂停
            document.paused_by = current_user.id
            document.paused_at = datetime.now(timezone.utc).replace(tzinfo=None)
            document.is_paused = True
            db.session.commit()

        elif action == "resume":
            # 恢复操作仅在文档处于暂停或错误状态时有效
            if document.indexing_status not in ["paused", "error"]:
                raise InvalidActionError('Document not in paused or error state.')

            # 更新文档状态为恢复
            document.paused_by = None
            document.paused_at = None
            document.is_paused = False
            db.session.commit()
        else:
            # 不支持的操作类型
            raise InvalidActionError()

        return {'result': 'success'}, 200


class DocumentDeleteApi(DocumentResource):
    """
    文档删除API，继承自DocumentResource。
    要求先设置好环境，用户需登录且账号初始化完成。
    
    方法:
    delete: 根据给定的文档ID和数据集ID删除文档。
    
    参数:
    - dataset_id: 数据集的唯一标识符。
    - document_id: 文档的唯一标识符。
    
    返回值:
    - 当文档成功删除时，返回一个包含结果信息的字典和HTTP状态码204。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    def delete(self, dataset_id, document_id):
        # 将传入的ID转换为字符串类型
        dataset_id = str(dataset_id)
        document_id = str(document_id)
        
        # 尝试获取指定ID的数据集
        dataset = DatasetService.get_dataset(dataset_id)
        if dataset is None:
            raise NotFound("Dataset not found.")
        
        # 检查用户的数据集模型设置
        DatasetService.check_dataset_model_setting(dataset)

        # 获取文档
        document = self.get_document(dataset_id, document_id)

        try:
            # 尝试删除文档，若文档正在被索引则会抛出异常
            DocumentService.delete_document(document)
        except services.errors.document.DocumentIndexingError:
            raise DocumentIndexingError('Cannot delete document during indexing.')

        # 删除成功，返回成功信息和HTTP状态码204
        return {'result': 'success'}, 204


class DocumentMetadataApi(DocumentResource):
    """
    处理文档元数据API的请求。
    
    方法:
    - put: 更新指定文档的元数据。
    
    参数:
    - dataset_id: 数据集的唯一标识符。
    - document_id: 文档的唯一标识符。
    
    返回值:
    - 成功更新时返回包含成功消息的JSON响应。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    def put(self, dataset_id, document_id):
        # 将传入的ID转换为字符串格式
        dataset_id = str(dataset_id)
        document_id = str(document_id)
        # 获取指定的文档对象
        document = self.get_document(dataset_id, document_id)

        # 从请求中获取数据
        req_data = request.get_json()

        # 提取文档类型和元数据信息
        doc_type = req_data.get('doc_type')
        doc_metadata = req_data.get('doc_metadata')

        # 检查当前用户是否有权限进行操作
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        # 确保文档类型和元数据都已提供
        if doc_type is None or doc_metadata is None:
            raise ValueError('Both doc_type and doc_metadata must be provided.')

        # 检查文档类型是否有效
        if doc_type not in DocumentService.DOCUMENT_METADATA_SCHEMA:
            raise ValueError('Invalid doc_type.')

        # 确保元数据是字典类型
        if not isinstance(doc_metadata, dict):
            raise ValueError('doc_metadata must be a dictionary.')

        # 获取文档类型的元数据架构
        metadata_schema = DocumentService.DOCUMENT_METADATA_SCHEMA[doc_type]

        # 更新文档的元数据
        document.doc_metadata = {}
        if doc_type == 'others':
            document.doc_metadata = doc_metadata
        else:
            for key, value_type in metadata_schema.items():
                value = doc_metadata.get(key)
                # 仅保留符合类型要求的元数据字段
                if value is not None and isinstance(value, value_type):
                    document.doc_metadata[key] = value

        # 更新文档类型和更新时间
        document.doc_type = doc_type
        document.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.session.commit()

        # 返回成功消息
        return {'result': 'success', 'message': 'Document metadata updated.'}, 200


class DocumentStatusApi(DocumentResource):
    """
    文档状态API接口类，用于处理文档的启用、禁用、归档和取消归档操作。

    方法:
    - patch: 根据提供的动作参数，更新文档的状态。
    """

    @setup_required
    @login_required
    @account_initialization_required
    @cloud_edition_billing_resource_check('vector_space')
    def patch(self, dataset_id, document_id, action):
        """
        根据提供的动作参数，更新文档的状态。

        参数:
        - dataset_id: 数据集ID，用于标识文档所属的数据集。
        - document_id: 文档ID，用于标识需要操作的文档。
        - action: 动作字符串，可选值为"enable"、"disable"、"archive"和"un_archive"，分别表示启用、禁用、归档和取消归档文档。

        返回值:
        - 一个包含结果信息的字典和HTTP状态码。成功时返回{'result': 'success'}和状态码200，错误时抛出异常。

        异常:
        - NotFound: 当指定的数据集不存在时抛出。
        - Forbidden: 当当前用户没有权限操作文档时抛出。
        - InvalidActionError: 当指定的操作无效或文档处于不允许执行该操作的状态时抛出。
        """

        # 将传入的ID转换为字符串类型
        dataset_id = str(dataset_id)
        document_id = str(document_id)

        # 获取指定ID的数据集
        dataset = DatasetService.get_dataset(dataset_id)
        if dataset is None:
            raise NotFound("Dataset not found.")

        # 检查用户的数据集模型设置
        DatasetService.check_dataset_model_setting(dataset)

        # 获取文档对象
        document = self.get_document(dataset_id, document_id)

        # 检查当前用户是否有权限操作文档
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        # 检查文档是否正在被索引
        indexing_cache_key = 'document_{}_indexing'.format(document.id)
        cache_result = redis_client.get(indexing_cache_key)
        if cache_result is not None:
            raise InvalidActionError("Document is being indexed, please try again later")

        # 根据动作参数更新文档状态
        if action == "enable":
            if document.enabled:
                raise InvalidActionError('Document already enabled.')

            # 启用文档
            document.enabled = True
            document.disabled_at = None
            document.disabled_by = None
            document.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.session.commit()

            # 设置缓存以防止重复索引同一文档
            redis_client.setex(indexing_cache_key, 600, 1)

            # 添加文档到索引队列
            add_document_to_index_task.delay(document_id)

            return {'result': 'success'}, 200

        elif action == "disable":
            # 禁用文档
            if not document.completed_at or document.indexing_status != 'completed':
                raise InvalidActionError('Document is not completed.')
            if not document.enabled:
                raise InvalidActionError('Document already disabled.')

            document.enabled = False
            document.disabled_at = datetime.now(timezone.utc).replace(tzinfo=None)
            document.disabled_by = current_user.id
            document.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.session.commit()

            # 设置缓存以防止重复索引同一文档
            redis_client.setex(indexing_cache_key, 600, 1)

            # 从索引中移除文档
            remove_document_from_index_task.delay(document_id)

            return {'result': 'success'}, 200

        elif action == "archive":
            # 归档文档
            if document.archived:
                raise InvalidActionError('Document already archived.')

            document.archived = True
            document.archived_at = datetime.now(timezone.utc).replace(tzinfo=None)
            document.archived_by = current_user.id
            document.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.session.commit()

            if document.enabled:
                # 设置缓存以防止重复索引同一文档
                redis_client.setex(indexing_cache_key, 600, 1)

                # 从索引中移除文档
                remove_document_from_index_task.delay(document_id)

            return {'result': 'success'}, 200
        elif action == "un_archive":
            # 取消归档文档
            if not document.archived:
                raise InvalidActionError('Document is not archived.')

            document.archived = False
            document.archived_at = None
            document.archived_by = None
            document.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.session.commit()

            # 设置缓存以防止重复索引同一文档
            redis_client.setex(indexing_cache_key, 600, 1)

            # 添加文档到索引队列
            add_document_to_index_task.delay(document_id)

            return {'result': 'success'}, 200
        else:
            raise InvalidActionError()


class DocumentPauseApi(DocumentResource):
    # 此类继承自DocumentResource，用于处理文档暂停的API请求

    @setup_required
    @login_required
    @account_initialization_required
    def patch(self, dataset_id, document_id):
        """
        暂停文档。

        参数:
        - dataset_id: 数据集的ID，类型为int或str。
        - document_id: 文档的ID，类型为int或str。

        返回值:
        - 返回一个包含结果信息的字典和HTTP状态码204。
        
        异常:
        - 如果数据集或文档不存在，抛出NotFound异常。
        - 如果文档已归档，抛出ArchivedDocumentImmutableError异常。
        - 如果文档暂停失败（已完成的文档无法暂停），抛出DocumentIndexingError异常。
        """

        # 将传入的ID转换为字符串类型
        dataset_id = str(dataset_id)
        document_id = str(document_id)

        # 根据ID获取数据集
        dataset = DatasetService.get_dataset(dataset_id)
        if not dataset:
            raise NotFound('Dataset not found.')

        # 在指定的数据集中获取文档
        document = DocumentService.get_document(dataset.id, document_id)

        # 如果文档不存在，抛出404错误
        if document is None:
            raise NotFound("Document Not Exists.")

        # 如果文档已归档，抛出403错误
        if DocumentService.check_archived(document):
            raise ArchivedDocumentImmutableError()

        try:
            # 尝试暂停文档
            DocumentService.pause_document(document)
        except services.errors.document.DocumentIndexingError:
            # 如果文档已完成索引，无法暂停，抛出错误
            raise DocumentIndexingError('Cannot pause completed document.')

        # 操作成功，返回成功信息和状态码
        return {'result': 'success'}, 204


class DocumentRecoverApi(DocumentResource):
    @setup_required
    @login_required
    @account_initialization_required
    def patch(self, dataset_id, document_id):
        """
        恢复文档。

        参数:
        - dataset_id: 数据集的ID，将被转换为字符串格式。
        - document_id: 文档的ID，将被转换为字符串格式。

        返回值:
        - 成功恢复文档时返回一个包含结果信息的字典和HTTP状态码204。

        异常:
        - NotFound: 如果数据集或文档不存在时抛出。
        - ArchivedDocumentImmutableError: 如果文档被归档时抛出。
        - DocumentIndexingError: 如果文档不在暂停状态时抛出。
        """

        dataset_id = str(dataset_id)
        document_id = str(document_id)
        dataset = DatasetService.get_dataset(dataset_id)
        if not dataset:
            raise NotFound('Dataset not found.')
        document = DocumentService.get_document(dataset.id, document_id)

        # 检查文档是否存在，不存在则抛出404异常
        if document is None:
            raise NotFound("Document Not Exists.")

        # 检查文档是否被归档，若已归档则抛出403异常
        if DocumentService.check_archived(document):
            raise ArchivedDocumentImmutableError()
        try:
            # 尝试恢复文档
            DocumentService.recover_document(document)
        except services.errors.document.DocumentIndexingError:
            # 如果文档不在暂停状态，抛出异常
            raise DocumentIndexingError('Document is not in paused status.')

        return {'result': 'success'}, 204


class DocumentRetryApi(DocumentResource):
    @setup_required
    @login_required
    @account_initialization_required
    def post(self, dataset_id):
        """retry document."""

        parser = reqparse.RequestParser()
        parser.add_argument('document_ids', type=list, required=True, nullable=False,
                            location='json')
        args = parser.parse_args()
        dataset_id = str(dataset_id)
        dataset = DatasetService.get_dataset(dataset_id)
        retry_documents = []
        if not dataset:
            raise NotFound('Dataset not found.')
        for document_id in args['document_ids']:
            try:
                document_id = str(document_id)

                document = DocumentService.get_document(dataset.id, document_id)

                # 404 if document not found
                if document is None:
                    raise NotFound("Document Not Exists.")

                # 403 if document is archived
                if DocumentService.check_archived(document):
                    raise ArchivedDocumentImmutableError()

                # 400 if document is completed
                if document.indexing_status == 'completed':
                    raise DocumentAlreadyFinishedError()
                retry_documents.append(document)
            except Exception as e:
                logging.error(f"Document {document_id} retry failed: {str(e)}")
                continue
        # retry document
        DocumentService.retry_document(dataset_id, retry_documents)

        return {'result': 'success'}, 204


class DocumentRenameApi(DocumentResource):
    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(document_fields)
    def post(self, dataset_id, document_id):
        # The role of the current user in the ta table must be admin or owner
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        parser = reqparse.RequestParser()
        parser.add_argument('name', type=str, required=True, nullable=False, location='json')
        args = parser.parse_args()

        try:
            document = DocumentService.rename_document(dataset_id, document_id, args['name'])
        except services.errors.document.DocumentIndexingError:
            raise DocumentIndexingError('Cannot delete document during indexing.')

        return document


api.add_resource(GetProcessRuleApi, '/datasets/process-rule')
api.add_resource(DatasetDocumentListApi,
                 '/datasets/<uuid:dataset_id>/documents')
api.add_resource(DatasetInitApi,
                 '/datasets/init')
api.add_resource(DocumentIndexingEstimateApi,
                 '/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/indexing-estimate')
api.add_resource(DocumentBatchIndexingEstimateApi,
                 '/datasets/<uuid:dataset_id>/batch/<string:batch>/indexing-estimate')
api.add_resource(DocumentBatchIndexingStatusApi,
                 '/datasets/<uuid:dataset_id>/batch/<string:batch>/indexing-status')
api.add_resource(DocumentIndexingStatusApi,
                 '/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/indexing-status')
api.add_resource(DocumentDetailApi,
                 '/datasets/<uuid:dataset_id>/documents/<uuid:document_id>')
api.add_resource(DocumentProcessingApi,
                 '/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/processing/<string:action>')
api.add_resource(DocumentDeleteApi,
                 '/datasets/<uuid:dataset_id>/documents/<uuid:document_id>')
api.add_resource(DocumentMetadataApi,
                 '/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/metadata')
api.add_resource(DocumentStatusApi,
                 '/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/status/<string:action>')
api.add_resource(DocumentPauseApi, '/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/processing/pause')
api.add_resource(DocumentRecoverApi, '/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/processing/resume')
api.add_resource(DocumentRetryApi, '/datasets/<uuid:dataset_id>/retry')
api.add_resource(DocumentRenameApi,
                 '/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/rename')
