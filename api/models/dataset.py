import base64
import hashlib
import hmac
import json
import logging
import os
import pickle
import re
import time
from json import JSONDecodeError

from flask import current_app
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import JSONB

from extensions.ext_database import db
from extensions.ext_storage import storage
from models import StringUUID
from models.account import Account
from models.model import App, Tag, TagBinding, UploadFile


class Dataset(db.Model):
    """
    数据集模型，用于表示数据库中的数据集表。

    属性:
    - id: 数据集的唯一标识符。
    - tenant_id: 租户ID，表示该数据集属于哪个租户。
    - name: 数据集的名称。
    - description: 数据集的描述信息。
    - provider: 数据集的提供者。
    - permission: 数据集的访问权限。
    - data_source_type: 数据集的数据源类型。
    - indexing_technique: 数据集的索引技术。
    - index_struct: 索引结构的详细信息。
    - created_by: 创建该数据集的用户ID。
    - created_at: 数据集的创建时间。
    - updated_by: 最后一次更新该数据集的用户ID。
    - updated_at: 数据集的最后更新时间。
    - embedding_model: 用于嵌入的模型名称。
    - embedding_model_provider: 嵌入模型的提供者。
    - collection_binding_id: 集合绑定的ID。
    - retrieval_model: 检索模型的配置。

    方法:
    - dataset_keyword_table: 获取与数据集关联的关键词表。
    - index_struct_dict: 将索引结构转换为字典格式。
    - created_by_account: 获取创建该数据集的账户信息。
    - latest_process_rule: 获取数据集的最新处理规则。
    - app_count: 获取使用该数据集的应用数量。
    - document_count: 获取属于该数据集的文档数量。
    - available_document_count: 获取该数据集中可用的文档数量。
    - available_segment_count: 获取该数据集中可用的文档段落数量。
    - word_count: 计算该数据集的总单词数。
    - doc_form: 获取该数据集的文档格式。
    - retrieval_model_dict: 将检索模型配置转换为字典格式。
    - gen_collection_name_by_id: 根据数据集ID生成集合名称。
    """

    __tablename__ = 'datasets'  # 指定表名为datasets
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='dataset_pkey'),  # 设置主键约束
        db.Index('dataset_tenant_idx', 'tenant_id'),  # 创建tenant_id的索引
        db.Index('retrieval_model_idx', "retrieval_model", postgresql_using='gin')  # 创建检索模型的Gin索引
    )

    INDEXING_TECHNIQUE_LIST = ['high_quality', 'economy', None]

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    tenant_id = db.Column(StringUUID, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    provider = db.Column(db.String(255), nullable=False,
                         server_default=db.text("'vendor'::character varying"))
    permission = db.Column(db.String(255), nullable=False,
                           server_default=db.text("'only_me'::character varying"))
    data_source_type = db.Column(db.String(255))
    indexing_technique = db.Column(db.String(255), nullable=True)
    index_struct = db.Column(db.Text, nullable=True)
    created_by = db.Column(StringUUID, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False,
                           server_default=db.text('CURRENT_TIMESTAMP(0)'))
    updated_by = db.Column(StringUUID, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False,
                           server_default=db.text('CURRENT_TIMESTAMP(0)'))
    embedding_model = db.Column(db.String(255), nullable=True)
    embedding_model_provider = db.Column(db.String(255), nullable=True)
    collection_binding_id = db.Column(StringUUID, nullable=True)
    retrieval_model = db.Column(JSONB, nullable=True)

    @property
    def dataset_keyword_table(self):
        """
        获取与数据集关联的关键词表。

        返回:
        - 与数据集关联的关键词表对象，如果不存在则返回None。
        """
        dataset_keyword_table = db.session.query(DatasetKeywordTable).filter(
            DatasetKeywordTable.dataset_id == self.id).first()
        if dataset_keyword_table:
            return dataset_keyword_table

        return None

    @property
    def index_struct_dict(self):
        """
        将索引结构转换为字典格式。

        返回:
        - 索引结构的字典表示，如果索引结构为空则返回None。
        """
        return json.loads(self.index_struct) if self.index_struct else None

    @property
    def created_by_account(self):
        """
        获取创建该数据集的账户信息。

        返回:
        - 创建该数据集的账户对象，如果账户不存在则返回None。
        """
        return Account.query.get(self.created_by)

    @property
    def latest_process_rule(self):
        """
        获取数据集的最新处理规则。

        返回:
        - 数据集的最新处理规则对象，如果不存在则返回None。
        """
        return DatasetProcessRule.query.filter(DatasetProcessRule.dataset_id == self.id) \
            .order_by(DatasetProcessRule.created_at.desc()).first()

    @property
    def app_count(self):
        return db.session.query(func.count(AppDatasetJoin.id)).filter(AppDatasetJoin.dataset_id == self.id,
                                                                      App.id == AppDatasetJoin.app_id).scalar()

    @property
    def document_count(self):
        """
        获取属于该数据集的文档数量。

        返回:
        - 属于该数据集的文档数量。
        """
        return db.session.query(func.count(Document.id)).filter(Document.dataset_id == self.id).scalar()

    @property
    def available_document_count(self):
        """
        获取该数据集中可用的文档数量。

        返回:
        - 该数据集中可用的文档数量。
        """
        return db.session.query(func.count(Document.id)).filter(
            Document.dataset_id == self.id,
            Document.indexing_status == 'completed',
            Document.enabled == True,
            Document.archived == False
        ).scalar()

    @property
    def available_segment_count(self):
        """
        获取该数据集中可用的文档段落数量。

        返回:
        - 该数据集中可用的文档段落数量。
        """
        return db.session.query(func.count(DocumentSegment.id)).filter(
            DocumentSegment.dataset_id == self.id,
            DocumentSegment.status == 'completed',
            DocumentSegment.enabled == True
        ).scalar()

    @property
    def word_count(self):
        """
        计算该数据集的总单词数。

        返回:
        - 该数据集的总单词数。
        """
        return Document.query.with_entities(func.coalesce(func.sum(Document.word_count))) \
            .filter(Document.dataset_id == self.id).scalar()

    @property
    def doc_form(self):
        """
        获取该数据集的文档格式。

        返回:
        - 该数据集的文档格式，如果不存在则返回None。
        """
        document = db.session.query(Document).filter(
            Document.dataset_id == self.id).first()
        if document:
            return document.doc_form
        return None

    @property
    def retrieval_model_dict(self):
        """
        将检索模型配置转换为字典格式。

        返回:
        - 检索模型配置的字典表示，如果未配置则返回默认的检索模型配置。
        """
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
        return self.retrieval_model if self.retrieval_model else default_retrieval_model

    @property
    def tags(self):
        tags = db.session.query(Tag).join(
            TagBinding,
            Tag.id == TagBinding.tag_id
        ).filter(
            TagBinding.target_id == self.id,
            TagBinding.tenant_id == self.tenant_id,
            Tag.tenant_id == self.tenant_id,
            Tag.type == 'knowledge'
        ).all()

        return tags if tags else []

    @staticmethod
    def gen_collection_name_by_id(dataset_id: str) -> str:
        """
        根据数据集ID生成集合名称。

        参数:
        - dataset_id: 数据集的唯一标识符。

        返回:
        - 生成的集合名称。
        """
        normalized_dataset_id = dataset_id.replace("-", "_")
        return f'Vector_index_{normalized_dataset_id}_Node'


class DatasetProcessRule(db.Model):
    """
    数据集处理规则模型类，继承自db.Model，用于在数据库中存储数据集处理规则。

    参数:
    - db (SQLAlchemy Model Base): SQLAlchemy ORM基类

    属性:
    __tablename__: 定义数据库中的表名
    __table_args__: 定义表的约束条件，包括主键约束和索引
    id: 规则的唯一标识符，类型为UUID，不能为空，服务器端默认使用uuid_generate_v4()生成
    dataset_id: 关联的数据集ID，类型为UUID，不能为空
    mode: 数据处理模式，字符串类型，长度限制为255，不能为空，默认值为'automatic'，可选值包括['automatic', 'custom']
    rules: 数据处理的具体规则，以文本形式存储，类型为Text，可为空
    created_by: 创建该规则的用户ID，类型为UUID，不能为空
    created_at: 规则创建时间，类型为DateTime，不能为空，服务器端默认设置为当前时间

    类常量:
    MODES: 可用的处理模式列表
    PRE_PROCESSING_RULES: 预处理规则列表
    AUTOMATIC_RULES: 自动处理模式下的预设规则（包括预处理规则和分词规则）

    方法:
    to_dict(): 将数据集处理规则对象转换为字典形式，方便序列化或传输
    rules_dict: 获取已存储规则的字典表示，尝试从rules属性的JSON字符串解析得到
    """

    __tablename__ = 'dataset_process_rules'
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='dataset_process_rule_pkey'),
        db.Index('dataset_process_rule_dataset_id_idx', 'dataset_id'),
    )

    id = db.Column(StringUUID, nullable=False,
                   server_default=db.text('uuid_generate_v4()'))
    dataset_id = db.Column(StringUUID, nullable=False)
    mode = db.Column(db.String(255), nullable=False,
                     server_default=db.text("'automatic'::character varying"))
    rules = db.Column(db.Text, nullable=True)
    created_by = db.Column(StringUUID, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False,
                           server_default=db.text('CURRENT_TIMESTAMP(0)'))

    MODES = ['automatic', 'custom']
    PRE_PROCESSING_RULES = ['remove_stopwords', 'remove_extra_spaces', 'remove_urls_emails']
    AUTOMATIC_RULES = {
        'pre_processing_rules': [
            {'id': 'remove_extra_spaces', 'enabled': True},
            {'id': 'remove_urls_emails', 'enabled': False}
        ],
        'segmentation': {
            'delimiter': '\n',
            'max_tokens': 500,
            'chunk_overlap': 50
        }
    }

    def to_dict(self):
        """
        将DatasetProcessRule对象转化为字典形式。
        
        返回值:
        dict: 包含所有属性的字典，其中rules属性转化为解析后的字典。
        """
        return {
            'id': self.id,
            'dataset_id': self.dataset_id,
            'mode': self.mode,
            'rules': self.rules_dict,
            'created_by': self.created_by,
            'created_at': self.created_at,
        }

    @property
    def rules_dict(self):
        """
        获取rules属性所代表的规则字典。
        
        返回值:
        dict 或 None: 当rules属性可以被成功解析为JSON时，返回其对应的字典；否则返回None。
        """
        try:
            return json.loads(self.rules) if self.rules else None
        except JSONDecodeError:
            return None


