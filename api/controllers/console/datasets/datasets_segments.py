import uuid
from datetime import datetime, timezone

import pandas as pd
from flask import request
from flask_login import current_user
from flask_restful import Resource, marshal, reqparse
from werkzeug.exceptions import Forbidden, NotFound

import services
from controllers.console import api
from controllers.console.app.error import ProviderNotInitializeError
from controllers.console.datasets.error import InvalidActionError, NoFileUploadedError, TooManyFilesError
from controllers.console.setup import setup_required
from controllers.console.wraps import (
    account_initialization_required,
    cloud_edition_billing_knowledge_limit_check,
    cloud_edition_billing_resource_check,
)
from core.errors.error import LLMBadRequestError, ProviderTokenNotInitError
from core.model_manager import ModelManager
from core.model_runtime.entities.model_entities import ModelType
from extensions.ext_database import db
from extensions.ext_redis import redis_client
from fields.segment_fields import segment_fields
from libs.login import login_required
from models.dataset import DocumentSegment
from services.dataset_service import DatasetService, DocumentService, SegmentService
from tasks.batch_create_segment_to_index_task import batch_create_segment_to_index_task
from tasks.disable_segment_from_index_task import disable_segment_from_index_task
from tasks.enable_segment_to_index_task import enable_segment_to_index_task


class DatasetDocumentSegmentListApi(Resource):
    """
    数据集文档段落列表API接口类，用于获取指定文档中的段落列表。
    
    参数:
    - dataset_id: 数据集的唯一标识符。
    - document_id: 文档的唯一标识符。
    
    返回值:
    - 一个包含段落数据、是否有更多数据、限制数、总数据数的字典，以及HTTP状态码200。
    - 如果指定的数据集或文档不存在，抛出相应的异常。
    """

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, dataset_id, document_id):
        # 将传入的ID转换为字符串格式
        dataset_id = str(dataset_id)
        document_id = str(document_id)

        # 根据ID获取数据集对象
        dataset = DatasetService.get_dataset(dataset_id)
        if not dataset:
            raise NotFound('Dataset not found.')

        # 检查用户是否有权限访问该数据集
        try:
            DatasetService.check_dataset_permission(dataset, current_user)
        except services.errors.account.NoPermissionError as e:
            raise Forbidden(str(e))

        # 根据ID获取文档对象
        document = DocumentService.get_document(dataset_id, document_id)
        if not document:
            raise NotFound('Document not found.')

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('last_id', type=str, default=None, location='args')
        parser.add_argument('limit', type=int, default=20, location='args')
        parser.add_argument('status', type=str,
                            action='append', default=[], location='args')
        parser.add_argument('hit_count_gte', type=int,
                            default=None, location='args')
        parser.add_argument('enabled', type=str, default='all', location='args')
        parser.add_argument('keyword', type=str, default=None, location='args')
        args = parser.parse_args()

        # 获取解析后的参数值
        last_id = args['last_id']
        limit = min(args['limit'], 100)
        status_list = args['status']
        hit_count_gte = args['hit_count_gte']
        keyword = args['keyword']

        # 构建初始查询
        query = DocumentSegment.query.filter(
            DocumentSegment.document_id == str(document_id),
            DocumentSegment.tenant_id == current_user.current_tenant_id
        )

        # 如果提供了last_id，筛选出位置大于该段落的位置的段落
        if last_id is not None:
            last_segment = db.session.get(DocumentSegment, str(last_id))
            if last_segment:
                query = query.filter(
                    DocumentSegment.position > last_segment.position)
            else:
                return {'data': [], 'has_more': False, 'limit': limit}, 200

        # 根据状态筛选
        if status_list:
            query = query.filter(DocumentSegment.status.in_(status_list))

        # 根据命中数大于等于筛选
        if hit_count_gte is not None:
            query = query.filter(DocumentSegment.hit_count >= hit_count_gte)

        # 根据关键字搜索
        if keyword:
            query = query.where(DocumentSegment.content.ilike(f'%{keyword}%'))

        # 根据启用状态筛选
        if args['enabled'].lower() != 'all':
            if args['enabled'].lower() == 'true':
                query = query.filter(DocumentSegment.enabled == True)
            elif args['enabled'].lower() == 'false':
                query = query.filter(DocumentSegment.enabled == False)

        # 计算总记录数并获取数据
        total = query.count()
        segments = query.order_by(DocumentSegment.position).limit(limit + 1).all()

        # 检查是否有更多数据
        has_more = False
        if len(segments) > limit:
            has_more = True
            segments = segments[:-1]

        # 返回查询结果
        return {
            'data': marshal(segments, segment_fields),
            'doc_form': document.doc_form,
            'has_more': has_more,
            'limit': limit,
            'total': total
        }, 200


