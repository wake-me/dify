import datetime
import json
import logging
import random
import time
import uuid
from typing import Optional

from flask import current_app
from flask_login import current_user
from sqlalchemy import func

from core.errors.error import LLMBadRequestError, ProviderTokenNotInitError
from core.model_manager import ModelManager
from core.model_runtime.entities.model_entities import ModelType
from core.rag.datasource.keyword.keyword_factory import Keyword
from core.rag.models.document import Document as RAGDocument
from events.dataset_event import dataset_was_deleted
from events.document_event import document_was_deleted
from extensions.ext_database import db
from extensions.ext_redis import redis_client
from libs import helper
from models.account import Account
from models.dataset import (
    AppDatasetJoin,
    Dataset,
    DatasetCollectionBinding,
    DatasetProcessRule,
    DatasetQuery,
    Document,
    DocumentSegment,
)
from models.model import UploadFile
from models.source import DataSourceBinding
from services.errors.account import NoPermissionError
from services.errors.dataset import DatasetNameDuplicateError
from services.errors.document import DocumentIndexingError
from services.errors.file import FileNotExistsError
from services.feature_service import FeatureModel, FeatureService
from services.tag_service import TagService
from services.vector_service import VectorService
from tasks.clean_notion_document_task import clean_notion_document_task
from tasks.deal_dataset_vector_index_task import deal_dataset_vector_index_task
from tasks.delete_segment_from_index_task import delete_segment_from_index_task
from tasks.disable_segment_from_index_task import disable_segment_from_index_task
from tasks.document_indexing_task import document_indexing_task
from tasks.document_indexing_update_task import document_indexing_update_task
from tasks.duplicate_document_indexing_task import duplicate_document_indexing_task
from tasks.recover_document_indexing_task import recover_document_indexing_task
from tasks.retry_document_indexing_task import retry_document_indexing_task


class DatasetService:

    @staticmethod
    def get_datasets(page, per_page, provider="vendor", tenant_id=None, user=None, search=None, tag_ids=None):
        if user:
            permission_filter = db.or_(Dataset.created_by == user.id,
                                    Dataset.permission == 'all_team_members')
        else:
            permission_filter = Dataset.permission == 'all_team_members'
        query = Dataset.query.filter(
            db.and_(Dataset.provider == provider, Dataset.tenant_id == tenant_id, permission_filter)) \
            .order_by(Dataset.created_at.desc())
        if search:
            query = query.filter(db.and_(Dataset.name.ilike(f'%{search}%')))
        if tag_ids:
            target_ids = TagService.get_target_ids_by_tag_ids('knowledge', tenant_id, tag_ids)
            if target_ids:
                query = query.filter(db.and_(Dataset.id.in_(target_ids)))
            else:
                return [], 0
        datasets = query.paginate(
            page=page,
            per_page=per_page,
            max_per_page=100,
            error_out=False
        )

        return datasets.items, datasets.total

    @staticmethod
    def get_process_rules(dataset_id):
        """
        获取指定数据集的最新处理规则。

        参数:
        - dataset_id: 数据集的唯一标识符。

        返回值:
        - 一个字典，包含处理规则的模式（mode）和具体规则（rules）。
        """
        # 从数据库中查询最新的数据集处理规则
        dataset_process_rule = db.session.query(DatasetProcessRule). \
            filter(DatasetProcessRule.dataset_id == dataset_id). \
            order_by(DatasetProcessRule.created_at.desc()). \
            limit(1). \
            one_or_none()
        
        # 如果找到了处理规则，则使用找到的规则；否则，使用默认规则
        if dataset_process_rule:
            mode = dataset_process_rule.mode
            rules = dataset_process_rule.rules_dict
        else:
            mode = DocumentService.DEFAULT_RULES['mode']
            rules = DocumentService.DEFAULT_RULES['rules']
        
        # 返回处理规则的模式和具体规则
        return {
            'mode': mode,
            'rules': rules
        }

    @staticmethod
    def get_datasets_by_ids(ids, tenant_id):
        """
        根据提供的ID列表和租户ID获取数据集。
        
        参数:
        ids -- 数据集ID的列表，这些ID用于查询特定的数据集。
        tenant_id -- 租户ID，查询限定于该租户拥有的数据集。
        
        返回值:
        返回一个包含数据集实例的列表以及数据集总数。
        """
        # 使用ORM方式构建查询，筛选出指定ID和租户ID的数据集
        datasets = Dataset.query.filter(Dataset.id.in_(ids),
                                        Dataset.tenant_id == tenant_id).paginate(
            page=1, per_page=len(ids), max_per_page=len(ids), error_out=False)
        # 返回查询结果中的数据集实例列表和总数量
        return datasets.items, datasets.total

    @staticmethod
    def create_empty_dataset(tenant_id: str, name: str, indexing_technique: Optional[str], account: Account):
        """
        创建一个空的数据集。

        参数:
        tenant_id (str): 租户ID，用于标识数据集所属的租户。
        name (str): 数据集的名称。
        indexing_technique (Optional[str]): 数据集的索引技术类型，可以为空。如果指定为'high_quality'，则会尝试使用高质量的嵌入模型。
        account (Account): 创建数据集的账户信息。

        返回值:
        Dataset: 创建的空数据集对象。
        """
        # 检查数据集名称是否已经存在
        if Dataset.query.filter_by(name=name, tenant_id=tenant_id).first():
            raise DatasetNameDuplicateError(
                f'Dataset with name {name} already exists.')
        
        embedding_model = None
        # 如果指定了高质量索引技术，尝试获取默认的文本嵌入模型
        if indexing_technique == 'high_quality':
            model_manager = ModelManager()
            embedding_model = model_manager.get_default_model_instance(
                tenant_id=tenant_id,
                model_type=ModelType.TEXT_EMBEDDING
            )
        
        # 创建数据集实例，并设置相关信息
        dataset = Dataset(name=name, indexing_technique=indexing_technique)
        dataset.created_by = account.id
        dataset.updated_by = account.id
        dataset.tenant_id = tenant_id
        # 如果存在嵌入模型，则设置模型的提供者和模型本身
        dataset.embedding_model_provider = embedding_model.provider if embedding_model else None
        dataset.embedding_model = embedding_model.model if embedding_model else None
        
        # 将数据集实例添加到数据库会话，并提交事务
        db.session.add(dataset)
        db.session.commit()
        
        return dataset

    @staticmethod
    def get_dataset(dataset_id):
        return Dataset.query.filter_by(
            id=dataset_id
        ).first()

    @staticmethod
    def check_dataset_model_setting(dataset):
        """
        检查数据集的模型设置是否正确。
        
        参数:
        - dataset: 一个数据集对象，必须包含indexing_technique, tenant_id, embedding_model_provider,
                    embedding_model等属性。
                    
        若数据集的索引技术为'high_quality'，则尝试获取相应的嵌入模型实例。如果无法获取成功，
        将抛出适当的错误提示用户配置问题或数据集不可用的原因。
        """
        if dataset.indexing_technique == 'high_quality':
            try:
                model_manager = ModelManager()  # 尝试创建模型管理器实例
                model_manager.get_model_instance(
                    tenant_id=dataset.tenant_id,
                    provider=dataset.embedding_model_provider,
                    model_type=ModelType.TEXT_EMBEDDING,
                    model=dataset.embedding_model
                )  # 尝试根据数据集的设置获取嵌入模型实例
            except LLMBadRequestError:
                # 如果请求模型实例失败，抛出值错误，提示用户没有可用的嵌入模型
                raise ValueError(
                    "No Embedding Model available. Please configure a valid provider "
                    "in the Settings -> Model Provider.")
            except ProviderTokenNotInitError as ex:
                # 如果因为提供商令牌未初始化导致失败，抛出值错误，说明数据集不可用的具体原因
                raise ValueError(f"The dataset in unavailable, due to: "
                                f"{ex.description}")

    @staticmethod
    def update_dataset(dataset_id, data, user):
        """
        更新数据集的信息。

        参数:
        - dataset_id: 数据集的唯一标识符。
        - data: 包含要更新的数据集字段的字典。
        - user: 进行更新操作的用户对象。

        返回值:
        - 更新后的数据集对象。
        """
        # 过滤掉值为None的字段，但保留'description'字段
        filtered_data = {k: v for k, v in data.items() if v is not None or k == 'description'}
        # 根据数据集ID获取数据集对象
        dataset = DatasetService.get_dataset(dataset_id)
        # 检查用户是否有更新数据集的权限
        DatasetService.check_dataset_permission(dataset, user)
        action = None
        # 如果更新索引技术
        if dataset.indexing_technique != data['indexing_technique']:
            # 根据新的索引技术确定需要添加或移除的属性
            if data['indexing_technique'] == 'economy':
                action = 'remove'
                # 移除与经济型索引技术相关的属性
                filtered_data['embedding_model'] = None
                filtered_data['embedding_model_provider'] = None
                filtered_data['collection_binding_id'] = None
            elif data['indexing_technique'] == 'high_quality':
                action = 'add'
                # 为高质量索引技术设置嵌入模型和绑定信息
                try:
                    model_manager = ModelManager()
                    embedding_model = model_manager.get_model_instance(
                        tenant_id=current_user.current_tenant_id,
                        provider=data['embedding_model_provider'],
                        model_type=ModelType.TEXT_EMBEDDING,
                        model=data['embedding_model']
                    )
                    filtered_data['embedding_model'] = embedding_model.model
                    filtered_data['embedding_model_provider'] = embedding_model.provider
                    dataset_collection_binding = DatasetCollectionBindingService.get_dataset_collection_binding(
                        embedding_model.provider,
                        embedding_model.model
                    )
                    filtered_data['collection_binding_id'] = dataset_collection_binding.id
                except LLMBadRequestError:
                    raise ValueError(
                        "No Embedding Model available. Please configure a valid provider "
                        "in the Settings -> Model Provider.")
                except ProviderTokenNotInitError as ex:
                    raise ValueError(ex.description)
        else:
            if data['embedding_model_provider'] != dataset.embedding_model_provider or \
                    data['embedding_model'] != dataset.embedding_model:
                action = 'update'
                try:
                    model_manager = ModelManager()
                    embedding_model = model_manager.get_model_instance(
                        tenant_id=current_user.current_tenant_id,
                        provider=data['embedding_model_provider'],
                        model_type=ModelType.TEXT_EMBEDDING,
                        model=data['embedding_model']
                    )
                    filtered_data['embedding_model'] = embedding_model.model
                    filtered_data['embedding_model_provider'] = embedding_model.provider
                    dataset_collection_binding = DatasetCollectionBindingService.get_dataset_collection_binding(
                        embedding_model.provider,
                        embedding_model.model
                    )
                    filtered_data['collection_binding_id'] = dataset_collection_binding.id
                except LLMBadRequestError:
                    raise ValueError(
                        "No Embedding Model available. Please configure a valid provider "
                        "in the Settings -> Model Provider.")
                except ProviderTokenNotInitError as ex:
                    raise ValueError(ex.description)

        filtered_data['updated_by'] = user.id
        filtered_data['updated_at'] = datetime.datetime.now()
        filtered_data['retrieval_model'] = data['retrieval_model']

        # 执行数据库更新操作
        dataset.query.filter_by(id=dataset_id).update(filtered_data)
        db.session.commit()
        # 如果有索引技术变更，则异步处理数据集向量索引任务
        if action:
            deal_dataset_vector_index_task.delay(dataset_id, action)
        return dataset

    @staticmethod
    def delete_dataset(dataset_id, user):
        """
        删除指定的数据集。

        参数:
        - dataset_id: 数据集的唯一标识符。
        - user: 请求删除数据集的用户。

        返回值:
        - 如果数据集成功被删除，返回True；如果数据集不存在或删除失败，返回False。
        """
        
        # 尝试获取指定ID的数据集
        dataset = DatasetService.get_dataset(dataset_id)

        # 如果数据集不存在，则直接返回False
        if dataset is None:
            return False

        # 检查用户是否有权限删除该数据集
        DatasetService.check_dataset_permission(dataset, user)

        # 发送数据集即将被删除的信号
        dataset_was_deleted.send(dataset)

        # 从数据库会话中删除数据集并提交更改
        db.session.delete(dataset)
        db.session.commit()
        return True

    @staticmethod
    def check_dataset_permission(dataset, user):
        """
        检查用户是否有权限访问特定数据集。
        
        参数:
        - dataset: 数据集对象，包含数据集的元数据，如租户ID和权限信息。
        - user: 用户对象，包含用户的元数据，如当前租户ID。
        
        抛出:
        - NoPermissionError: 如果用户没有访问数据集的权限，则抛出此错误。
        """
        # 检查数据集的租户ID是否与用户当前的租户ID匹配
        if dataset.tenant_id != user.current_tenant_id:
            logging.debug(
                f'User {user.id} does not have permission to access dataset {dataset.id}')
            raise NoPermissionError(
                'You do not have permission to access this dataset.')
        
        # 检查数据集的权限是否设置为'only_me'，并且数据集的创建者不是当前用户
        if dataset.permission == 'only_me' and dataset.created_by != user.id:
            logging.debug(
                f'User {user.id} does not have permission to access dataset {dataset.id}')
            raise NoPermissionError(
                'You do not have permission to access this dataset.')

    @staticmethod
    def get_dataset_queries(dataset_id: str, page: int, per_page: int):
        """
        获取指定数据集ID的查询记录。

        参数:
        - dataset_id: str，要查询的数据集ID。
        - page: int，请求的页码。
        - per_page: int，每页显示的记录数。

        返回值:
        - items: 查询结果列表，包含指定页码的查询记录。
        - total: 查询结果总数。
        """
        # 根据数据集ID过滤查询记录，并按创建时间降序排序
        dataset_queries = DatasetQuery.query.filter_by(dataset_id=dataset_id) \
            .order_by(db.desc(DatasetQuery.created_at)) \
            .paginate(
            page=page, per_page=per_page, max_per_page=100, error_out=False
        )
        # 返回查询结果列表和总记录数
        return dataset_queries.items, dataset_queries.total

    @staticmethod
    def get_related_apps(dataset_id: str):
        """
        获取与特定数据集关联的应用程序列表。

        参数:
        - dataset_id: 数据集的唯一标识符，类型为字符串。

        返回值:
        - 返回一个查询结果列表，包含所有与指定数据集相关联的应用程序对象，这些对象是根据它们与数据集关联的时间倒序排列的。
        """
        # 根据数据集ID查询关联的应用程序，按创建时间倒序排序，并获取所有结果
        return AppDatasetJoin.query.filter(AppDatasetJoin.dataset_id == dataset_id) \
            .order_by(db.desc(AppDatasetJoin.created_at)).all()