class Document(db.Model):
    """
    文档模型，用于表示一个文档实体，包括其各种状态和属性。

    属性:
    - id: 文档的唯一标识符。
    - tenant_id: 租户的唯一标识符。
    - dataset_id: 所属数据集的唯一标识符。
    - position: 在数据集中的位置。
    - data_source_type: 数据源类型，如上传文件或Notion导入。
    - data_source_info: 有关数据源的详细信息，以JSON字符串形式存储。
    - dataset_process_rule_id: 数据处理规则的唯一标识符。
    - batch: 批次标识。
    - name: 文档的名称。
    - created_from: 创建来源。
    - created_by: 创建者的唯一标识符。
    - created_api_request_id: 创建时的API请求标识符。
    - created_at: 创建时间。
    - processing_started_at: 开始处理的时间。
    - file_id: 文件的标识符。
    - word_count: 字词数量。
    - parsing_completed_at: 解析完成的时间。
    - cleaning_completed_at: 清理完成的时间。
    - splitting_completed_at: 分割完成的时间。
    - tokens: 用于索引的令牌数量。
    - indexing_latency: 索引延迟。
    - completed_at: 完成索引的时间。
    - is_paused: 是否暂停。
    - paused_by: 暂停者的唯一标识符。
    - paused_at: 暂停的时间。
    - error: 错误信息。
    - stopped_at: 停止的时间。
    - indexing_status: 索引状态。
    - enabled: 是否启用。
    - disabled_at: 禁用的时间。
    - disabled_by: 禁用者的唯一标识符。
    - archived: 是否归档。
    - archived_reason: 归档原因。
    - archived_by: 归档者的唯一标识符。
    - archived_at: 归档的时间。
    - updated_at: 最后更新的时间。
    - doc_type: 文档类型。
    - doc_metadata: 文档元数据，以JSON格式存储。
    - doc_form: 文档形式。
    - doc_language: 文档语言。
    - DATA_SOURCES: 可能的数据源类型列表。

    方法:
    - display_status: 获取文档的显示状态。
    - data_source_info_dict: 将data_source_info转换为字典。
    - data_source_detail_dict: 获取数据源的详细信息字典。
    - average_segment_length: 计算平均段落长度。
    - dataset_process_rule: 获取数据处理规则对象。
    - dataset: 获取所属数据集对象。
    - segment_count: 获取文档段落的数量。
    - hit_count: 获取文档段落的命中次数总数。
    """
    __tablename__ = 'documents'
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='document_pkey'),
        db.Index('document_dataset_id_idx', 'dataset_id'),
        db.Index('document_is_paused_idx', 'is_paused'),
        db.Index('document_tenant_idx', 'tenant_id'),
    )

    # initial fields
    id = db.Column(StringUUID, nullable=False,
                   server_default=db.text('uuid_generate_v4()'))
    tenant_id = db.Column(StringUUID, nullable=False)
    dataset_id = db.Column(StringUUID, nullable=False)
    position = db.Column(db.Integer, nullable=False)
    data_source_type = db.Column(db.String(255), nullable=False)
    data_source_info = db.Column(db.Text, nullable=True)
    dataset_process_rule_id = db.Column(StringUUID, nullable=True)
    batch = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    created_from = db.Column(db.String(255), nullable=False)
    created_by = db.Column(StringUUID, nullable=False)
    created_api_request_id = db.Column(StringUUID, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False,
                           server_default=db.text('CURRENT_TIMESTAMP(0)'))

    # 开始处理
    processing_started_at = db.Column(db.DateTime, nullable=True)

    # 解析
    file_id = db.Column(db.Text, nullable=True)
    word_count = db.Column(db.Integer, nullable=True)
    parsing_completed_at = db.Column(db.DateTime, nullable=True)

    # 清理
    cleaning_completed_at = db.Column(db.DateTime, nullable=True)

    # 分割
    splitting_completed_at = db.Column(db.DateTime, nullable=True)

    # 索引
    tokens = db.Column(db.Integer, nullable=True)
    indexing_latency = db.Column(db.Float, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    # 暂停
    is_paused = db.Column(db.Boolean, nullable=True, server_default=db.text('false'))
    paused_by = db.Column(StringUUID, nullable=True)
    paused_at = db.Column(db.DateTime, nullable=True)

    # 错误
    error = db.Column(db.Text, nullable=True)
    stopped_at = db.Column(db.DateTime, nullable=True)

    # 基本字段
    indexing_status = db.Column(db.String(
        255), nullable=False, server_default=db.text("'waiting'::character varying"))
    enabled = db.Column(db.Boolean, nullable=False,
                        server_default=db.text('true'))
    disabled_at = db.Column(db.DateTime, nullable=True)
    disabled_by = db.Column(StringUUID, nullable=True)
    archived = db.Column(db.Boolean, nullable=False,
                         server_default=db.text('false'))
    archived_reason = db.Column(db.String(255), nullable=True)
    archived_by = db.Column(StringUUID, nullable=True)
    archived_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False,
                           server_default=db.text('CURRENT_TIMESTAMP(0)'))
    doc_type = db.Column(db.String(40), nullable=True)
    doc_metadata = db.Column(db.JSON, nullable=True)
    doc_form = db.Column(db.String(
        255), nullable=False, server_default=db.text("'text_model'::character varying"))
    doc_language = db.Column(db.String(255), nullable=True)

    DATA_SOURCES = ['upload_file', 'notion_import']

    @property
    def display_status(self):
        """
        获取文档的显示状态。

        返回:
            文档当前的状态，如'queuing', 'paused', 'indexing', 'error', 'available', 'disabled', 'archived'。
        """
        status = None
        if self.indexing_status == 'waiting':
            status = 'queuing'
        elif self.indexing_status not in ['completed', 'error', 'waiting'] and self.is_paused:
            status = 'paused'
        elif self.indexing_status in ['parsing', 'cleaning', 'splitting', 'indexing']:
            status = 'indexing'
        elif self.indexing_status == 'error':
            status = 'error'
        elif self.indexing_status == 'completed' and not self.archived and self.enabled:
            status = 'available'
        elif self.indexing_status == 'completed' and not self.archived and not self.enabled:
            status = 'disabled'
        elif self.indexing_status == 'completed' and self.archived:
            status = 'archived'
        return status

    @property
    def data_source_info_dict(self):
        """
        将data_source_info转换为字典。

        返回:
            如果data_source_info是有效的JSON字符串，则返回其字典表示；否则返回空字典。
        """
        if self.data_source_info:
            try:
                data_source_info_dict = json.loads(self.data_source_info)
            except JSONDecodeError:
                data_source_info_dict = {}

            return data_source_info_dict
        return None

    @property
    def data_source_detail_dict(self):
        """
        获取数据源的详细信息字典。

        返回:
            根据数据源类型返回不同的详细信息字典，如果数据源类型是'upload_file'，则包含上传文件的详细信息；如果是'notion_import'，则返回Notion导入的相关信息。
        """
        if self.data_source_info:
            if self.data_source_type == 'upload_file':
                data_source_info_dict = json.loads(self.data_source_info)
                file_detail = db.session.query(UploadFile). \
                    filter(UploadFile.id == data_source_info_dict['upload_file_id']). \
                    one_or_none()
                if file_detail:
                    return {
                        'upload_file': {
                            'id': file_detail.id,
                            'name': file_detail.name,
                            'size': file_detail.size,
                            'extension': file_detail.extension,
                            'mime_type': file_detail.mime_type,
                            'created_by': file_detail.created_by,
                            'created_at': file_detail.created_at.timestamp()
                        }
                    }
            elif self.data_source_type == 'notion_import':
                return json.loads(self.data_source_info)
        return {}

    @property
    def average_segment_length(self):
        """
        计算平均段落长度。

        返回:
            如果文档有段落且非空，则返回字词数量除以段落数量的整数结果；否则返回0。
        """
        if self.word_count and self.word_count != 0 and self.segment_count and self.segment_count != 0:
            return self.word_count // self.segment_count
        return 0

    @property
    def dataset_process_rule(self):
        """
        获取数据处理规则对象。

        返回:
            如果存在数据处理规则ID，则返回对应的数据处理规则对象；否则返回None。
        """
        if self.dataset_process_rule_id:
            return DatasetProcessRule.query.get(self.dataset_process_rule_id)
        return None

    @property
    def dataset(self):
        """
        获取指定文档集的详细信息。
        
        参数:
        - 无
        
        返回值:
        - 返回与当前实例关联的文档集信息。如果找不到对应的文档集，则返回None。
        """
        return db.session.query(Dataset).filter(Dataset.id == self.dataset_id).one_or_none()

    @property
    def segment_count(self):
        """
        计算当前文档中段落的数量。
        
        参数:
        - 无
        
        返回值:
        - 返回当前文档中段落的数量。
        """
        return DocumentSegment.query.filter(DocumentSegment.document_id == self.id).count()

    @property
    def hit_count(self):
        """
        计算当前文档中所有段落的命中总数。
        
        参数:
        - 无
        
        返回值:
        - 返回当前文档中所有段落的命中总数。如果文档中没有段落，则返回0。
        """
        return DocumentSegment.query.with_entities(func.coalesce(func.sum(DocumentSegment.hit_count))) \
            .filter(DocumentSegment.document_id == self.id).scalar()

