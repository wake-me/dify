import json

from flask import request
from flask_restful import marshal, reqparse
from sqlalchemy import desc
from werkzeug.exceptions import NotFound

import services.dataset_service
from controllers.service_api import api
from controllers.service_api.app.error import ProviderNotInitializeError
from controllers.service_api.dataset.error import (
    ArchivedDocumentImmutableError,
    DocumentIndexingError,
    NoFileUploadedError,
    TooManyFilesError,
)
from controllers.service_api.wraps import DatasetApiResource, cloud_edition_billing_resource_check
from core.errors.error import ProviderTokenNotInitError
from extensions.ext_database import db
from fields.document_fields import document_fields, document_status_fields
from libs.login import current_user
from models.dataset import Dataset, Document, DocumentSegment
from services.dataset_service import DocumentService
from services.file_service import FileService


class DocumentAddByTextApi(DatasetApiResource):
    """文档资源类。"""

    @cloud_edition_billing_resource_check('vector_space', 'dataset')
    @cloud_edition_billing_resource_check('documents', 'dataset')
    def post(self, tenant_id, dataset_id):
        """
        通过文本创建文档。

        参数:
        - tenant_id: 租户ID，字符串类型，标识租户。
        - dataset_id: 数据集ID，字符串类型，标识数据集。

        返回值:
        - 一个包含文档和批次信息的字典，以及HTTP状态码200。
        """

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('name', type=str, required=True, nullable=False, location='json')
        parser.add_argument('text', type=str, required=True, nullable=False, location='json')
        parser.add_argument('process_rule', type=dict, required=False, nullable=True, location='json')
        parser.add_argument('original_document_id', type=str, required=False, location='json')
        parser.add_argument('doc_form', type=str, default='text_model', required=False, nullable=False, location='json')
        parser.add_argument('doc_language', type=str, default='English', required=False, nullable=False,
                            location='json')
        parser.add_argument('indexing_technique', type=str, choices=Dataset.INDEXING_TECHNIQUE_LIST, nullable=False,
                            location='json')
        parser.add_argument('retrieval_model', type=dict, required=False, nullable=False,
                            location='json')
        args = parser.parse_args()

        # 验证数据集存在性和索引技术的必要性
        dataset_id = str(dataset_id)
        tenant_id = str(tenant_id)
        dataset = db.session.query(Dataset).filter(
            Dataset.tenant_id == tenant_id,
            Dataset.id == dataset_id
        ).first()

        if not dataset:
            raise ValueError('Dataset is not exist.')

        if not dataset.indexing_technique and not args['indexing_technique']:
            raise ValueError('indexing_technique is required.')

        # 上传文本文件
        upload_file = FileService.upload_text(args.get('text'), args.get('name'))
        data_source = {
            'type': 'upload_file',
            'info_list': {
                'data_source_type': 'upload_file',
                'file_info_list': {
                    'file_ids': [upload_file.id]
                }
            }
        }
        args['data_source'] = data_source

        # 验证创建文档的参数
        DocumentService.document_create_args_validate(args)

        try:
            # 保存文档到数据集
            documents, batch = DocumentService.save_document_with_dataset_id(
                dataset=dataset,
                document_data=args,
                account=current_user,
                dataset_process_rule=dataset.latest_process_rule if 'process_rule' not in args else None,
                created_from='api'
            )
        except ProviderTokenNotInitError as ex:
            raise ProviderNotInitializeError(ex.description)
        document = documents[0]

        # 返回创建的文档和批次信息
        documents_and_batch_fields = {
            'document': marshal(document, document_fields),
            'batch': batch
        }
        return documents_and_batch_fields, 200