class DatasetDocumentSegmentApi(Resource):
    """
    处理数据集文档段的API请求。

    方法:
    - patch: 根据提供的动作参数，启用或禁用指定的数据集文档段。

    参数:
    - dataset_id: 数据集的唯一标识符。
    - segment_id: 文档段的唯一标识符。
    - action: 操作类型，可为"enable"或"disable"。

    返回值:
    - 对于成功操作，返回一个包含结果信息的JSON对象和HTTP状态码200。
    - 对于错误操作，抛出相应的异常，返回对应的错误信息和HTTP状态码。
    """

    @setup_required
    @login_required
    @account_initialization_required
    @cloud_edition_billing_resource_check('vector_space')
    def patch(self, dataset_id, segment_id, action):
        dataset_id = str(dataset_id)
        dataset = DatasetService.get_dataset(dataset_id)
        if not dataset:
            raise NotFound('Dataset not found.')

        # 检查用户的数据集模型设置
        DatasetService.check_dataset_model_setting(dataset)
        # The role of the current user in the ta table must be admin, owner, or editor
        if not current_user.is_editor:
            raise Forbidden()

        try:
            DatasetService.check_dataset_permission(dataset, current_user)
        except services.errors.account.NoPermissionError as e:
            raise Forbidden(str(e))

        # 高质量索引技术检查
        if dataset.indexing_technique == 'high_quality':
            # 检查嵌入模型设置
            try:
                model_manager = ModelManager()
                model_manager.get_model_instance(
                    tenant_id=current_user.current_tenant_id,
                    provider=dataset.embedding_model_provider,
                    model_type=ModelType.TEXT_EMBEDDING,
                    model=dataset.embedding_model
                )
            except LLMBadRequestError:
                raise ProviderNotInitializeError(
                    "No Embedding Model available. Please configure a valid provider "
                    "in the Settings -> Model Provider.")
            except ProviderTokenNotInitError as ex:
                raise ProviderNotInitializeError(ex.description)

        # 查询指定的文档段
        segment = DocumentSegment.query.filter(
            DocumentSegment.id == str(segment_id),
            DocumentSegment.tenant_id == current_user.current_tenant_id
        ).first()

        if not segment:
            raise NotFound('Segment not found.')

        # 确保文档段的状态为"completed"
        if segment.status != 'completed':
            raise NotFound('Segment is not completed, enable or disable function is not allowed')

        # 检查文档是否正在被索引
        document_indexing_cache_key = 'document_{}_indexing'.format(segment.document_id)
        cache_result = redis_client.get(document_indexing_cache_key)
        if cache_result is not None:
            raise InvalidActionError("Document is being indexed, please try again later")

        # 检查段是否正在被索引
        indexing_cache_key = 'segment_{}_indexing'.format(segment.id)
        cache_result = redis_client.get(indexing_cache_key)
        if cache_result is not None:
            raise InvalidActionError("Segment is being indexed, please try again later")

        # 根据动作参数，执行启用或禁用操作
        if action == "enable":
            if segment.enabled:
                raise InvalidActionError("Segment is already enabled.")

            segment.enabled = True
            segment.disabled_at = None
            segment.disabled_by = None
            db.session.commit()

            # 设置缓存以防止重复索引同一段
            redis_client.setex(indexing_cache_key, 600, 1)

            # 异步任务：启用段以进行索引
            enable_segment_to_index_task.delay(segment.id)

            return {'result': 'success'}, 200
        elif action == "disable":
            if not segment.enabled:
                raise InvalidActionError("Segment is already disabled.")

            segment.enabled = False
            segment.disabled_at = datetime.now(timezone.utc).replace(tzinfo=None)
            segment.disabled_by = current_user.id
            db.session.commit()

            # 设置缓存以防止重复索引同一段
            redis_client.setex(indexing_cache_key, 600, 1)

            # 异步任务：从索引中禁用段
            disable_segment_from_index_task.delay(segment.id)

            return {'result': 'success'}, 200
        else:
            raise InvalidActionError()