class DocumentSegment(db.Model):
    """
    文档段落模型，用于表示文档中的一个片段。
    
    属性:
    - id: 唯一标识符，UUID类型。
    - tenant_id: 租户ID，UUID类型，不可为空。
    - dataset_id: 数据集ID，UUID类型，不可为空。
    - document_id: 文档ID，UUID类型，不可为空。
    - position: 段落位置，整数类型，不可为空。
    - content: 段落内容，文本类型，不可为空。
    - answer: 对应的答案，文本类型，可为空。
    - word_count: 单元格中的字数，整数类型，不可为空。
    - tokens: 代币数，整数类型，不可为空。
    - keywords: 关键词，JSON类型，可为空。
    - index_node_id: 索引节点ID，字符串类型，可为空。
    - index_node_hash: 索引节点哈希，字符串类型，可为空。
    - hit_count: 命中次数，整数类型，默认为0，不可为空。
    - enabled: 是否启用，布尔类型，默认为True，不可为空。
    - disabled_at: 禁用时间，日期时间类型，可为空。
    - disabled_by: 禁用操作者ID，UUID类型，可为空。
    - status: 状态，字符串类型，默认为'waiting'，不可为空。
    - created_by: 创建者ID，UUID类型，不可为空。
    - created_at: 创建时间，日期时间类型，不可为空。
    - updated_by: 更新者ID，UUID类型，可为空。
    - updated_at: 更新时间，日期时间类型，不可为空。
    - indexing_at: 索引时间，日期时间类型，可为空。
    - completed_at: 完成时间，日期时间类型，可为空。
    - error: 错误信息，文本类型，可为空。
    - stopped_at: 停止时间，日期时间类型，可为空。
    
    方法:
    - dataset: 获取数据集对象。
    - document: 获取文档对象。
    - previous_segment: 获取前一个段落对象。
    - next_segment: 获取下一个段落对象。
    """
    
    __tablename__ = 'document_segments'
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='document_segment_pkey'),
        db.Index('document_segment_dataset_id_idx', 'dataset_id'),
        db.Index('document_segment_document_id_idx', 'document_id'),
        db.Index('document_segment_tenant_dataset_idx', 'dataset_id', 'tenant_id'),
        db.Index('document_segment_tenant_document_idx', 'document_id', 'tenant_id'),
        db.Index('document_segment_dataset_node_idx', 'dataset_id', 'index_node_id'),
        db.Index('document_segment_tenant_idx', 'tenant_id'),
    )

    # initial fields
    id = db.Column(StringUUID, nullable=False,
                   server_default=db.text('uuid_generate_v4()'))
    tenant_id = db.Column(StringUUID, nullable=False)
    dataset_id = db.Column(StringUUID, nullable=False)
    document_id = db.Column(StringUUID, nullable=False)
    position = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=True)
    word_count = db.Column(db.Integer, nullable=False)
    tokens = db.Column(db.Integer, nullable=False)

    # 索引字段
    keywords = db.Column(db.JSON, nullable=True)
    index_node_id = db.Column(db.String(255), nullable=True)
    index_node_hash = db.Column(db.String(255), nullable=True)

    # 基础字段
    hit_count = db.Column(db.Integer, nullable=False, default=0)
    enabled = db.Column(db.Boolean, nullable=False,
                        server_default=db.text('true'))
    disabled_at = db.Column(db.DateTime, nullable=True)
    disabled_by = db.Column(StringUUID, nullable=True)
    status = db.Column(db.String(255), nullable=False,
                       server_default=db.text("'waiting'::character varying"))
    created_by = db.Column(StringUUID, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False,
                           server_default=db.text('CURRENT_TIMESTAMP(0)'))
    updated_by = db.Column(StringUUID, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False,
                           server_default=db.text('CURRENT_TIMESTAMP(0)'))
    indexing_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    error = db.Column(db.Text, nullable=True)
    stopped_at = db.Column(db.DateTime, nullable=True)

    @property
    def dataset(self):
        """
        获取数据集对象。
        
        返回:
        - Dataset对象或None。
        """
        return db.session.query(Dataset).filter(Dataset.id == self.dataset_id).first()

    @property
    def document(self):
        """
        获取文档对象。
        
        返回:
        - Document对象或None。
        """
        return db.session.query(Document).filter(Document.id == self.document_id).first()

    @property
    def previous_segment(self):
        """
        获取前一个段落对象。
        
        返回:
        - DocumentSegment对象或None。
        """
        return db.session.query(DocumentSegment).filter(
            DocumentSegment.document_id == self.document_id,
            DocumentSegment.position == self.position - 1
        ).first()

    @property
    def next_segment(self):
        """
        获取下一个段落对象。
        
        返回:
        - DocumentSegment对象或None。
        """
        return db.session.query(DocumentSegment).filter(
            DocumentSegment.document_id == self.document_id,
            DocumentSegment.position == self.position + 1
        ).first()

    def get_sign_content(self):
        pattern = r"/files/([a-f0-9\-]+)/image-preview"
        text = self.content
        match = re.search(pattern, text)

        if match:
            upload_file_id = match.group(1)
            nonce = os.urandom(16).hex()
            timestamp = str(int(time.time()))
            data_to_sign = f"image-preview|{upload_file_id}|{timestamp}|{nonce}"
            secret_key = current_app.config['SECRET_KEY'].encode()
            sign = hmac.new(secret_key, data_to_sign.encode(), hashlib.sha256).digest()
            encoded_sign = base64.urlsafe_b64encode(sign).decode()

            params = f"timestamp={timestamp}&nonce={nonce}&sign={encoded_sign}"
            replacement = r"\g<0>?{params}".format(params=params)
            text = re.sub(pattern, replacement, text)
        return text