class DocumentUpdateByTextApi(DatasetApiResource):
    """用于更新文档的资源类。"""

    @cloud_edition_billing_resource_check('vector_space', 'dataset')
    def post(self, tenant_id, dataset_id, document_id):
        """
        通过文本更新文档。
        
        参数:
        - tenant_id: 租户ID，字符串类型，标识租户。
        - dataset_id: 数据集ID，字符串类型，标识数据集。
        - document_id: 文档ID，字符串类型，标识要更新的文档。
        
        返回值:
        - 一个包含更新后的文档信息和批处理信息的字典，以及HTTP状态码200。
        
        抛出:
        - ValueError: 如果指定的数据集不存在。
        - ProviderNotInitializeError: 如果提供商未初始化。
        """
        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('name', type=str, required=False, nullable=True, location='json')
        parser.add_argument('text', type=str, required=False, nullable=True, location='json')
        parser.add_argument('process_rule', type=dict, required=False, nullable=True, location='json')
        parser.add_argument('doc_form', type=str, default='text_model', required=False, nullable=False, location='json')
        parser.add_argument('doc_language', type=str, default='English', required=False, nullable=False,
                            location='json')
        parser.add_argument('retrieval_model', type=dict, required=False, nullable=False,
                            location='json')
        args = parser.parse_args()
        
        # 校验数据集存在性
        dataset_id = str(dataset_id)
        tenant_id = str(tenant_id)
        dataset = db.session.query(Dataset).filter(
            Dataset.tenant_id == tenant_id,
            Dataset.id == dataset_id
        ).first()
        
        if not dataset:
            raise ValueError('Dataset is not exist.')

        # 处理上传的文本文件
        if args['text']:
            upload_file = FileService.upload_text(args.get('text'), args.get('name'))
            data_source = {
                'type': 'upload_file',
                'info_list': {
                    'data_source_type': 'upload_file',
                    'file_info_list': {
                        'file_ids': [upload_file.id]
                    }
                }
            }
            args['data_source'] = data_source
        
        # 验证参数合法性
        args['original_document_id'] = str(document_id)
        DocumentService.document_create_args_validate(args)

        try:
            # 保存文档并返回更新后的文档和批处理信息
            documents, batch = DocumentService.save_document_with_dataset_id(
                dataset=dataset,
                document_data=args,
                account=current_user,
                dataset_process_rule=dataset.latest_process_rule if 'process_rule' not in args else None,
                created_from='api'
            )
        except ProviderTokenNotInitError as ex:
            raise ProviderNotInitializeError(ex.description)
        document = documents[0]

        # 构装返回的数据
        documents_and_batch_fields = {
            'document': marshal(document, document_fields),
            'batch': batch
        }
        return documents_and_batch_fields, 200


class DocumentAddByFileApi(DatasetApiResource):
    """文档资源类。"""
    
    @cloud_edition_billing_resource_check('vector_space', 'dataset')
    @cloud_edition_billing_resource_check('documents', 'dataset')
    def post(self, tenant_id, dataset_id):
        """
        通过上传文件创建文档。
        
        参数:
        - tenant_id: 租户ID，字符串类型，用于标识租户。
        - dataset_id: 数据集ID，字符串类型，用于标识数据集。
        
        返回值:
        - 一个包含文档和批次信息的字典，以及HTTP状态码200。
        
        抛出:
        - ValueError: 当数据集不存在或未指定索引技术时抛出。
        - NoFileUploadedError: 当没有上传文件时抛出。
        - TooManyFilesError: 当上传文件数量超过1个时抛出。
        - ProviderNotInitializeError: 当供应商未初始化时抛出。
        """
        # 解析请求参数
        args = {}
        if 'data' in request.form:
            args = json.loads(request.form['data'])
        # 设置默认参数
        if 'doc_form' not in args:
            args['doc_form'] = 'text_model'
        if 'doc_language' not in args:
            args['doc_language'] = 'English'
        
        # 获取数据集信息
        dataset_id = str(dataset_id)
        tenant_id = str(tenant_id)
        dataset = db.session.query(Dataset).filter(
            Dataset.tenant_id == tenant_id,
            Dataset.id == dataset_id
        ).first()
        
        # 数据集存在性检查和索引技术验证
        if not dataset:
            raise ValueError('Dataset is not exist.')
        if not dataset.indexing_technique and not args.get('indexing_technique'):
            raise ValueError('indexing_technique is required.')

        # 处理文件上传
        file = request.files['file']
        # 检查是否上传了文件
        if 'file' not in request.files:
            raise NoFileUploadedError()

        if len(request.files) > 1:
            raise TooManyFilesError()

        upload_file = FileService.upload_file(file, current_user)
        data_source = {
            'type': 'upload_file',
            'info_list': {
                'file_info_list': {
                    'file_ids': [upload_file.id]
                }
            }
        }
        args['data_source'] = data_source
        
        # 参数验证
        DocumentService.document_create_args_validate(args)

        try:
            # 文档创建和保存
            documents, batch = DocumentService.save_document_with_dataset_id(
                dataset=dataset,
                document_data=args,
                account=dataset.created_by_account,
                dataset_process_rule=dataset.latest_process_rule if 'process_rule' not in args else None,
                created_from='api'
            )
        except ProviderTokenNotInitError as ex:
            raise ProviderNotInitializeError(ex.description)
        
        # 构装返回数据
        document = documents[0]
        documents_and_batch_fields = {
            'document': marshal(document, document_fields),
            'batch': batch
        }
        return documents_and_batch_fields, 200