class DatasetDocumentSegmentAddApi(Resource):
    """
    添加文档段落到数据集的API接口
    
    参数:
    - dataset_id: 数据集的唯一标识符
    - document_id: 文档的唯一标识符
    
    返回值:
    - 一个包含新增段落信息的字典，以及文档表单信息
    - HTTP状态码200表示成功
    
    抛出异常:
    - NotFound: 如果指定的数据集或文档不存在
    - Forbidden: 如果当前用户没有权限添加段落
    - ProviderNotInitializeError: 如果嵌入模型未配置或无效
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    @cloud_edition_billing_resource_check('vector_space')
    @cloud_edition_billing_knowledge_limit_check('add_segment')
    def post(self, dataset_id, document_id):
        # 检查数据集存在性
        dataset_id = str(dataset_id)
        dataset = DatasetService.get_dataset(dataset_id)
        if not dataset:
            raise NotFound('Dataset not found.')
        
        # 检查文档存在性
        document_id = str(document_id)
        document = DocumentService.get_document(dataset_id, document_id)
        if not document:
            raise NotFound('Document not found.')
        if not current_user.is_editor:
            raise Forbidden()
        
        # 检查高质索引技术对应的嵌入模型设置
        if dataset.indexing_technique == 'high_quality':
            try:
                model_manager = ModelManager()
                model_manager.get_model_instance(
                    tenant_id=current_user.current_tenant_id,
                    provider=dataset.embedding_model_provider,
                    model_type=ModelType.TEXT_EMBEDDING,
                    model=dataset.embedding_model
                )
            except LLMBadRequestError:
                raise ProviderNotInitializeError(
                    "No Embedding Model available. Please configure a valid provider "
                    "in the Settings -> Model Provider.")
            except ProviderTokenNotInitError as ex:
                raise ProviderNotInitializeError(ex.description)
                
        # 检查用户对数据集的权限
        try:
            DatasetService.check_dataset_permission(dataset, current_user)
        except services.errors.account.NoPermissionError as e:
            raise Forbidden(str(e))
        
        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('content', type=str, required=True, nullable=False, location='json')
        parser.add_argument('answer', type=str, required=False, nullable=True, location='json')
        parser.add_argument('keywords', type=list, required=False, nullable=True, location='json')
        args = parser.parse_args()
        
        # 验证参数合法性
        SegmentService.segment_create_args_validate(args, document)
        
        # 创建新的段落
        segment = SegmentService.create_segment(args, document, dataset)
        
        # 返回创建的段落信息
        return {
            'data': marshal(segment, segment_fields),
            'doc_form': document.doc_form
        }, 200


class DatasetDocumentSegmentUpdateApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @cloud_edition_billing_resource_check('vector_space')
    def patch(self, dataset_id, document_id, segment_id):
        """
        更新文档段落的内容。
        
        参数:
        - dataset_id: 数据集的ID，字符串类型。
        - document_id: 文档的ID，字符串类型。
        - segment_id: 段落的ID，字符串类型。
        
        返回值:
        - 一个包含更新后的段落信息和文档表单的字典，以及HTTP状态码200。
        
        抛出的异常:
        - NotFound: 如果指定的数据集、文档或段落不存在。
        - ProviderNotInitializeError: 如果嵌入模型未配置或提供者未初始化。
        - Forbidden: 如果当前用户没有权限进行此操作。
        - LLMBadRequestError: 如果获取嵌入模型实例时发生错误。
        """
        # 检查数据集存在性
        dataset_id = str(dataset_id)
        dataset = DatasetService.get_dataset(dataset_id)
        if not dataset:
            raise NotFound('Dataset not found.')
        # 检查用户的数据集模型设置
        DatasetService.check_dataset_model_setting(dataset)
        # 检查文档存在性
        document_id = str(document_id)
        document = DocumentService.get_document(dataset_id, document_id)
        if not document:
            raise NotFound('Document not found.')
        if dataset.indexing_technique == 'high_quality':
            # 高质量索引技术下，额外检查嵌入模型设置
            try:
                model_manager = ModelManager()
                model_manager.get_model_instance(
                    tenant_id=current_user.current_tenant_id,
                    provider=dataset.embedding_model_provider,
                    model_type=ModelType.TEXT_EMBEDDING,
                    model=dataset.embedding_model
                )
            except LLMBadRequestError:
                raise ProviderNotInitializeError(
                    "No Embedding Model available. Please configure a valid provider "
                    "in the Settings -> Model Provider.")
            except ProviderTokenNotInitError as ex:
                raise ProviderNotInitializeError(ex.description)
            # 检查段落存在性
        segment_id = str(segment_id)
        segment = DocumentSegment.query.filter(
            DocumentSegment.id == str(segment_id),
            DocumentSegment.tenant_id == current_user.current_tenant_id
        ).first()
        if not segment:
            raise NotFound('Segment not found.')
        # The role of the current user in the ta table must be admin, owner, or editor
        if not current_user.is_editor:
            raise Forbidden()
        try:
            DatasetService.check_dataset_permission(dataset, current_user)
        except services.errors.account.NoPermissionError as e:
            raise Forbidden(str(e))
        # 验证请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('content', type=str, required=True, nullable=False, location='json')
        parser.add_argument('answer', type=str, required=False, nullable=True, location='json')
        parser.add_argument('keywords', type=list, required=False, nullable=True, location='json')
        args = parser.parse_args()
        SegmentService.segment_create_args_validate(args, document)
        # 更新段落信息
        segment = SegmentService.update_segment(args, segment, document, dataset)
        # 返回更新后的段落信息
        return {
            'data': marshal(segment, segment_fields),
            'doc_form': document.doc_form
        }, 200

    @setup_required
    @login_required
    @account_initialization_required
    def delete(self, dataset_id, document_id, segment_id):
        """
        删除特定数据集中的文档段。
        
        参数:
        - dataset_id: 数据集的唯一标识符。
        - document_id: 文档的唯一标识符。
        - segment_id: 文档段的唯一标识符。
        
        返回值:
        - 一个包含结果信息的字典和HTTP状态码200，若成功删除文档段。
        
        抛出异常:
        - NotFound: 当指定的数据集、文档或文档段不存在时。
        - Forbidden: 当用户没有权限删除文档段时。
        """
        # 检查数据集存在性
        dataset_id = str(dataset_id)
        dataset = DatasetService.get_dataset(dataset_id)
        if not dataset:
            raise NotFound('Dataset not found.')
        
        # 检查用户的数据集模型设置
        DatasetService.check_dataset_model_setting(dataset)
        
        # 检查文档存在性
        document_id = str(document_id)
        document = DocumentService.get_document(dataset_id, document_id)
        if not document:
            raise NotFound('Document not found.')
        
        # 检查文档段存在性
        segment_id = str(segment_id)
        segment = DocumentSegment.query.filter(
            DocumentSegment.id == str(segment_id),
            DocumentSegment.tenant_id == current_user.current_tenant_id
        ).first()
        if not segment:
            raise NotFound('Segment not found.')
        # The role of the current user in the ta table must be admin or owner
        if not current_user.is_editor:
            raise Forbidden()
        
        # 检查用户对数据集的权限
        try:
            DatasetService.check_dataset_permission(dataset, current_user)
        except services.errors.account.NoPermissionError as e:
            raise Forbidden(str(e))
        
        # 删除文档段
        SegmentService.delete_segment(segment, document, dataset)
        return {'result': 'success'}, 200


class DatasetDocumentSegmentBatchImportApi(Resource):
    """
    处理文档分段批量导入的API请求。

    要求登录、账户初始化、云版本资源检查、云版本知识限制检查。
    """

    @setup_required
    @login_required
    @account_initialization_required
    @cloud_edition_billing_resource_check('vector_space')
    @cloud_edition_billing_knowledge_limit_check('add_segment')
    def post(self, dataset_id, document_id):
        """
        提交文档分段的批量导入任务。

        参数:
        - dataset_id: 数据集ID，字符串类型。
        - document_id: 文档ID，字符串类型。

        返回值:
        - 任务ID和任务状态，HTTP状态码200。
        - 如果任务不存在或出错，则返回错误信息和HTTP状态码500。
        """
        # 校验数据集存在性
        dataset_id = str(dataset_id)
        dataset = DatasetService.get_dataset(dataset_id)
        if not dataset:
            raise NotFound('Dataset not found.')
        
        # 校验文档存在性
        document_id = str(document_id)
        document = DocumentService.get_document(dataset_id, document_id)
        if not document:
            raise NotFound('Document not found.')
        
        # 从请求中获取文件
        file = request.files['file']
        
        # 校验文件是否上传
        if 'file' not in request.files:
            raise NoFileUploadedError()

        # 校验文件数量
        if len(request.files) > 1:
            raise TooManyFilesError()

        # 校验文件类型
        if not file.filename.endswith('.csv'):
            raise ValueError("Invalid file type. Only CSV files are allowed")

        try:
            # 读取并处理CSV文件
            df = pd.read_csv(file)
            result = []
            for index, row in df.iterrows():
                if document.doc_form == 'qa_model':
                    data = {'content': row[0], 'answer': row[1]}
                else:
                    data = {'content': row[0]}
                result.append(data)
            if len(result) == 0:
                raise ValueError("The CSV file is empty.")
            
            # 创建异步任务
            job_id = str(uuid.uuid4())
            indexing_cache_key = 'segment_batch_import_{}'.format(str(job_id))
            redis_client.setnx(indexing_cache_key, 'waiting')
            batch_create_segment_to_index_task.delay(str(job_id), result, dataset_id, document_id,
                                                     current_user.current_tenant_id, current_user.id)
        except Exception as e:
            return {'error': str(e)}, 500
        return {
            'job_id': job_id,
            'job_status': 'waiting'
        }, 200

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, job_id):
        """
        查询文档分段批量导入任务的状态。

        参数:
        - job_id: 任务ID，字符串类型。

        返回值:
        - 任务ID和任务状态，HTTP状态码200。
        - 如果任务不存在，则返回错误信息和HTTP状态码400。
        """
        job_id = str(job_id)
        indexing_cache_key = 'segment_batch_import_{}'.format(job_id)
        cache_result = redis_client.get(indexing_cache_key)
        if cache_result is None:
            raise ValueError("The job is not exist.")

        return {
            'job_id': job_id,
            'job_status': cache_result.decode()
        }, 200

api.add_resource(DatasetDocumentSegmentListApi,
                 '/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/segments')
api.add_resource(DatasetDocumentSegmentApi,
                 '/datasets/<uuid:dataset_id>/segments/<uuid:segment_id>/<string:action>')
api.add_resource(DatasetDocumentSegmentAddApi,
                 '/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/segment')
api.add_resource(DatasetDocumentSegmentUpdateApi,
                 '/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/segments/<uuid:segment_id>')
api.add_resource(DatasetDocumentSegmentBatchImportApi,
                 '/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/segments/batch_import',
                 '/datasets/batch_import_status/<uuid:job_id>')