class AppDatasetJoin(db.Model):
    """
    app 和 dataset 关联的模型类，用于表示应用和数据集之间的关系。
    
    属性:
    - id: 关联的唯一标识符，使用UUID作为主键。
    - app_id: 应用的唯一标识符，UUID类型，不可为空。
    - dataset_id: 数据集的唯一标识符，UUID类型，不可为空。
    - created_at: 记录创建时间，DateTime类型，不可为空，默认为当前时间。
    
    方法:
    - app: 一个属性方法，用于获取与当前关联相关联的应用对象。
    """
    
    __tablename__ = 'app_dataset_joins'  # 指定数据库表名为 app_dataset_joins
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='app_dataset_join_pkey'),  # 指定主键约束
        db.Index('app_dataset_join_app_dataset_idx', 'dataset_id', 'app_id'),  # 创建索引以优化查询
    )

    id = db.Column(StringUUID, primary_key=True, nullable=False, server_default=db.text('uuid_generate_v4()'))
    app_id = db.Column(StringUUID, nullable=False)
    dataset_id = db.Column(StringUUID, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.current_timestamp())

    @property
    def app(self):
        """
        app 属性，用于获取与当前关联相关联的应用对象。
        
        返回值:
        - 返回一个App对象，该对象与当前关联的app_id相匹配。
        """
        return App.query.get(self.app_id)  # 通过app_id查询并返回对应的App对象