class DocumentUpdateByFileApi(DatasetApiResource):
    """用于更新文档的资源类。"""

    @cloud_edition_billing_resource_check('vector_space', 'dataset')
    def post(self, tenant_id, dataset_id, document_id):
        """
        通过上传文件更新文档。
        
        参数:
        - tenant_id: 租户ID，字符串类型，用于标识租户。
        - dataset_id: 数据集ID，字符串类型，用于标识数据集。
        - document_id: 文档ID，字符串类型，用于标识需要更新的文档。
        
        返回值:
        - 一个包含更新后的文档信息和批处理信息的字典，以及HTTP状态码200。
        
        异常:
        - ValueError: 如果数据集不存在。
        - TooManyFilesError: 如果上传的文件数量超过1个。
        - ProviderNotInitializeError: 如果数据提供商未初始化。
        """
        args = {}
        # 从请求表单中获取参数
        if 'data' in request.form:
            args = json.loads(request.form['data'])
        # 设置默认的文档形式和语言
        if 'doc_form' not in args:
            args['doc_form'] = 'text_model'
        if 'doc_language' not in args:
            args['doc_language'] = 'English'

        # 获取数据集信息
        dataset_id = str(dataset_id)
        tenant_id = str(tenant_id)
        dataset = db.session.query(Dataset).filter(
            Dataset.tenant_id == tenant_id,
            Dataset.id == dataset_id
        ).first()

        # 数据集存在性验证
        if not dataset:
            raise ValueError('Dataset is not exist.')
        # 处理文件上传
        if 'file' in request.files:
            # 检查是否上传多个文件
            if len(request.files) > 1:
                raise TooManyFilesError()

            # 保存上传的文件
            file = request.files['file']
            upload_file = FileService.upload_file(file, current_user)
            data_source = {
                'type': 'upload_file',
                'info_list': {
                    'file_info_list': {
                        'file_ids': [upload_file.id]
                    }
                }
            }
            args['data_source'] = data_source
        # 验证参数合法性
        args['original_document_id'] = str(document_id)
        DocumentService.document_create_args_validate(args)

        try:
            # 保存文档并返回相关信息
            documents, batch = DocumentService.save_document_with_dataset_id(
                dataset=dataset,
                document_data=args,
                account=dataset.created_by_account,
                dataset_process_rule=dataset.latest_process_rule if 'process_rule' not in args else None,
                created_from='api'
            )
        except ProviderTokenNotInitError as ex:
            # 处理数据提供商未初始化异常
            raise ProviderNotInitializeError(ex.description)
        document = documents[0]
        documents_and_batch_fields = {
            'document': marshal(document, document_fields),
            'batch': batch
        }
        return documents_and_batch_fields, 200


class DocumentDeleteApi(DatasetApiResource):
    def delete(self, tenant_id, dataset_id, document_id):
        """
        删除文档。

        参数:
        tenant_id (str): 租户ID。
        dataset_id (str): 数据集ID。
        document_id (str): 文档ID。

        返回:
        tuple: 包含成功删除的响应和HTTP状态码200。
        """

        # 将输入ID转换为字符串格式
        document_id = str(document_id)
        dataset_id = str(dataset_id)
        tenant_id = str(tenant_id)

        # 查询数据集信息
        dataset = db.session.query(Dataset).filter(
            Dataset.tenant_id == tenant_id,
            Dataset.id == dataset_id
        ).first()

        # 如果数据集不存在，则抛出异常
        if not dataset:
            raise ValueError('Dataset is not exist.')

        # 尝试获取文档
        document = DocumentService.get_document(dataset.id, document_id)

        # 如果文档不存在，抛出404异常
        if document is None:
            raise NotFound("Document Not Exists.")

        # 如果文档已归档，抛出403异常
        if DocumentService.check_archived(document):
            raise ArchivedDocumentImmutableError()

        try:
            # 尝试删除文档，如果正在索引时删除文档，会抛出异常
            DocumentService.delete_document(document)
        except services.errors.document.DocumentIndexingError:
            raise DocumentIndexingError('Cannot delete document during indexing.')

        # 返回删除成功的消息
        return {'result': 'success'}, 200