class DocumentService:
    # 默认规则配置
    DEFAULT_RULES = {
        'mode': 'custom',  # 模式设置为自定义
        'rules': {  # 规则配置
            'pre_processing_rules': [  # 预处理规则列表
                {'id': 'remove_extra_spaces', 'enabled': True},  # 移除多余空格规则，启用
                {'id': 'remove_urls_emails', 'enabled': False}  # 移除URL和电子邮件规则，禁用
            ],
            'segmentation': {  # 分割配置
                'delimiter': '\n',  # 分隔符设置为换行符
                'max_tokens': 500,  # 最大分词数
                'chunk_overlap': 50  # 分块重叠数
            }
        }
    }

    # 定义文档元数据的模式
    DOCUMENT_METADATA_SCHEMA = {
        "book": {  # 书籍元数据
            "title": str,  # 标题
            "language": str,  # 语言
            "author": str,  # 作者
            "publisher": str,  # 出版社
            "publication_date": str,  # 出版日期
            "isbn": str,  # ISBN号
            "category": str,  # 类别
        },
        "web_page": {  # 网页元数据
            "title": str,  # 标题
            "url": str,  # URL
            "language": str,  # 语言
            "publish_date": str,  # 发布日期
            "author/publisher": str,  # 作者或发布者
            "topic/keywords": str,  # 主题或关键词
            "description": str,  # 描述
        },
        "paper": {  # 论文元数据
            "title": str,  # 标题
            "language": str,  # 语言
            "author": str,  # 作者
            "publish_date": str,  # 发表日期
            "journal/conference_name": str,  # 期刊或会议名称
            "volume/issue/page_numbers": str,  # 卷号/期号/页码
            "doi": str,  # DOI
            "topic/keywords": str,  # 主题或关键词
            "abstract": str,  # 摘要
        },
        "social_media_post": {  # 社交媒体帖子元数据
            "platform": str,  # 平台
            "author/username": str,  # 作者/用户名
            "publish_date": str,  # 发布日期
            "post_url": str,  # 帖子URL
            "topic/tags": str,  # 主题/标签
        },
        "wikipedia_entry": {  # 维基百科条目元数据
            "title": str,  # 标题
            "language": str,  # 语言
            "web_page_url": str,  # 网页URL
            "last_edit_date": str,  # 最后编辑日期
            "editor/contributor": str,  # 编辑者/贡献者
            "summary/introduction": str,  # 摘要/介绍
        },
        "personal_document": {  # 个人文档元数据
            "title": str,  # 标题
            "author": str,  # 作者
            "creation_date": str,  # 创建日期
            "last_modified_date": str,  # 最后修改日期
            "document_type": str,  # 文档类型
            "tags/category": str,  # 标签/类别
        },
        "business_document": {  # 商业文档元数据
            "title": str,  # 标题
            "author": str,  # 作者
            "creation_date": str,  # 创建日期
            "last_modified_date": str,  # 最后修改日期
            "document_type": str,  # 文档类型
            "department/team": str,  # 部门/团队
        },
        "im_chat_log": {  # 即时聊天日志元数据
            "chat_platform": str,  # 聊天平台
            "chat_participants/group_name": str,  # 聊天参与者/群组名称
            "start_date": str,  # 开始日期
            "end_date": str,  # 结束日期
            "summary": str,  # 摘要
        },
        "synced_from_notion": {  # 从Notion同步的文档元数据
            "title": str,  # 标题
            "language": str,  # 语言
            "author/creator": str,  # 作者/创建者
            "creation_date": str,  # 创建日期
            "last_modified_date": str,  # 最后修改日期
            "notion_page_link": str,  # Notion页面链接
            "category/tags": str,  # 类别/标签
            "description": str,  # 描述
        },
        "synced_from_github": {  # 从GitHub同步的代码文件元数据
            "repository_name": str,  # 仓库名称
            "repository_description": str,  # 仓库描述
            "repository_owner/organization": str,  # 仓库所有者/组织
            "code_filename": str,  # 代码文件名
            "code_file_path": str,  # 代码文件路径
            "programming_language": str,  # 编程语言
            "github_link": str,  # GitHub链接
            "open_source_license": str,  # 开源许可证
            "commit_date": str,  # 提交日期
            "commit_author": str,  # 提交作者
        },
        "others": dict  # 其他类型的文档元数据，以字典形式存储
    }

    @staticmethod
    def get_document(dataset_id: str, document_id: str) -> Optional[Document]:
        """
        从数据库中获取指定数据集ID和文档ID的文档对象。
        
        参数:
        - dataset_id: str，指定的数据集ID。
        - document_id: str，指定的文档ID。
        
        返回值:
        - Optional[Document]，如果找到对应的文档，则返回Document对象，否则返回None。
        """
        # 根据数据集ID和文档ID查询数据库，获取第一个匹配的文档对象
        document = db.session.query(Document).filter(
            Document.id == document_id,
            Document.dataset_id == dataset_id
        ).first()

        return document

    @staticmethod
    def get_document_by_id(document_id: str) -> Optional[Document]:
        """
        根据文档ID从数据库中获取文档对象。
        
        参数:
        document_id: str - 需要查询的文档的ID，为字符串类型。
        
        返回值:
        Optional[Document] - 如果找到对应文档，则返回Document对象；否则返回None。
        """
        # 从数据库中查询指定ID的文档，并获取第一条结果
        document = db.session.query(Document).filter(
            Document.id == document_id
        ).first()

        return document

    @staticmethod
    def get_document_by_dataset_id(dataset_id: str) -> list[Document]:
        """
        根据数据集ID获取文档列表。
        
        参数:
        - dataset_id: str，要查询的数据集的唯一标识符。
        
        返回值:
        - list[Document]，符合条件的文档对象列表。
        """
        # 查询数据库中数据集ID为dataset_id且启用状态为True的文档
        documents = db.session.query(Document).filter(
            Document.dataset_id == dataset_id,
            Document.enabled == True
        ).all()

        return documents

    @staticmethod
    def get_error_documents_by_dataset_id(dataset_id: str) -> list[Document]:
        documents = db.session.query(Document).filter(
            Document.dataset_id == dataset_id,
            Document.indexing_status.in_(['error', 'paused'])
        ).all()
        return documents

    @staticmethod
    def get_batch_documents(dataset_id: str, batch: str) -> list[Document]:
        """
        从数据库中获取指定批次和数据集ID的文档列表。
        
        参数:
        - dataset_id: 数据集的唯一标识符，类型为字符串。
        - batch: 批次的标识符，用于区分不同的数据批处理，类型为字符串。
        
        返回值:
        - 返回一个文档对象列表，每个对象都是Document类的实例。
        """
        
        # 根据批次、数据集ID和当前用户所属的租户ID查询文档
        documents = db.session.query(Document).filter(
            Document.batch == batch,
            Document.dataset_id == dataset_id,
            Document.tenant_id == current_user.current_tenant_id
        ).all()

        return documents

    @staticmethod
    def get_document_file_detail(file_id: str):
        """
        获取指定文件ID的文档文件详情。

        参数:
        file_id: str - 需要查询的文件的ID。

        返回值:
        返回查询到的文件详情对象，如果不存在则返回None。
        """
        # 从数据库中查询指定ID的文件详情
        file_detail = db.session.query(UploadFile). \
            filter(UploadFile.id == file_id). \
            one_or_none()
        return file_detail

    @staticmethod
    def check_archived(document):
        """
        检查文档是否已归档
        
        参数:
        - document: 一个包含 archived 属性的对象，该属性表示文档是否已归档。
        
        返回值:
        - 返回一个布尔值，True 表示文档已归档，False 表示文档未归档。
        """
        if document.archived:
            return True
        else:
            return False

    @staticmethod
    def delete_document(document):
        """
        删除文档。

        触发文档被删除的信号，然后从数据库中删除该文档，并提交数据库会话。

        参数:
        - document: 要删除的文档对象。

        返回值:
        - 无
        """
        # 发送文档被删除的信号
        document_was_deleted.send(document.id, dataset_id=document.dataset_id, doc_form=document.doc_form)

        # 从数据库会话中删除文档并提交更改
        db.session.delete(document)
        db.session.commit()

    @staticmethod
    def rename_document(dataset_id: str, document_id: str, name: str) -> Document:
        dataset = DatasetService.get_dataset(dataset_id)
        if not dataset:
            raise ValueError('Dataset not found.')

        document = DocumentService.get_document(dataset_id, document_id)

        if not document:
            raise ValueError('Document not found.')

        if document.tenant_id != current_user.current_tenant_id:
            raise ValueError('No permission.')

        document.name = name

        db.session.add(document)
        db.session.commit()

        return document

    @staticmethod
    def pause_document(document):
        """
        暂停文档的索引过程。

        参数:
        - document: 需要被暂停索引的文档对象。

        返回值:
        - 无。

        异常:
        - DocumentIndexingError: 如果文档的索引状态不处于可暂停的状态（即不在"waiting", "parsing", "cleaning", "splitting", "indexing"之一），则抛出此异常。
        """
        # 检查文档的索引状态是否允许暂停
        if document.indexing_status not in ["waiting", "parsing", "cleaning", "splitting", "indexing"]:
            raise DocumentIndexingError()
        
        # 更新文档为暂停状态
        document.is_paused = True
        document.paused_by = current_user.id
        document.paused_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

        db.session.add(document)
        db.session.commit()  # 提交数据库事务，将暂停状态持久化
        
        # 在Redis缓存中设置文档暂停的标志
        indexing_cache_key = 'document_{}_is_paused'.format(document.id)
        redis_client.setnx(indexing_cache_key, "True")  # 使用Redis的SETNX命令确保标志只设置一次

    @staticmethod
    def recover_document(document):
        """
        恢复文档的索引过程。

        参数:
        - document: 一个文档对象，该对象必须有一个.is_paused属性用于判断文档是否暂停索引。

        返回值:
        - 无

        抛出:
        - DocumentIndexingError: 如果文档没有处于暂停状态，则抛出此错误。
        """
        if not document.is_paused:
            raise DocumentIndexingError()
        # 更新文档状态为恢复
        document.is_paused = False
        document.paused_by = None
        document.paused_at = None

        db.session.add(document)
        db.session.commit()
        # 删除暂停标志的缓存
        indexing_cache_key = 'document_{}_is_paused'.format(document.id)
        redis_client.delete(indexing_cache_key)
        # 触发异步任务以恢复文档索引
        recover_document_indexing_task.delay(document.dataset_id, document.id)

    @staticmethod
    def retry_document(dataset_id: str, documents: list[Document]):
        for document in documents:
            # retry document indexing
            document.indexing_status = 'waiting'
            db.session.add(document)
            db.session.commit()
            # add retry flag
            retry_indexing_cache_key = 'document_{}_is_retried'.format(document.id)
            redis_client.setex(retry_indexing_cache_key, 600, 1)
        # trigger async task
        document_ids = [document.id for document in documents]
        retry_document_indexing_task.delay(dataset_id, document_ids)

    @staticmethod
    def get_documents_position(dataset_id):
        """
        获取给定数据集ID的第一个文档的位置。

        参数:
        - dataset_id: 数据集的唯一标识符。

        返回值:
        - 如果找到相关文档，则返回文档的位置（从1开始计数）；
        - 如果未找到相关文档，则返回1。
        """
        # 查询数据集ID对应的文档，并按位置降序排序，获取第一个文档
        document = Document.query.filter_by(dataset_id=dataset_id).order_by(Document.position.desc()).first()
        if document:
            # 如果找到文档，返回其位置加1
            return document.position + 1
        else:
            # 如果未找到文档，返回1
            return 1

    @staticmethod
    def save_document_with_dataset_id(dataset: Dataset, document_data: dict,
                                    account: Account, dataset_process_rule: Optional[DatasetProcessRule] = None,
                                    created_from: str = 'web'):
        """
        根据给定的数据集和文档数据，在数据库中保存或更新文档，并关联数据集ID。
        
        :param dataset: 数据集对象，需要保存或更新文档的数据集。
        :param document_data: 文档数据字典，包含文档的各种信息如来源、格式等。
        :param account: 账户对象，执行操作的账户。
        :param dataset_process_rule: 数据集处理规则对象，可选，用于指定文档处理规则。
        :param created_from: 文档创建来源，默认为'web'。
        :return: 包含保存或更新的文档信息的列表，以及批次ID。
        """

        # 检查文档上传限制
        features = FeatureService.get_features(current_user.current_tenant_id)
        if features.billing.enabled:
            # 如果文档数据中不包含原始文档ID，或原始文档ID为空，则进行上传限制检查
            if 'original_document_id' not in document_data or not document_data['original_document_id']:
                count = 0
                # 根据文档来源类型计算文档数量
                if document_data["data_source"]["type"] == "upload_file":
                    upload_file_list = document_data["data_source"]["info_list"]['file_info_list']['file_ids']
                    count = len(upload_file_list)
                elif document_data["data_source"]["type"] == "notion_import":
                    notion_info_list = document_data["data_source"]['info_list']['notion_info_list']
                    for notion_info in notion_info_list:
                        count = count + len(notion_info['pages'])
                batch_upload_limit = int(current_app.config['BATCH_UPLOAD_LIMIT'])
                # 如果文档数量超过批量上传限制，则抛出异常
                if count > batch_upload_limit:
                    raise ValueError(f"You have reached the batch upload limit of {batch_upload_limit}.")

                # 检查文档上传配额
                DocumentService.check_documents_upload_quota(count, features)

        # 如果数据集的数据源类型为空，则更新为文档数据中的数据源类型
        if not dataset.data_source_type:
            dataset.data_source_type = document_data["data_source"]["type"]

        # 检查并更新数据集的索引技术设置
        if not dataset.indexing_technique:
            if 'indexing_technique' not in document_data \
                    or document_data['indexing_technique'] not in Dataset.INDEXING_TECHNIQUE_LIST:
                raise ValueError("Indexing technique is required")

            dataset.indexing_technique = document_data["indexing_technique"]
            if document_data["indexing_technique"] == 'high_quality':
                # 设置高质量索引技术相关的模型和集合绑定信息
                model_manager = ModelManager()
                embedding_model = model_manager.get_default_model_instance(
                    tenant_id=current_user.current_tenant_id,
                    model_type=ModelType.TEXT_EMBEDDING
                )
                dataset.embedding_model = embedding_model.model
                dataset.embedding_model_provider = embedding_model.provider
                dataset_collection_binding = DatasetCollectionBindingService.get_dataset_collection_binding(
                    embedding_model.provider,
                    embedding_model.model
                )
                dataset.collection_binding_id = dataset_collection_binding.id
                # 设置默认的检索模型
                if not dataset.retrieval_model:
                    default_retrieval_model = {
                        'search_method': 'semantic_search',
                        'reranking_enable': False,
                        'reranking_model': {
                            'reranking_provider_name': '',
                            'reranking_model_name': ''
                        },
                        'top_k': 2,
                        'score_threshold_enabled': False
                    }

                    dataset.retrieval_model = document_data.get('retrieval_model') if document_data.get(
                        'retrieval_model') else default_retrieval_model

        documents = []
        batch = time.strftime('%Y%m%d%H%M%S') + str(random.randint(100000, 999999))
        if document_data.get("original_document_id"):
            document = DocumentService.update_document_with_dataset_id(dataset, document_data, account)
            documents.append(document)
        else:
            # 保存或更新数据集处理规则
            if not dataset_process_rule:
                process_rule = document_data["process_rule"]
                if process_rule["mode"] == "custom":
                    dataset_process_rule = DatasetProcessRule(
                        dataset_id=dataset.id,
                        mode=process_rule["mode"],
                        rules=json.dumps(process_rule["rules"]),
                        created_by=account.id
                    )
                elif process_rule["mode"] == "automatic":
                    dataset_process_rule = DatasetProcessRule(
                        dataset_id=dataset.id,
                        mode=process_rule["mode"],
                        rules=json.dumps(DatasetProcessRule.AUTOMATIC_RULES),
                        created_by=account.id
                    )
                db.session.add(dataset_process_rule)
                db.session.commit()

            # 根据数据源类型保存文档
            position = DocumentService.get_documents_position(dataset.id)
            document_ids = []
            duplicate_document_ids = []
            if document_data["data_source"]["type"] == "upload_file":
                upload_file_list = document_data["data_source"]["info_list"]['file_info_list']['file_ids']
                for file_id in upload_file_list:
                    # 为每个上传的文件创建文档
                    file = db.session.query(UploadFile).filter(
                        UploadFile.tenant_id == dataset.tenant_id,
                        UploadFile.id == file_id
                    ).first()

                    if not file:
                        raise FileNotExistsError()

                    file_name = file.name
                    data_source_info = {
                        "upload_file_id": file_id,
                    }
                    # check duplicate
                    if document_data.get('duplicate', False):
                        document = Document.query.filter_by(
                            dataset_id=dataset.id,
                            tenant_id=current_user.current_tenant_id,
                            data_source_type='upload_file',
                            enabled=True,
                            name=file_name
                        ).first()
                        if document:
                            document.dataset_process_rule_id = dataset_process_rule.id
                            document.updated_at = datetime.datetime.utcnow()
                            document.created_from = created_from
                            document.doc_form = document_data['doc_form']
                            document.doc_language = document_data['doc_language']
                            document.data_source_info = json.dumps(data_source_info)
                            document.batch = batch
                            document.indexing_status = 'waiting'
                            db.session.add(document)
                            documents.append(document)
                            duplicate_document_ids.append(document.id)
                            continue
                    document = DocumentService.build_document(dataset, dataset_process_rule.id,
                                                            document_data["data_source"]["type"],
                                                            document_data["doc_form"],
                                                            document_data["doc_language"],
                                                            data_source_info, created_from, position,
                                                            account, file_name, batch)
                    db.session.add(document)
                    db.session.flush()
                    document_ids.append(document.id)
                    documents.append(document)
                    position += 1
            elif document_data["data_source"]["type"] == "notion_import":
                # 处理Notion导入的文档
                notion_info_list = document_data["data_source"]['info_list']['notion_info_list']
                exist_page_ids = []
                exist_document = dict()
                documents = Document.query.filter_by(
                    dataset_id=dataset.id,
                    tenant_id=current_user.current_tenant_id,
                    data_source_type='notion_import',
                    enabled=True
                ).all()
                if documents:
                    for document in documents:
                        data_source_info = json.loads(document.data_source_info)
                        exist_page_ids.append(data_source_info['notion_page_id'])
                        exist_document[data_source_info['notion_page_id']] = document.id
                for notion_info in notion_info_list:
                    workspace_id = notion_info['workspace_id']
                    data_source_binding = DataSourceBinding.query.filter(
                        db.and_(
                            DataSourceBinding.tenant_id == current_user.current_tenant_id,
                            DataSourceBinding.provider == 'notion',
                            DataSourceBinding.disabled == False,
                            DataSourceBinding.source_info['workspace_id'] == f'"{workspace_id}"'
                        )
                    ).first()
                    if not data_source_binding:
                        raise ValueError('Data source binding not found.')
                    for page in notion_info['pages']:
                        if page['page_id'] not in exist_page_ids:
                            # 为Notion新页面创建文档
                            data_source_info = {
                                "notion_workspace_id": workspace_id,
                                "notion_page_id": page['page_id'],
                                "notion_page_icon": page['page_icon'],
                                "type": page['type']
                            }
                            document = DocumentService.build_document(dataset, dataset_process_rule.id,
                                                                    document_data["data_source"]["type"],
                                                                    document_data["doc_form"],
                                                                    document_data["doc_language"],
                                                                    data_source_info, created_from, position,
                                                                    account, page['page_name'], batch)
                            db.session.add(document)
                            db.session.flush()
                            document_ids.append(document.id)
                            documents.append(document)
                            position += 1
                        else:
                            exist_document.pop(page['page_id'])
                    # 删除未选择的文档
                    if len(exist_document) > 0:
                        clean_notion_document_task.delay(list(exist_document.values()), dataset.id)
                db.session.commit()

            # trigger async task
            if document_ids:
                document_indexing_task.delay(dataset.id, document_ids)
            if duplicate_document_ids:
                duplicate_document_indexing_task.delay(dataset.id, duplicate_document_ids)

        return documents, batch

    @staticmethod
    def check_documents_upload_quota(count: int, features: FeatureModel):
        """
        检查剩余文档上传配额。
        
        参数:
        count: int - 需要上传的文档数量。
        features: FeatureModel - 包含用户订阅功能信息的对象。
        
        返回值:
        无返回值。但如果上传文档的数量超过订阅配额允许的剩余数量，将抛出 ValueError 异常。
        """
        # 计算还可以上传的文档大小
        can_upload_size = features.documents_upload_quota.limit - features.documents_upload_quota.size
        # 如果尝试上传的文档数量超过剩余配额，抛出异常
        if count > can_upload_size:
            raise ValueError(
                f'You have reached the limit of your subscription. Only {can_upload_size} documents can be uploaded.')

    @staticmethod
    def build_document(dataset: Dataset, process_rule_id: str, data_source_type: str, document_form: str,
                    document_language: str, data_source_info: dict, created_from: str, position: int,
                    account: Account,
                    name: str, batch: str):
        """
        构建文档对象。

        参数:
        - dataset: 数据集对象，包含数据集的元数据。
        - process_rule_id: 数据处理规则ID。
        - data_source_type: 数据源类型。
        - document_form: 文档形式。
        - document_language: 文档语言。
        - data_source_info: 数据源信息字典。
        - created_from: 文档创建来源。
        - position: 文档在数据集中的位置。
        - account: 账户对象，标识创建文档的用户。
        - name: 文档名称。
        - batch: 批次号。

        返回值:
        - 构建好的文档对象。
        """
        # 创建Document实例并设置属性
        document = Document(
            tenant_id=dataset.tenant_id,
            dataset_id=dataset.id,
            position=position,
            data_source_type=data_source_type,
            data_source_info=json.dumps(data_source_info),  # 将数据源信息转换为JSON字符串
            dataset_process_rule_id=process_rule_id,
            batch=batch,
            name=name,
            created_from=created_from,
            created_by=account.id,  # 记录创建者ID
            doc_form=document_form,
            doc_language=document_language
        )
        return document

    @staticmethod
    def get_tenant_documents_count():
        """
        获取当前租户未归档、启用且已完成的文档数量。
        
        参数:
        无
        
        返回值:
        documents_count (int): 符合条件的文档数量。
        """
        # 查询条件：完成时间不为空、启用状态为True、归档状态为False、租户ID与当前用户所属租户ID匹配
        documents_count = Document.query.filter(Document.completed_at.isnot(None),
                                                Document.enabled == True,
                                                Document.archived == False,
                                                Document.tenant_id == current_user.current_tenant_id).count()
        return documents_count

    @staticmethod
    def update_document_with_dataset_id(dataset: Dataset, document_data: dict,
                                            account: Account, dataset_process_rule: Optional[DatasetProcessRule] = None,
                                            created_from: str = 'web'):
        """
        使用给定的数据集ID更新文档信息。
        
        :param dataset: 数据集对象，用于确定要更新的文档所属的数据集。
        :param document_data: 包含文档更新信息的字典，如文档名称、处理规则和数据源等。
        :param account: 执行更新操作的账户对象。
        :param dataset_process_rule: 数据集处理规则对象，可选，用于更新文档的处理规则。
        :param created_from: 文档创建来源，默认为'web'。
        :return: 更新后的文档对象。
        """
        # 检查数据集的模型设置是否正确
        DatasetService.check_dataset_model_setting(dataset)
        # 根据原始文档ID获取文档对象
        document = DocumentService.get_document(dataset.id, document_data["original_document_id"])
        # 如果文档不可用，则抛出异常
        if document.display_status != 'available':
            raise ValueError("Document is not available")
        # update document name
        if document_data.get('name'):
            document.name = document_data['name']
        # save process rule
        if document_data.get('process_rule'):
            process_rule = document_data["process_rule"]
            # 根据规则模式创建或更新数据集处理规则
            if process_rule["mode"] == "custom":
                dataset_process_rule = DatasetProcessRule(
                    dataset_id=dataset.id,
                    mode=process_rule["mode"],
                    rules=json.dumps(process_rule["rules"]),
                    created_by=account.id
                )
            elif process_rule["mode"] == "automatic":
                dataset_process_rule = DatasetProcessRule(
                    dataset_id=dataset.id,
                    mode=process_rule["mode"],
                    rules=json.dumps(DatasetProcessRule.AUTOMATIC_RULES),
                    created_by=account.id
                )
            # 添加处理规则到数据库并提交更改
            db.session.add(dataset_process_rule)
            db.session.commit()
            document.dataset_process_rule_id = dataset_process_rule.id
        # update document data source
        if document_data.get('data_source'):
            file_name = ''
            data_source_info = {}
            if document_data["data_source"]["type"] == "upload_file":
                # 处理上传文件类型的数据源
                upload_file_list = document_data["data_source"]["info_list"]['file_info_list']['file_ids']
                for file_id in upload_file_list:
                    file = db.session.query(UploadFile).filter(
                        UploadFile.tenant_id == dataset.tenant_id,
                        UploadFile.id == file_id
                    ).first()
                    
                    # 如果找不到文件，则抛出异常
                    if not file:
                        raise FileNotExistsError()

                    file_name = file.name
                    data_source_info = {
                        "upload_file_id": file_id,
                    }
            elif document_data["data_source"]["type"] == "notion_import":
                # 处理Notion导入类型的数据源
                notion_info_list = document_data["data_source"]['info_list']['notion_info_list']
                for notion_info in notion_info_list:
                    workspace_id = notion_info['workspace_id']
                    data_source_binding = DataSourceBinding.query.filter(
                        db.and_(
                            DataSourceBinding.tenant_id == current_user.current_tenant_id,
                            DataSourceBinding.provider == 'notion',
                            DataSourceBinding.disabled == False,
                            DataSourceBinding.source_info['workspace_id'] == f'"{workspace_id}"'
                        )
                    ).first()
                    if not data_source_binding:
                        raise ValueError('Data source binding not found.')
                    for page in notion_info['pages']:
                        data_source_info = {
                            "notion_workspace_id": workspace_id,
                            "notion_page_id": page['page_id'],
                            "notion_page_icon": page['page_icon'],
                            "type": page['type']
                        }
            # 更新文档的数据源类型和信息
            document.data_source_type = document_data["data_source"]["type"]
            document.data_source_info = json.dumps(data_source_info)
            document.name = file_name
        
        # 更新文档状态为等待索引，并清除之前的处理状态
        document.indexing_status = 'waiting'
        document.completed_at = None
        document.processing_started_at = None
        document.parsing_completed_at = None
        document.cleaning_completed_at = None
        document.splitting_completed_at = None
        document.updated_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        document.created_from = created_from
        document.doc_form = document_data['doc_form']
        # 将更新后的文档对象添加到数据库并提交更改
        db.session.add(document)
        db.session.commit()
        
        # 更新文档段落状态为重新分段，准备进行异步任务处理
        update_params = {
            DocumentSegment.status: 're_segment'
        }
        DocumentSegment.query.filter_by(document_id=document.id).update(update_params)
        db.session.commit()
        # trigger async task
        document_indexing_update_task.delay(document.dataset_id, document.id)
        return document

    @staticmethod
    def save_document_without_dataset_id(tenant_id: str, document_data: dict, account: Account):
        """
        保存文档，但不基于特定的dataset_id。
        
        参数:
        - tenant_id: 租户ID，字符串类型，用于标识文档所属的租户。
        - document_data: 包含文档数据的字典，需要包括数据源类型和相关信息。
        - account: Account实例，标识进行文档保存操作的账户信息。
        
        返回值:
        - dataset: 保存后的数据集对象。
        - documents: 保存后的文档列表。
        - batch: 是否批量保存的标识。
        """

        # 获取当前租户的功能设置
        features = FeatureService.get_features(current_user.current_tenant_id)

        # 检查是否启用了计费功能，并对文档数据源类型进行校验和计数，以判断是否超过批量上传限制
        if features.billing.enabled:
            count = 0
            if document_data["data_source"]["type"] == "upload_file":
                upload_file_list = document_data["data_source"]["info_list"]['file_info_list']['file_ids']
                count = len(upload_file_list)
            elif document_data["data_source"]["type"] == "notion_import":
                notion_info_list = document_data["data_source"]['info_list']['notion_info_list']
                for notion_info in notion_info_list:
                    count = count + len(notion_info['pages'])
            batch_upload_limit = int(current_app.config['BATCH_UPLOAD_LIMIT'])
            if count > batch_upload_limit:
                raise ValueError(f"You have reached the batch upload limit of {batch_upload_limit}.")

            # 检查文档上传配额
            DocumentService.check_documents_upload_quota(count, features)

        # 根据文档的索引技术选择嵌入模型和检索模型
        embedding_model = None
        dataset_collection_binding_id = None
        retrieval_model = None
        if document_data['indexing_technique'] == 'high_quality':
            model_manager = ModelManager()
            embedding_model = model_manager.get_default_model_instance(
                tenant_id=current_user.current_tenant_id,
                model_type=ModelType.TEXT_EMBEDDING
            )
            dataset_collection_binding = DatasetCollectionBindingService.get_dataset_collection_binding(
                embedding_model.provider,
                embedding_model.model
            )
            dataset_collection_binding_id = dataset_collection_binding.id
            if document_data.get('retrieval_model'):
                retrieval_model = document_data['retrieval_model']
            else:
                default_retrieval_model = {
                    'search_method': 'semantic_search',
                    'reranking_enable': False,
                    'reranking_model': {
                        'reranking_provider_name': '',
                        'reranking_model_name': ''
                    },
                    'top_k': 2,
                    'score_threshold_enabled': False
                }
                retrieval_model = default_retrieval_model

        # 创建数据集对象并准备保存
        dataset = Dataset(
            tenant_id=tenant_id,
            name='',
            data_source_type=document_data["data_source"]["type"],
            indexing_technique=document_data["indexing_technique"],
            created_by=account.id,
            embedding_model=embedding_model.model if embedding_model else None,
            embedding_model_provider=embedding_model.provider if embedding_model else None,
            collection_binding_id=dataset_collection_binding_id,
            retrieval_model=retrieval_model
        )

        # 将数据集对象添加到数据库会话并刷新
        db.session.add(dataset)
        db.session.flush()

        # 保存文档，并根据文档数据和账户信息关联到数据集
        documents, batch = DocumentService.save_document_with_dataset_id(dataset, document_data, account)

        # 截断文档名称长度，更新数据集名称和描述，然后提交数据库会话
        cut_length = 18
        cut_name = documents[0].name[:cut_length]
        dataset.name = cut_name + '...'
        dataset.description = 'useful for when you want to answer queries about the ' + documents[0].name
        db.session.commit()

        return dataset, documents, batch

    @classmethod
    def document_create_args_validate(cls, args: dict):
        """
        验证创建文档时传入参数的有效性。
        
        参数:
        - cls: 类的引用，用于可能的类方法调用。
        - args: 一个字典，包含创建文档时传入的各种参数。
        
        无返回值，但会在参数不合法时抛出异常。
        """
        # 当原始文档ID不存在或为空时，必须验证数据源和处理规则参数
        if 'original_document_id' not in args or not args['original_document_id']:
            DocumentService.data_source_args_validate(args)  # 验证数据源参数
            DocumentService.process_rule_args_validate(args)  # 验证处理规则参数
        else:
            # 原始文档ID存在时，需判断是否提供了数据源或处理规则
            if ('data_source' not in args and not args['data_source']) \
                    and ('process_rule' not in args and not args['process_rule']):
                raise ValueError("Data source or Process rule is required")  # 必须提供数据源或处理规则
            else:
                if args.get('data_source'):
                    DocumentService.data_source_args_validate(args)
                if args.get('process_rule'):
                    DocumentService.process_rule_args_validate(args)

    @classmethod
    def data_source_args_validate(cls, args: dict):
        """
        验证数据源参数的有效性。

        参数:
        - cls: 类的引用，用于可能的类方法调用，但在此函数中未使用。
        - args: 一个字典，包含需要验证的数据源相关参数。

        抛出:
        - ValueError: 如果数据源、数据源类型、数据源信息或具体的数据源详情（根据数据源类型）缺失或无效，则抛出此异常。
        """

        # 验证数据源是否存在且不为空
        if 'data_source' not in args or not args['data_source']:
            raise ValueError("Data source is required")

        # 验证数据源是否为字典类型
        if not isinstance(args['data_source'], dict):
            raise ValueError("Data source is invalid")

        # 验证数据源类型是否存在且不为空
        if 'type' not in args['data_source'] or not args['data_source']['type']:
            raise ValueError("Data source type is required")

        # 验证数据源类型是否有效
        if args['data_source']['type'] not in Document.DATA_SOURCES:
            raise ValueError("Data source type is invalid")

        # 验证数据源信息是否存在且不为空
        if 'info_list' not in args['data_source'] or not args['data_source']['info_list']:
            raise ValueError("Data source info is required")

        # 根据不同的数据源类型，验证相应的详细信息项
        if args['data_source']['type'] == 'upload_file':
            # 验证文件数据源的详细信息是否存在且不为空
            if 'file_info_list' not in args['data_source']['info_list'] or not args['data_source']['info_list'][
                'file_info_list']:
                raise ValueError("File source info is required")
        if args['data_source']['type'] == 'notion_import':
            # 验证Notion数据源的详细信息是否存在且不为空
            if 'notion_info_list' not in args['data_source']['info_list'] or not args['data_source']['info_list'][
                'notion_info_list']:
                raise ValueError("Notion source info is required")

    @classmethod
    def process_rule_args_validate(cls, args: dict):
        """
        验证处理规则参数的合法性。

        参数:
        - cls: 通常表示类的当前实例，这里未使用，可能用于扩展或钩子。
        - args: 一个字典，包含要验证的处理规则参数。

        抛出:
        - ValueError: 当缺少必需的参数、参数类型不正确、参数值非法时抛出。
        """

        # 检查是否提供了处理规则，并确保其不为空
        if 'process_rule' not in args or not args['process_rule']:
            raise ValueError("Process rule is required")

        # 确保处理规则是字典类型
        if not isinstance(args['process_rule'], dict):
            raise ValueError("Process rule is invalid")

        # 检查处理规则模式是否提供且合法
        if 'mode' not in args['process_rule'] or not args['process_rule']['mode']:
            raise ValueError("Process rule mode is required")

        if args['process_rule']['mode'] not in DatasetProcessRule.MODES:
            raise ValueError("Process rule mode is invalid")

        # 当模式为'automatic'时，初始化规则为空字典
        if args['process_rule']['mode'] == 'automatic':
            args['process_rule']['rules'] = {}
        else:
            # 检查规则详情是否提供且不为空，并确保其是字典类型
            if 'rules' not in args['process_rule'] or not args['process_rule']['rules']:
                raise ValueError("Process rule rules is required")

            if not isinstance(args['process_rule']['rules'], dict):
                raise ValueError("Process rule rules is invalid")

            # 检查预处理规则是否提供且合法
            if 'pre_processing_rules' not in args['process_rule']['rules'] \
                    or args['process_rule']['rules']['pre_processing_rules'] is None:
                raise ValueError("Process rule pre_processing_rules is required")

            if not isinstance(args['process_rule']['rules']['pre_processing_rules'], list):
                raise ValueError("Process rule pre_processing_rules is invalid")

            # 验证预处理规则的每个条目，并去重
            unique_pre_processing_rule_dicts = {}
            for pre_processing_rule in args['process_rule']['rules']['pre_processing_rules']:
                if 'id' not in pre_processing_rule or not pre_processing_rule['id']:
                    raise ValueError("Process rule pre_processing_rules id is required")

                if pre_processing_rule['id'] not in DatasetProcessRule.PRE_PROCESSING_RULES:
                    raise ValueError("Process rule pre_processing_rules id is invalid")

                if 'enabled' not in pre_processing_rule or pre_processing_rule['enabled'] is None:
                    raise ValueError("Process rule pre_processing_rules enabled is required")

                if not isinstance(pre_processing_rule['enabled'], bool):
                    raise ValueError("Process rule pre_processing_rules enabled is invalid")

                unique_pre_processing_rule_dicts[pre_processing_rule['id']] = pre_processing_rule

            args['process_rule']['rules']['pre_processing_rules'] = list(unique_pre_processing_rule_dicts.values())

            # 检查分割规则的合法性
            if 'segmentation' not in args['process_rule']['rules'] \
                    or args['process_rule']['rules']['segmentation'] is None:
                raise ValueError("Process rule segmentation is required")

            if not isinstance(args['process_rule']['rules']['segmentation'], dict):
                raise ValueError("Process rule segmentation is invalid")

            # 确保分割规则中的分隔符和最大令牌数是必须的，且类型正确
            if 'separator' not in args['process_rule']['rules']['segmentation'] \
                    or not args['process_rule']['rules']['segmentation']['separator']:
                raise ValueError("Process rule segmentation separator is required")

            if not isinstance(args['process_rule']['rules']['segmentation']['separator'], str):
                raise ValueError("Process rule segmentation separator is invalid")

            if 'max_tokens' not in args['process_rule']['rules']['segmentation'] \
                    or not args['process_rule']['rules']['segmentation']['max_tokens']:
                raise ValueError("Process rule segmentation max_tokens is required")

            if not isinstance(args['process_rule']['rules']['segmentation']['max_tokens'], int):
                raise ValueError("Process rule segmentation max_tokens is invalid")

    @classmethod
    def estimate_args_validate(cls, args: dict):
        """
        验证估计参数的合法性。

        参数:
        - cls: 类的引用，用于可能的类方法调用，但在此函数中未使用。
        - args: 一个字典，包含需要验证的参数信息。

        验证参数结构和类型，确保所有必需的字段都存在且符合预期的格式。特别地，此函数验证以下部分：
        - 'info_list' 字段必须存在且不为空，且必须是字典类型。
        - 'process_rule' 字段必须存在且不为空，且必须是字典类型。
        - 'process_rule' 中的 'mode' 字段必须存在且不为空，且必须是预定义的有效模式之一。
        - 如果 'mode' 为 'automatic'，则 'rules' 字段默认为空字典。
        - 如果 'mode' 不为 'automatic'，则 'rules' 字段必须存在且不为空，且必须是字典类型。
        - 'rules' 中的 'pre_processing_rules' 字段必须存在，且必须是列表类型，每个元素是字典类型，并满足特定的结构和类型要求。
        - 'rules' 中的 'segmentation' 字段必须存在且不为空，且必须是字典类型，满足特定的结构和类型要求。

        抛出:
        - ValueError: 当验证失败时，抛出具体的错误信息。
        """
        
        # 确保数据源信息存在且不为空
        if 'info_list' not in args or not args['info_list']:
            raise ValueError("Data source info is required")

        # 确保数据信息是字典类型
        if not isinstance(args['info_list'], dict):
            raise ValueError("Data info is invalid")

        # 确保处理规则存在且不为空
        if 'process_rule' not in args or not args['process_rule']:
            raise ValueError("Process rule is required")

        # 确保处理规则是字典类型
        if not isinstance(args['process_rule'], dict):
            raise ValueError("Process rule is invalid")

        # 确保处理规则中的模式存在且不为空
        if 'mode' not in args['process_rule'] or not args['process_rule']['mode']:
            raise ValueError("Process rule mode is required")

        # 确保处理规则的模式是有效的
        if args['process_rule']['mode'] not in DatasetProcessRule.MODES:
            raise ValueError("Process rule mode is invalid")

        # 如果模式为'automatic'，则将'rules'设置为空字典
        if args['process_rule']['mode'] == 'automatic':
            args['process_rule']['rules'] = {}
        else:
            # 确保'rules'存在且不为空，且是字典类型
            if 'rules' not in args['process_rule'] or not args['process_rule']['rules']:
                raise ValueError("Process rule rules is required")

            if not isinstance(args['process_rule']['rules'], dict):
                raise ValueError("Process rule rules is invalid")

            # 确保预处理规则存在，且是列表类型
            if 'pre_processing_rules' not in args['process_rule']['rules'] \
                    or args['process_rule']['rules']['pre_processing_rules'] is None:
                raise ValueError("Process rule pre_processing_rules is required")

            if not isinstance(args['process_rule']['rules']['pre_processing_rules'], list):
                raise ValueError("Process rule pre_processing_rules is invalid")

            # 验证预处理规则的每个条目
            unique_pre_processing_rule_dicts = {}
            for pre_processing_rule in args['process_rule']['rules']['pre_processing_rules']:
                if 'id' not in pre_processing_rule or not pre_processing_rule['id']:
                    raise ValueError("Process rule pre_processing_rules id is required")

                if pre_processing_rule['id'] not in DatasetProcessRule.PRE_PROCESSING_RULES:
                    raise ValueError("Process rule pre_processing_rules id is invalid")

                if 'enabled' not in pre_processing_rule or pre_processing_rule['enabled'] is None:
                    raise ValueError("Process rule pre_processing_rules enabled is required")

                if not isinstance(pre_processing_rule['enabled'], bool):
                    raise ValueError("Process rule pre_processing_rules enabled is invalid")

                unique_pre_processing_rule_dicts[pre_processing_rule['id']] = pre_processing_rule

            # 重置预处理规则为去重后的列表
            args['process_rule']['rules']['pre_processing_rules'] = list(unique_pre_processing_rule_dicts.values())

            # 确保分割规则存在，且满足结构和类型要求
            if 'segmentation' not in args['process_rule']['rules'] \
                    or args['process_rule']['rules']['segmentation'] is None:
                raise ValueError("Process rule segmentation is required")

            if not isinstance(args['process_rule']['rules']['segmentation'], dict):
                raise ValueError("Process rule segmentation is invalid")

            if 'separator' not in args['process_rule']['rules']['segmentation'] \
                    or not args['process_rule']['rules']['segmentation']['separator']:
                raise ValueError("Process rule segmentation separator is required")

            if not isinstance(args['process_rule']['rules']['segmentation']['separator'], str):
                raise ValueError("Process rule segmentation separator is invalid")

            if 'max_tokens' not in args['process_rule']['rules']['segmentation'] \
                    or not args['process_rule']['rules']['segmentation']['max_tokens']:
                raise ValueError("Process rule segmentation max_tokens is required")

            if not isinstance(args['process_rule']['rules']['segmentation']['max_tokens'], int):
                raise ValueError("Process rule segmentation max_tokens is invalid")