class DatasetQuery(db.Model):
    """
    数据集查询模型，用于表示数据集查询的相关信息。
    
    属性:
    - id: 查询的唯一标识符，使用UUID作为主键。
    - dataset_id: 关联的数据集的UUID。
    - content: 查询的内容，以文本形式存储。
    - source: 查询的来源，使用字符串形式表示。
    - source_app_id: 来源应用的UUID，可为空。
    - created_by_role: 创建查询的用户的角色，以字符串形式存储。
    - created_by: 创建查询的用户的UUID。
    - created_at: 查询创建的时间，使用DateTime类型，默认为当前时间。
    """
    
    __tablename__ = 'dataset_queries'  # 指定数据库表名为'dataset_queries'
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='dataset_query_pkey'),  # 指定主键约束
        db.Index('dataset_query_dataset_id_idx', 'dataset_id'),  # 为dataset_id创建索引
    )

    id = db.Column(StringUUID, primary_key=True, nullable=False, server_default=db.text('uuid_generate_v4()'))
    dataset_id = db.Column(StringUUID, nullable=False)
    content = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(255), nullable=False)
    source_app_id = db.Column(StringUUID, nullable=True)
    created_by_role = db.Column(db.String, nullable=False)
    created_by = db.Column(StringUUID, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.current_timestamp())