class DocumentListApi(DatasetApiResource):
    """
    文档列表API接口类，用于通过特定的租户ID和数据集ID获取文档列表。
    
    方法:
    - get: 根据租户ID和数据集ID获取文档列表的分页数据。
    
    参数:
    - tenant_id: 租户的唯一标识符。
    - dataset_id: 数据集的唯一标识符。
    
    返回值:
    - 返回一个包含文档数据、是否有更多数据、每页限制、总数据量和当前页码的字典。
    """
    
    def get(self, tenant_id, dataset_id):
        # 将传入的ID参数转换为字符串类型
        dataset_id = str(dataset_id)
        tenant_id = str(tenant_id)

        # 从请求参数中获取页码和每页数量，并设置默认值
        page = request.args.get('page', default=1, type=int)
        limit = request.args.get('limit', default=20, type=int)

        # 从请求参数中获取搜索关键字
        search = request.args.get('keyword', default=None, type=str)

        # 根据租户ID和数据集ID查询数据集信息
        dataset = db.session.query(Dataset).filter(
            Dataset.tenant_id == tenant_id,
            Dataset.id == dataset_id
        ).first()
        
        # 如果数据集不存在，则抛出未找到异常
        if not dataset:
            raise NotFound('Dataset not found.')

        # 构建文档查询基础查询条件
        query = Document.query.filter_by(
            dataset_id=str(dataset_id), tenant_id=tenant_id)

        # 如果存在搜索关键字，则添加到查询条件中
        if search:
            search = f'%{search}%'
            query = query.filter(Document.name.like(search))

        # 根据创建时间对查询结果进行降序排序
        query = query.order_by(desc(Document.created_at))

        # 执行分页查询，并获取当前页的文档列表
        paginated_documents = query.paginate(
            page=page, per_page=limit, max_per_page=100, error_out=False)
        documents = paginated_documents.items

        # 构建并返回查询结果的响应字典
        response = {
            'data': marshal(documents, document_fields),
            'has_more': len(documents) == limit,
            'limit': limit,
            'total': paginated_documents.total,
            'page': page
        }

        return response


class DocumentIndexingStatusApi(DatasetApiResource):
    """
    文档索引状态API，用于获取特定数据集和批次的文档索引状态。
    
    参数:
    - tenant_id: 租户ID，用于识别不同的租户。
    - dataset_id: 数据集ID，用于识别特定的数据集。
    - batch: 批次号，用于识别文档所属的批次。
    
    返回值:
    - 返回一个包含文档索引状态的字典。
    """
    
    def get(self, tenant_id, dataset_id, batch):
        # 将输入参数转换为字符串类型
        dataset_id = str(dataset_id)
        batch = str(batch)
        tenant_id = str(tenant_id)
        
        # 根据租户ID和数据集ID查询数据集
        dataset = db.session.query(Dataset).filter(
            Dataset.tenant_id == tenant_id,
            Dataset.id == dataset_id
        ).first()
        # 如果数据集不存在，则抛出异常
        if not dataset:
            raise NotFound('Dataset not found.')
        
        # 根据数据集ID和批次获取文档
        documents = DocumentService.get_batch_documents(dataset_id, batch)
        # 如果文档不存在，则抛出异常
        if not documents:
            raise NotFound('Documents not found.')
        
        documents_status = []
        for document in documents:
            # 查询已完成的文档段数量和总段数量
            completed_segments = DocumentSegment.query.filter(DocumentSegment.completed_at.isnot(None),
                                                              DocumentSegment.document_id == str(document.id),
                                                              DocumentSegment.status != 're_segment').count()
            total_segments = DocumentSegment.query.filter(DocumentSegment.document_id == str(document.id),
                                                          DocumentSegment.status != 're_segment').count()
            # 更新文档的完成段数和总段数
            document.completed_segments = completed_segments
            document.total_segments = total_segments
            # 如果文档暂停，则设置索引状态为"paused"
            if document.is_paused:
                document.indexing_status = 'paused'
            # 将文档状态信息进行封装
            documents_status.append(marshal(document, document_status_fields))
        
        # 准备并返回最终的数据
        data = {
            'data': documents_status
        }
        return data


api.add_resource(DocumentAddByTextApi, '/datasets/<uuid:dataset_id>/document/create_by_text')
api.add_resource(DocumentAddByFileApi, '/datasets/<uuid:dataset_id>/document/create_by_file')
api.add_resource(DocumentUpdateByTextApi, '/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/update_by_text')
api.add_resource(DocumentUpdateByFileApi, '/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/update_by_file')
api.add_resource(DocumentDeleteApi, '/datasets/<uuid:dataset_id>/documents/<uuid:document_id>')
api.add_resource(DocumentListApi, '/datasets/<uuid:dataset_id>/documents')
api.add_resource(DocumentIndexingStatusApi, '/datasets/<uuid:dataset_id>/documents/<string:batch>/indexing-status')