class SegmentService:
    @classmethod
    def segment_create_args_validate(cls, args: dict, document: Document):
        """
        验证创建文档段落的参数有效性。

        参数:
        - cls: 类的引用，用于可能的类方法调用，但在此函数中未使用。
        - args: 一个字典，包含需要验证的参数。必须包含'answer'和'content'键。
        - document: Document对象，包含文档信息，用于判断文档类型。

        返回值:
        - 无返回值，但会抛出ValueError异常如果验证失败。
        """
        # 针对问答模型类型的文档，验证'answer'参数
        if document.doc_form == 'qa_model':
            # 如果'answer'键不存在或其值为空，则抛出异常
            if 'answer' not in args or not args['answer']:
                raise ValueError("Answer is required")
            # 如果'answer'值经过空白字符处理后仍为空，则抛出异常
            if not args['answer'].strip():
                raise ValueError("Answer is empty")
        # 验证'content'参数，确保其非空
        if 'content' not in args or not args['content'] or not args['content'].strip():
            raise ValueError("Content is empty")

    @classmethod
    def create_segment(cls, args: dict, document: Document, dataset: Dataset):
        """
        创建一个文档段（segment）。

        参数:
        - cls: 类的引用。
        - args: 包含创建文档段所需信息的字典，预期包含 'content' 和可选的 'answer' 键。
        - document: 文档对象，表示正在处理的文档。
        - dataset: 数据集对象，指定文档所属的数据集。

        返回:
        - 创建的文档段对象。
        """

        # 初始化基本文档段信息
        content = args['content']
        doc_id = str(uuid.uuid4())
        segment_hash = helper.generate_text_hash(content)
        tokens = 0

        # 如果数据集使用高质索引技术，则计算文本嵌入所需的tokens
        if dataset.indexing_technique == 'high_quality':
            # 获取嵌入模型实例
            model_manager = ModelManager()
            embedding_model = model_manager.get_model_instance(
                tenant_id=current_user.current_tenant_id,
                provider=dataset.embedding_model_provider,
                model_type=ModelType.TEXT_EMBEDDING,
                model=dataset.embedding_model
            )
            # calc embedding use tokens
            tokens = embedding_model.get_text_embedding_num_tokens(
                texts=[content]
            )
        lock_name = 'add_segment_lock_document_id_{}'.format(document.id)
        with redis_client.lock(lock_name, timeout=600):
            max_position = db.session.query(func.max(DocumentSegment.position)).filter(
                DocumentSegment.document_id == document.id
            ).scalar()
            segment_document = DocumentSegment(
                tenant_id=current_user.current_tenant_id,
                dataset_id=document.dataset_id,
                document_id=document.id,
                index_node_id=doc_id,
                index_node_hash=segment_hash,
                position=max_position + 1 if max_position else 1,
                content=content,
                word_count=len(content),
                tokens=tokens,
                status='completed',
                indexing_at=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),
                completed_at=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),
                created_by=current_user.id
            )
            if document.doc_form == 'qa_model':
                segment_document.answer = args['answer']

            db.session.add(segment_document)
            db.session.commit()

            # save vector index
            try:
                VectorService.create_segments_vector([args['keywords']], [segment_document], dataset)
            except Exception as e:
                logging.exception("create segment index failed")
                segment_document.enabled = False
                segment_document.disabled_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                segment_document.status = 'error'
                segment_document.error = str(e)
                db.session.commit()
            segment = db.session.query(DocumentSegment).filter(DocumentSegment.id == segment_document.id).first()
            return segment

    @classmethod
    def multi_create_segment(cls, segments: list, document: Document, dataset: Dataset):
        lock_name = 'multi_add_segment_lock_document_id_{}'.format(document.id)
        with redis_client.lock(lock_name, timeout=600):
            embedding_model = None
            if dataset.indexing_technique == 'high_quality':
                model_manager = ModelManager()
                embedding_model = model_manager.get_model_instance(
                    tenant_id=current_user.current_tenant_id,
                    provider=dataset.embedding_model_provider,
                    model_type=ModelType.TEXT_EMBEDDING,
                    model=dataset.embedding_model
                )
            max_position = db.session.query(func.max(DocumentSegment.position)).filter(
                DocumentSegment.document_id == document.id
            ).scalar()
            pre_segment_data_list = []
            segment_data_list = []
            keywords_list = []
            for segment_item in segments:
                content = segment_item['content']
                doc_id = str(uuid.uuid4())
                segment_hash = helper.generate_text_hash(content)
                tokens = 0
                if dataset.indexing_technique == 'high_quality' and embedding_model:
                    # calc embedding use tokens
                    tokens = embedding_model.get_text_embedding_num_tokens(
                        texts=[content]
                    )
                segment_document = DocumentSegment(
                    tenant_id=current_user.current_tenant_id,
                    dataset_id=document.dataset_id,
                    document_id=document.id,
                    index_node_id=doc_id,
                    index_node_hash=segment_hash,
                    position=max_position + 1 if max_position else 1,
                    content=content,
                    word_count=len(content),
                    tokens=tokens,
                    status='completed',
                    indexing_at=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),
                    completed_at=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),
                    created_by=current_user.id
                )
                if document.doc_form == 'qa_model':
                    segment_document.answer = segment_item['answer']
                db.session.add(segment_document)
                segment_data_list.append(segment_document)

                pre_segment_data_list.append(segment_document)
                keywords_list.append(segment_item['keywords'])

            try:
                # save vector index
                VectorService.create_segments_vector(keywords_list, pre_segment_data_list, dataset)
            except Exception as e:
                logging.exception("create segment index failed")
                for segment_document in segment_data_list:
                    segment_document.enabled = False
                    segment_document.disabled_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                    segment_document.status = 'error'
                    segment_document.error = str(e)
            db.session.commit()
            return segment_data_list

    @classmethod
    def update_segment(cls, args: dict, segment: DocumentSegment, document: Document, dataset: Dataset):
        """
        更新文档段落信息。

        参数:
        - cls: 类的引用
        - args: 包含更新内容的字典
        - segment: 需要更新的文档段落对象
        - document: 对应的文档对象
        - dataset: 对应的数据集对象

        返回值:
        - 更新后的文档段落对象
        """

        # 检查段落是否正在索引中
        indexing_cache_key = 'segment_{}_indexing'.format(segment.id)
        cache_result = redis_client.get(indexing_cache_key)
        if cache_result is not None:
            raise ValueError("Segment is indexing, please try again later")
        if 'enabled' in args and args['enabled'] is not None:
            action = args['enabled']
            if segment.enabled != action:
                if not action:
                    segment.enabled = action
                    segment.disabled_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                    segment.disabled_by = current_user.id
                    db.session.add(segment)
                    db.session.commit()
                    # Set cache to prevent indexing the same segment multiple times
                    redis_client.setex(indexing_cache_key, 600, 1)
                    disable_segment_from_index_task.delay(segment.id)
                    return segment
        if not segment.enabled:
            if 'enabled' in args and args['enabled'] is not None:
                if not args['enabled']:
                    raise ValueError("Can't update disabled segment")
            else:
                raise ValueError("Can't update disabled segment")
        try:
            content = args['content']

            # 如果内容未改变，则更新部分字段
            if segment.content == content:
                # 更新QA模型的答案
                if document.doc_form == 'qa_model':
                    segment.answer = args['answer']
                if args.get('keywords'):
                    segment.keywords = args['keywords']
                segment.enabled = True
                segment.disabled_at = None
                segment.disabled_by = None
                db.session.add(segment)
                db.session.commit()

                # 如果有关键词，则更新段落索引
                if args['keywords']:
                    keyword = Keyword(dataset)
                    keyword.delete_by_ids([segment.index_node_id])
                    document = RAGDocument(
                        page_content=segment.content,
                        metadata={
                            "doc_id": segment.index_node_id,
                            "doc_hash": segment.index_node_hash,
                            "document_id": segment.document_id,
                            "dataset_id": segment.dataset_id,
                        }
                    )
                    keyword.add_texts([document], keywords_list=[args['keywords']])
            else:
                # 如果内容已改变，则全面更新段落信息
                segment_hash = helper.generate_text_hash(content)
                tokens = 0

                # 根据索引技术选择不同的处理方式
                if dataset.indexing_technique == 'high_quality':
                    model_manager = ModelManager()
                    embedding_model = model_manager.get_model_instance(
                        tenant_id=current_user.current_tenant_id,
                        provider=dataset.embedding_model_provider,
                        model_type=ModelType.TEXT_EMBEDDING,
                        model=dataset.embedding_model
                    )

                    # calc embedding use tokens
                    tokens = embedding_model.get_text_embedding_num_tokens(
                        texts=[content]
                    )

                # 更新段落内容和相关统计信息
                segment.content = content
                segment.index_node_hash = segment_hash
                segment.word_count = len(content)
                segment.tokens = tokens
                segment.status = 'completed'
                segment.indexing_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                segment.completed_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                segment.updated_by = current_user.id
                segment.updated_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                segment.enabled = True
                segment.disabled_at = None
                segment.disabled_by = None
                if document.doc_form == 'qa_model':
                    segment.answer = args['answer']

                db.session.add(segment)
                db.session.commit()

                # 更新向量索引
                VectorService.update_segment_vector(args['keywords'], segment, dataset)

        except Exception as e:
            # 在更新过程中遇到异常则标记段落为错误状态并记录异常
            logging.exception("update segment index failed")
            segment.enabled = False
            segment.disabled_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            segment.status = 'error'
            segment.error = str(e)
            db.session.commit()
        
        # 重新从数据库获取段落对象以确保数据一致性
        segment = db.session.query(DocumentSegment).filter(DocumentSegment.id == segment.id).first()
        return segment

    @classmethod
    def delete_segment(cls, segment: DocumentSegment, document: Document, dataset: Dataset):
        indexing_cache_key = 'segment_{}_delete_indexing'.format(segment.id)
        cache_result = redis_client.get(indexing_cache_key)
        if cache_result is not None:
            raise ValueError("Segment is deleting.")

        # enabled segment need to delete index
        if segment.enabled:
            # send delete segment index task
            redis_client.setex(indexing_cache_key, 600, 1)
            delete_segment_from_index_task.delay(segment.id, segment.index_node_id, dataset.id, document.id)
        db.session.delete(segment)
        db.session.commit()