class DatasetKeywordTable(db.Model):
    """
    数据集关键词表模型，用于表示数据集与关键词表之间的关系。
    
    属性:
    - id: 唯一标识符，使用UUID作为主键。
    - dataset_id: 关联的数据集的唯一标识符，不可为空，且为唯一值。
    - keyword_table: 存储关键词表的JSON字符串，关键词映射到其对应的节点索引集合。
    
    方法:
    - keyword_table_dict: 将keyword_table中的JSON字符串解析为字典，其中节点索引集合转换为set类型。
    """
    
    __tablename__ = 'dataset_keyword_tables'  # 指定数据库表名
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='dataset_keyword_table_pkey'),  # 指定主键约束
        db.Index('dataset_keyword_table_dataset_id_idx', 'dataset_id'),  # 为dataset_id创建索引
    )

    id = db.Column(StringUUID, primary_key=True, server_default=db.text('uuid_generate_v4()'))
    dataset_id = db.Column(StringUUID, nullable=False, unique=True)
    keyword_table = db.Column(db.Text, nullable=False)
    data_source_type = db.Column(db.String(255), nullable=False,
                                 server_default=db.text("'database'::character varying"))

    @property
    def keyword_table_dict(self):
        """
        将keyword_table中的JSON字符串解析为字典，其中的列表转换为集合类型。
        
        返回值:
        - 如果keyword_table非空，返回解析后的字典，其中列表转换为了集合；
        - 如果keyword_table为空，返回None。
        """
        class SetDecoder(json.JSONDecoder):
            """
            自定义JSON解码器，用于将JSON中的列表转换为集合。
            """
            def __init__(self, *args, **kwargs):
                super().__init__(object_hook=self.object_hook, *args, **kwargs)

            def object_hook(self, dct):
                """
                解析JSON对象时的钩子函数，用于将列表转换为集合。
                
                参数:
                - dct: 解析中的JSON对象。
                
                返回值:
                - 将列表转换为集合后的JSON对象。
                """
                if isinstance(dct, dict):
                    for keyword, node_idxs in dct.items():
                        if isinstance(node_idxs, list):
                            dct[keyword] = set(node_idxs)
                return dct

        # get dataset
        dataset = Dataset.query.filter_by(
            id=self.dataset_id
        ).first()
        if not dataset:
            return None
        if self.data_source_type == 'database':
            return json.loads(self.keyword_table, cls=SetDecoder) if self.keyword_table else None
        else:
            file_key = 'keyword_files/' + dataset.tenant_id + '/' + self.dataset_id + '.txt'
            try:
                keyword_table_text = storage.load_once(file_key)
                if keyword_table_text:
                    return json.loads(keyword_table_text.decode('utf-8'), cls=SetDecoder)
                return None
            except Exception as e:
                logging.exception(str(e))
                return None


class Embedding(db.Model):
    """
    表示一个嵌入模型的数据库模型类，该类与数据库表`embeddings`相对应，并定义了存储模型信息及操作嵌入数据的方法。

    属性:
    - id: 嵌入的唯一标识符，类型为UUID，作为主键。
    - model_name: 模型的名称，类型为字符串，不能为空。
    - hash: 用于确保模型唯一性的哈希值，类型为字符串，不能为空。
    - embedding: 存储模型嵌入数据的二进制大对象，类型为LargeBinary，不能为空。
    - created_at: 记录创建时间，类型为DateTime，由服务器自动设置为当前时间。

    方法:
    - set_embedding: 设置模型的嵌入数据。
    - get_embedding: 获取模型的嵌入数据。
    """

    __tablename__ = 'embeddings'  # 定义数据库表名
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='embedding_pkey'),
        db.UniqueConstraint('model_name', 'hash', 'provider_name', name='embedding_hash_idx')
    )

    id = db.Column(StringUUID, primary_key=True, server_default=db.text('uuid_generate_v4()'))
    model_name = db.Column(db.String(40), nullable=False,
                           server_default=db.text("'text-embedding-ada-002'::character varying"))
    hash = db.Column(db.String(64), nullable=False)
    embedding = db.Column(db.LargeBinary, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    provider_name = db.Column(db.String(40), nullable=False,
                              server_default=db.text("''::character varying"))

    def set_embedding(self, embedding_data: list[float]):
        """
        设置模型的嵌入数据。

        参数:
        - embedding_data (list[float]): 一个浮点数列表，表示要存储的模型嵌入数据。

        该方法将输入的嵌入数据序列化后存入数据库中的`embedding`字段。
        """
        self.embedding = pickle.dumps(embedding_data, protocol=pickle.HIGHEST_PROTOCOL)

    def get_embedding(self) -> list[float]:
        """
        获取模型的嵌入数据。

        返回值:
        - list[float]: 一个浮点数列表，表示从数据库中获取的模型嵌入数据。

        该方法从数据库中的`embedding`字段读取并反序列化嵌入数据。
        """
        return pickle.loads(self.embedding)


class DatasetCollectionBinding(db.Model):
    """
    数据集集合绑定模型，用于表示数据集与集合之间的绑定关系。
    
    属性:
    id: 唯一标识符，使用UUID作为主键。
    provider_name: 提供者名称，不可为空。
    model_name: 模型名称，不可为空。
    type: 绑定类型，默认为'dataset'，不可为空。
    collection_name: 集合名称，不可为空。
    created_at: 创建时间，不可为空，默认为当前时间。
    """
    __tablename__ = 'dataset_collection_bindings'  # 指定数据库表名为dataset_collection_bindings
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='dataset_collection_bindings_pkey'),  # 指定主键约束
        db.Index('provider_model_name_idx', 'provider_name', 'model_name')  # 创建provider_name和model_name的索引
    )

    id = db.Column(StringUUID, primary_key=True, server_default=db.text('uuid_generate_v4()'))
    provider_name = db.Column(db.String(40), nullable=False)
    model_name = db.Column(db.String(40), nullable=False)
    type = db.Column(db.String(40), server_default=db.text("'dataset'::character varying"), nullable=False)
    collection_name = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