class DatasetCollectionBindingService:
    @classmethod
    def get_dataset_collection_binding(cls, provider_name: str, model_name: str,
                                        collection_type: str = 'dataset') -> DatasetCollectionBinding:
        """
        获取给定提供者名称、模型名称和集合类型的DatasetCollectionBinding对象。
        如果找不到，则创建一个新的DatasetCollectionBinding对象并将其添加到数据库。

        参数:
        - provider_name: str, 提供者的名称
        - model_name: str, 模型的名称
        - collection_type: str, 集合的类型，默认为'dataset'

        返回值:
        - DatasetCollectionBinding, 对应的DatasetCollectionBinding对象
        """
        # 尝试从数据库中查询符合条件的DatasetCollectionBinding对象
        dataset_collection_binding = db.session.query(DatasetCollectionBinding). \
            filter(DatasetCollectionBinding.provider_name == provider_name,
                DatasetCollectionBinding.model_name == model_name,
                DatasetCollectionBinding.type == collection_type). \
            order_by(DatasetCollectionBinding.created_at). \
            first()

        # 如果查询结果为空，则创建并添加一个新的DatasetCollectionBinding对象到数据库
        if not dataset_collection_binding:
            dataset_collection_binding = DatasetCollectionBinding(
                provider_name=provider_name,
                model_name=model_name,
                collection_name=Dataset.gen_collection_name_by_id(str(uuid.uuid4())),
                type=collection_type
            )
            db.session.add(dataset_collection_binding)
            db.session.commit()
        return dataset_collection_binding

    @classmethod
    def get_dataset_collection_binding_by_id_and_type(cls, collection_binding_id: str,
                                                        collection_type: str = 'dataset') -> DatasetCollectionBinding:
        """
        通过ID和类型获取数据集集合绑定对象。
        
        参数:
        - cls: 类的引用，用于调用数据库会话。
        - collection_binding_id: str，要查询的数据集集合绑定的ID。
        - collection_type: str，数据集集合的类型，默认为 'dataset'。
        
        返回值:
        - DatasetCollectionBinding对象，对应于指定ID和类型的绑定记录。
        """
        # 查询数据库，获取符合条件的数据集集合绑定对象
        dataset_collection_binding = db.session.query(DatasetCollectionBinding). \
            filter(DatasetCollectionBinding.id == collection_binding_id,
                DatasetCollectionBinding.type == collection_type). \
            order_by(DatasetCollectionBinding.created_at). \
            first()

        return dataset_collection_binding
