import concurrent.futures
import datetime
import json
import logging
import re
import threading
import time
import uuid
from typing import Optional, cast

from flask import Flask, current_app
from flask_login import current_user
from sqlalchemy.orm.exc import ObjectDeletedError

from configs import dify_config
from core.errors.error import ProviderTokenNotInitError
from core.llm_generator.llm_generator import LLMGenerator
from core.model_manager import ModelInstance, ModelManager
from core.model_runtime.entities.model_entities import ModelType, PriceType
from core.model_runtime.model_providers.__base.large_language_model import LargeLanguageModel
from core.model_runtime.model_providers.__base.text_embedding_model import TextEmbeddingModel
from core.rag.datasource.keyword.keyword_factory import Keyword
from core.rag.docstore.dataset_docstore import DatasetDocumentStore
from core.rag.extractor.entity.extract_setting import ExtractSetting
from core.rag.index_processor.index_processor_base import BaseIndexProcessor
from core.rag.index_processor.index_processor_factory import IndexProcessorFactory
from core.rag.models.document import Document
from core.rag.splitter.fixed_text_splitter import (
    EnhanceRecursiveCharacterTextSplitter,
    FixedRecursiveCharacterTextSplitter,
)
from core.rag.splitter.text_splitter import TextSplitter
from extensions.ext_database import db
from extensions.ext_redis import redis_client
from extensions.ext_storage import storage
from libs import helper
from models.dataset import Dataset, DatasetProcessRule, DocumentSegment
from models.dataset import Document as DatasetDocument
from models.model import UploadFile
from services.feature_service import FeatureService


class IndexingRunner:
    """
    负责执行索引过程的类。
    
    属性:
    storage: 存储介质，用于数据存储。
    model_manager: 模型管理器，用于管理索引模型。
    """

    def __init__(self):
        """
        初始化IndexingRunner实例。
        """
        self.storage = storage
        self.model_manager = ModelManager()

    def run(self, dataset_documents: list[DatasetDocument]):
        """
        执行索引过程。
        
        参数:
        dataset_documents: 一个DatasetDocument实例列表，表示需要进行索引的数据集文档。
        """
        for dataset_document in dataset_documents:
            try:
                # 根据文档ID查询数据集
                dataset = Dataset.query.filter_by(
                    id=dataset_document.dataset_id
                ).first()

                # 如果数据集不存在，则抛出异常
                if not dataset:
                    raise ValueError("no dataset found")

                # 根据处理规则查询索引处理方式
                processing_rule = db.session.query(DatasetProcessRule). \
                    filter(DatasetProcessRule.id == dataset_document.dataset_process_rule_id). \
                    first()
                index_type = dataset_document.doc_form
                # 根据索引类型创建索引处理器
                index_processor = IndexProcessorFactory(index_type).init_index_processor()
                # 使用索引处理器提取文本数据
                text_docs = self._extract(index_processor, dataset_document, processing_rule.to_dict())

                # 对提取的文本进行转换
                documents = self._transform(index_processor, dataset, text_docs, dataset_document.doc_language,
                                            processing_rule.to_dict())
                # 保存分段结果
                self._load_segments(dataset, dataset_document, documents)

                # 加载索引
                self._load(
                    index_processor=index_processor,
                    dataset=dataset,
                    dataset_document=dataset_document,
                    documents=documents
                )
            except DocumentIsPausedException:
                # 如果文档被暂停，则抛出暂停异常
                raise DocumentIsPausedException('Document paused, document id: {}'.format(dataset_document.id))
            except ProviderTokenNotInitError as e:
                # 如果提供商令牌未初始化，则更新文档状态为错误并记录错误信息
                dataset_document.indexing_status = 'error'
                dataset_document.error = str(e.description)
                dataset_document.stopped_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                db.session.commit()
            except ObjectDeletedError:
                # 如果文档被删除，则记录警告信息
                logging.warning('Document deleted, document id: {}'.format(dataset_document.id))
            except Exception as e:
                # 对于其他异常，记录异常信息，并更新文档状态为错误
                logging.exception("consume document failed")
                dataset_document.indexing_status = 'error'
                dataset_document.error = str(e)
                dataset_document.stopped_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                db.session.commit()


    def run_in_splitting_status(self, dataset_document: DatasetDocument):
        """
        当索引状态为splitting时，执行索引过程。
        
        :param dataset_document: 数据集文档对象，包含需要索引的数据集的详细信息。
        :type dataset_document: DatasetDocument
        """
        try:
            # 获取数据集
            dataset = Dataset.query.filter_by(
                id=dataset_document.dataset_id
            ).first()

            if not dataset:
                raise ValueError("no dataset found")

            # 获取已存在的文档分段列表并删除
            document_segments = DocumentSegment.query.filter_by(
                dataset_id=dataset.id,
                document_id=dataset_document.id
            ).all()

            for document_segment in document_segments:
                db.session.delete(document_segment)
            db.session.commit()
            
            # 获取处理规则
            processing_rule = db.session.query(DatasetProcessRule). \
                filter(DatasetProcessRule.id == dataset_document.dataset_process_rule_id). \
                first()

            index_type = dataset_document.doc_form
            index_processor = IndexProcessorFactory(index_type).init_index_processor()
            
            # 提取文本
            text_docs = self._extract(index_processor, dataset_document, processing_rule.to_dict())

            # 转换文档
            documents = self._transform(index_processor, dataset, text_docs, dataset_document.doc_language,
                                        processing_rule.to_dict())
            # 保存分段
            self._load_segments(dataset, dataset_document, documents)

            # 加载索引
            self._load(
                index_processor=index_processor,
                dataset=dataset,
                dataset_document=dataset_document,
                documents=documents
            )
        except DocumentIsPausedException:
            # 如果文档被暂停，则抛出暂停异常
            raise DocumentIsPausedException('Document paused, document id: {}'.format(dataset_document.id))
        except ProviderTokenNotInitError as e:
            # 处理提供商令牌未初始化的错误
            dataset_document.indexing_status = 'error'
            dataset_document.error = str(e.description)
            dataset_document.stopped_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            db.session.commit()
        except Exception as e:
            # 记录并处理其他异常
            logging.exception("consume document failed")
            dataset_document.indexing_status = 'error'
            dataset_document.error = str(e)
            dataset_document.stopped_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            db.session.commit()

    def run_in_indexing_status(self, dataset_document: DatasetDocument):
        """
        在索引状态为indexing时运行索引过程。
        
        参数:
        - dataset_document: DatasetDocument对象，包含需要索引的文档数据集信息。
        
        注意: 此函数不返回任何值，但可能会抛出异常。
        """

        try:
            # 获取数据集
            dataset = Dataset.query.filter_by(
                id=dataset_document.dataset_id
            ).first()

            if not dataset:
                raise ValueError("no dataset found")  # 如果未找到对应的数据集，则抛出异常

            # 获取已存在的文档段列表并删除
            document_segments = DocumentSegment.query.filter_by(
                dataset_id=dataset.id,
                document_id=dataset_document.id
            ).all()

            documents = []
            if document_segments:
                for document_segment in document_segments:
                    # 将文档段转换为节点
                    if document_segment.status != "completed":
                        document = Document(
                            page_content=document_segment.content,
                            metadata={
                                "doc_id": document_segment.index_node_id,
                                "doc_hash": document_segment.index_node_hash,
                                "document_id": document_segment.document_id,
                                "dataset_id": document_segment.dataset_id,
                            }
                        )

                        documents.append(document)

            # 构建索引
            # 获取处理规则
            processing_rule = db.session.query(DatasetProcessRule). \
                filter(DatasetProcessRule.id == dataset_document.dataset_process_rule_id). \
                first()

            index_type = dataset_document.doc_form
            index_processor = IndexProcessorFactory(index_type).init_index_processor()
            self._load(
                index_processor=index_processor,
                dataset=dataset,
                dataset_document=dataset_document,
                documents=documents
            )
        except DocumentIsPausedException:
            # 如果文档被暂停，则抛出暂停异常
            raise DocumentIsPausedException('Document paused, document id: {}'.format(dataset_document.id))
        except ProviderTokenNotInitError as e:
            # 处理提供商令牌未初始化的错误
            dataset_document.indexing_status = 'error'
            dataset_document.error = str(e.description)
            dataset_document.stopped_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            db.session.commit()
        except Exception as e:
            # 记录并处理通用异常
            logging.exception("consume document failed")
            dataset_document.indexing_status = 'error'
            dataset_document.error = str(e)
            dataset_document.stopped_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            db.session.commit()

    def indexing_estimate(self, tenant_id: str, extract_settings: list[ExtractSetting], tmp_processing_rule: dict,
                          doc_form: str = None, doc_language: str = 'English', dataset_id: str = None,
                          indexing_technique: str = 'economy') -> dict:
        """
        根据文档形式、语言、数据集ID及索引技术等参数，估算文档的索引情况。计算总段落数、令牌数及费用信息。

        参数:
        - tenant_id (str): 租户标识符。
        - extract_settings (list[ExtractSetting]): 提取文档信息的设置列表。
        - tmp_processing_rule (dict): 用于文档处理的临时处理规则。
        - doc_form (str, 可选): 文档形式，默认为None。
        - doc_language (str, 可选): 文档语言，默认为'English'。
        - dataset_id (str, 可选): 数据集标识符，默认为None。
        - indexing_technique (str, 可选): 使用的索引技术，默认为'经济型'。

        返回:
        - dict: 包含估算索引详情的字典，如总段落数、令牌数、总价及货币单位。
        """
        
        # 检查文档是否超过基于租户计费特性的批量上传限制。
        features = FeatureService.get_features(tenant_id)
        if features.billing.enabled:
            count = len(extract_settings)
            batch_upload_limit = dify_config.BATCH_UPLOAD_LIMIT
            if count > batch_upload_limit:
                raise ValueError(f"You have reached the batch upload limit of {batch_upload_limit}.")

        embedding_model_instance = None
        # 根据数据集ID和索引技术确定合适的嵌入模型实例。
        if dataset_id:
            dataset = Dataset.query.filter_by(
                id=dataset_id
            ).first()
            if not dataset:
                raise ValueError('Dataset not found.')
            
            # 检查是否使用高质量索引技术
            if dataset.indexing_technique == 'high_quality' or indexing_technique == 'high_quality':
                # 如果数据集指定了嵌入模型提供者，则尝试获取该模型实例
                if dataset.embedding_model_provider:
                    embedding_model_instance = self.model_manager.get_model_instance(
                        tenant_id=tenant_id,
                        provider=dataset.embedding_model_provider,
                        model_type=ModelType.TEXT_EMBEDDING,
                        model=dataset.embedding_model
                    )
                else:
                    # 如果未指定嵌入模型提供者，则获取默认的嵌入模型实例
                    embedding_model_instance = self.model_manager.get_default_model_instance(
                        tenant_id=tenant_id,
                        model_type=ModelType.TEXT_EMBEDDING,
                    )
        else:
            # 如果未提供数据集ID，且使用高质量索引技术，则直接获取默认的嵌入模型实例
            if indexing_technique == 'high_quality':
                embedding_model_instance = self.model_manager.get_default_model_instance(
                    tenant_id=tenant_id,
                    model_type=ModelType.TEXT_EMBEDDING,
                )
        # 初始化用于存储计算结果的变量。
        tokens = 0
        preview_texts = []
        total_segments = 0
        total_price = 0
        currency = 'USD'
        index_type = doc_form
        index_processor = IndexProcessorFactory(index_type).init_index_processor()
        all_text_docs = []
        for extract_setting in extract_settings:
            # 基于指定的提取设置和处理规则提取文本文档。
            text_docs = index_processor.extract(extract_setting, process_rule_mode=tmp_processing_rule["mode"])
            all_text_docs.extend(text_docs)
            processing_rule = DatasetProcessRule(
                mode=tmp_processing_rule["mode"],
                rules=json.dumps(tmp_processing_rule["rules"])
            )

            # 根据处理规则和嵌入模型实例获取适当的拆分器。
            splitter = self._get_splitter(processing_rule, embedding_model_instance)

            # 将文本文档分割成更小的段落。
            documents = self._split_to_documents_for_estimate(
                text_docs=text_docs,
                splitter=splitter,
                processing_rule=processing_rule
            )

            total_segments += len(documents)
            for document in documents:
                if len(preview_texts) < 5:
                    preview_texts.append(document.page_content)
                if indexing_technique == 'high_quality' or embedding_model_instance:
                    tokens += embedding_model_instance.get_text_embedding_num_tokens(
                        texts=[self.filter_string(document.page_content)]
                    )

        # 若文档形式为'问答模型'，则使用问答模型计算费用。
        if doc_form and doc_form == 'qa_model':
            model_instance = self.model_manager.get_default_model_instance(
                tenant_id=tenant_id,
                model_type=ModelType.LLM
            )

            model_type_instance = model_instance.model_type_instance
            model_type_instance = cast(LargeLanguageModel, model_type_instance)

            if len(preview_texts) > 0:
                # qa model document
                response = LLMGenerator.generate_qa_document(current_user.current_tenant_id, preview_texts[0],
                                                             doc_language)
                document_qa_list = self.format_split_text(response)
                price_info = model_type_instance.get_price(
                    model=model_instance.model,
                    credentials=model_instance.credentials,
                    price_type=PriceType.INPUT,
                    tokens=total_segments * 2000,
                )
                return {
                    "total_segments": total_segments * 20,
                    "tokens": total_segments * 2000,
                    "total_price": '{:f}'.format(price_info.total_amount),
                    "currency": price_info.currency,
                    "qa_preview": document_qa_list,
                    "preview": preview_texts
                }
        # 若使用了嵌入模型实例，则根据令牌数计算费用。
        if embedding_model_instance:
            embedding_model_type_instance = cast(TextEmbeddingModel, embedding_model_instance.model_type_instance)
            embedding_price_info = embedding_model_type_instance.get_price(
                model=embedding_model_instance.model,
                credentials=embedding_model_instance.credentials,
                price_type=PriceType.INPUT,
                tokens=tokens
            )
            total_price = '{:f}'.format(embedding_price_info.total_amount)
            currency = embedding_price_info.currency
        return {
            "total_segments": total_segments,
            "tokens": tokens,
            "total_price": total_price,
            "currency": currency,
            "preview": preview_texts
        }

    def _extract(self, index_processor: BaseIndexProcessor, dataset_document: DatasetDocument, process_rule: dict) \
            -> list[Document]:
        # load file
        if dataset_document.data_source_type not in ["upload_file", "notion_import", "website_crawl"]:
            return []

        data_source_info = dataset_document.data_source_info_dict
        text_docs = []
        if dataset_document.data_source_type == 'upload_file':
            # 上传文件类型的处理逻辑
            if not data_source_info or 'upload_file_id' not in data_source_info:
                raise ValueError("no upload file found")

            file_detail = db.session.query(UploadFile). \
                filter(UploadFile.id == data_source_info['upload_file_id']). \
                one_or_none()

            if file_detail:
                extract_setting = ExtractSetting(
                    datasource_type="upload_file",
                    upload_file=file_detail,
                    document_model=dataset_document.doc_form
                )
                text_docs = index_processor.extract(extract_setting, process_rule_mode=process_rule['mode'])
        elif dataset_document.data_source_type == 'notion_import':
            # Notion导入类型的处理逻辑
            if (not data_source_info or 'notion_workspace_id' not in data_source_info
                    or 'notion_page_id' not in data_source_info):
                raise ValueError("no notion import info found")
            extract_setting = ExtractSetting(
                datasource_type="notion_import",
                notion_info={
                    "notion_workspace_id": data_source_info['notion_workspace_id'],
                    "notion_obj_id": data_source_info['notion_page_id'],
                    "notion_page_type": data_source_info['type'],
                    "document": dataset_document,
                    "tenant_id": dataset_document.tenant_id
                },
                document_model=dataset_document.doc_form
            )
            text_docs = index_processor.extract(extract_setting, process_rule_mode=process_rule['mode'])
        elif dataset_document.data_source_type == 'website_crawl':
            if (not data_source_info or 'provider' not in data_source_info
                    or 'url' not in data_source_info or 'job_id' not in data_source_info):
                raise ValueError("no website import info found")
            extract_setting = ExtractSetting(
                datasource_type="website_crawl",
                website_info={
                    "provider": data_source_info['provider'],
                    "job_id": data_source_info['job_id'],
                    "tenant_id": dataset_document.tenant_id,
                    "url": data_source_info['url'],
                    "mode": data_source_info['mode'],
                    "only_main_content": data_source_info['only_main_content']
                },
                document_model=dataset_document.doc_form
            )
            text_docs = index_processor.extract(extract_setting, process_rule_mode=process_rule['mode'])
        # update document status to splitting
        self._update_document_index_status(
            document_id=dataset_document.id,
            after_indexing_status="splitting",
            extra_update_params={
                DatasetDocument.word_count: sum(len(text_doc.page_content) for text_doc in text_docs),
                DatasetDocument.parsing_completed_at: datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            }
        )

        # 更新文档ID为数据集文档ID
        text_docs = cast(list[Document], text_docs)
        for text_doc in text_docs:
            text_doc.metadata['document_id'] = dataset_document.id
            text_doc.metadata['dataset_id'] = dataset_document.dataset_id

        return text_docs

    @staticmethod
    def filter_string(text):
        text = re.sub(r'<\|', '<', text)
        text = re.sub(r'\|>', '>', text)
        text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F\xEF\xBF\xBE]', '', text)
        # Unicode  U+FFFE
        text = re.sub('\uFFFE', '', text)
        return text

    @staticmethod
    def _get_splitter(processing_rule: DatasetProcessRule,
                      embedding_model_instance: Optional[ModelInstance]) -> TextSplitter:
        """
        根据处理规则获取文本分割器对象。

        参数:
        - processing_rule: DatasetProcessRule对象，包含数据集的处理规则。
        - embedding_model_instance: ModelInstance对象的可选实例，用于嵌入模型的实例。

        返回值:
        - TextSplitter对象，用于对文本进行分割。

        根据处理规则的不同（定制规则或自动规则），创建并返回不同的TextSplitter实例。
        """

        if processing_rule.mode == "custom":
            # 根据用户定义的分割规则进行文本分割
            rules = json.loads(processing_rule.rules)
            segmentation = rules["segmentation"]
            max_segmentation_tokens_length = dify_config.INDEXING_MAX_SEGMENTATION_TOKENS_LENGTH
            if segmentation["max_tokens"] < 50 or segmentation["max_tokens"] > max_segmentation_tokens_length:
                raise ValueError(f"Custom segment length should be between 50 and {max_segmentation_tokens_length}.")

            separator = segmentation["separator"]
            # 替换转义的换行符
            if separator:
                separator = separator.replace('\\n', '\n')

            if segmentation.get('chunk_overlap'):
                chunk_overlap = segmentation['chunk_overlap']
            else:
                chunk_overlap = 0

            # 创建定制的文本分割器
            character_splitter = FixedRecursiveCharacterTextSplitter.from_encoder(
                chunk_size=segmentation["max_tokens"],
                chunk_overlap=chunk_overlap,
                fixed_separator=separator,
                separators=["\n\n", "。", ". ", " ", ""],
                embedding_model_instance=embedding_model_instance
            )
        else:
            # 使用自动分割规则进行文本分割
            character_splitter = EnhanceRecursiveCharacterTextSplitter.from_encoder(
                chunk_size=DatasetProcessRule.AUTOMATIC_RULES['segmentation']['max_tokens'],
                chunk_overlap=DatasetProcessRule.AUTOMATIC_RULES['segmentation']['chunk_overlap'],
                separators=["\n\n", "。", ". ", " ", ""],
                embedding_model_instance=embedding_model_instance
            )

        return character_splitter

    def _step_split(self, text_docs: list[Document], splitter: TextSplitter,
                    dataset: Dataset, dataset_document: DatasetDocument, processing_rule: DatasetProcessRule) \
            -> list[Document]:
        """
        将文本文档拆分为更小的文档，并将它们保存到文档段中。
        
        此方法使用指定的分隔器将给定的文本文档拆分成较小的文档段。然后，它将这些段保存到关联的
        数据集文档中的文档存储中。同时更新文档及其段的状态以反映正在进行的索引过程。
        
        参数：
        - text_docs（list[Document]）：要拆分的Document对象列表。
        - splitter（TextSplitter）：用于划分文本文档的分隔器算法。
        - dataset（Dataset）：拆分后的文档所属的数据集。
        - dataset_document（DatasetDocument）：数据集中正在处理的具体文档。
        - processing_rule（DatasetProcessRule）：定义文档处理方式的规则。
        
        返回：
        - list[Document]：表示原始文档拆分段的Document对象列表。
        """

        # 根据指定的分隔器和处理规则将输入的文本文档拆分为更小的文档。
        documents = self._split_to_documents(
            text_docs=text_docs,
            splitter=splitter,
            processing_rule=processing_rule,
            tenant_id=dataset.tenant_id,
            document_form=dataset_document.doc_form,
            document_language=dataset_document.doc_language
        )

        # 使用数据集和数据集文档信息初始化一个文档存储，以保存拆分的文档。
        doc_store = DatasetDocumentStore(
            dataset=dataset,
            user_id=dataset_document.created_by,
            document_id=dataset_document.id
        )

        # 将拆分的文档保存到文档存储中。
        doc_store.add_documents(documents)

        # 更新数据集文档的状态为'索引中'，为即将进行的索引过程做准备。
        cur_time = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        self._update_document_index_status(
            document_id=dataset_document.id,
            after_indexing_status="indexing",
            extra_update_params={
                DatasetDocument.cleaning_completed_at: cur_time,
                DatasetDocument.splitting_completed_at: cur_time,
            }
        )

        # 更新由数据集文档生成的所有段的状态为'索引中'，表示索引过程已经开始。
        self._update_segments_by_document(
            dataset_document_id=dataset_document.id,
            update_params={
                DocumentSegment.status: "indexing",
                DocumentSegment.indexing_at: datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            }
        )

        return documents

    def _split_to_documents(self, text_docs: list[Document], splitter: TextSplitter,
                            processing_rule: DatasetProcessRule, tenant_id: str,
                            document_form: str, document_language: str) -> list[Document]:
        """
        根据指定的分隔符和处理规则，将文本文档分割成节点。
        
        :param text_docs: 包含源文本文档的Document对象列表。
        :param splitter: TextSplitter实例，用于分割文档。
        :param processing_rule: 数据集处理规则对象。
        :param tenant_id: 租户ID字符串。
        :param document_form: 文档形式，可选'qa_model'。
        :param document_language: 文档语言字符串。

        :return: 分割后的Document对象列表。
        """
        all_documents = []
        all_qa_documents = []

        # 清理文档文本并分割文档
        for text_doc in text_docs:
            # 清理文档内容
            document_text = self._document_clean(text_doc.page_content, processing_rule)
            text_doc.page_content = document_text

            # 将文档解析为节点
            documents = splitter.split_documents([text_doc])
            split_documents = []
            for document_node in documents:
                if document_node.page_content.strip():
                    doc_id = str(uuid.uuid4())
                    hash = helper.generate_text_hash(document_node.page_content)

                    # 设置元数据
                    document_node.metadata['doc_id'] = doc_id
                    document_node.metadata['doc_hash'] = hash

                    # 删除分隔符
                    page_content = document_node.page_content
                    if page_content.startswith(".") or page_content.startswith("。"):
                        page_content = page_content[1:]
                    document_node.page_content = page_content

                    # 添加到已分割文档列表
                    if document_node.page_content:
                        split_documents.append(document_node)
                all_documents.extend(split_documents)

        # 处理QA模型格式的文档
        if document_form == 'qa_model':
            for i in range(0, len(all_documents), 10):
                threads = []
                sub_documents = all_documents[i:i + 10]
                for doc in sub_documents:
                    # 创建线程以格式化QA文档
                    document_format_thread = threading.Thread(target=self.format_qa_document, kwargs={
                        'flask_app': current_app._get_current_object(),
                        'tenant_id': tenant_id, 'document_node': doc, 'all_qa_documents': all_qa_documents,
                        'document_language': document_language})
                    threads.append(document_format_thread)
                    document_format_thread.start()
                # 等待所有线程完成
                for thread in threads:
                    thread.join()

            # 返回格式化后的QA文档
            return all_qa_documents
        # 返回未格式化的文档
        return all_documents

    def format_qa_document(self, flask_app: Flask, tenant_id: str, document_node, all_qa_documents, document_language):
        """
        格式化问答文档。
        
        参数:
        - flask_app: Flask应用实例，用于提供应用上下文。
        - tenant_id: 租户ID，标识文档所属的租户。
        - document_node: 文档节点，包含文档的页面内容和其他元数据。
        - all_qa_documents: 一个列表，用于收集所有格式化后的问答文档。
        - document_language: 文档的语言。
        
        返回值:
        - 无。函数通过修改all_qa_documents参数来返回结果。
        """
        format_documents = []
        # 如果页面内容为空，则提前返回
        if document_node.page_content is None or not document_node.page_content.strip():
            return
        with flask_app.app_context():
            try:
                # 使用QA模型生成问答文档
                response = LLMGenerator.generate_qa_document(tenant_id, document_node.page_content, document_language)
                document_qa_list = self.format_split_text(response)
                qa_documents = []
                for result in document_qa_list:
                    qa_document = Document(page_content=result['question'], metadata=document_node.metadata.model_copy())
                    doc_id = str(uuid.uuid4())
                    hash = helper.generate_text_hash(result['question'])
                    qa_document.metadata['answer'] = result['answer']
                    qa_document.metadata['doc_id'] = doc_id
                    qa_document.metadata['doc_hash'] = hash
                    qa_documents.append(qa_document)
                format_documents.extend(qa_documents)
            except Exception as e:
                # 记录异常
                logging.exception(e)

            # 将格式化后的问答文档添加到总集中
            all_qa_documents.extend(format_documents)

    def _split_to_documents_for_estimate(self, text_docs: list[Document], splitter: TextSplitter,
                                         processing_rule: DatasetProcessRule) -> list[Document]:
        """
        根据指定的分隔器和处理规则将给定的文本文档分割成更小的节点。

        :param text_docs: 包含待分割文本内容的Document对象列表。
        :param splitter: 负责将文档划分为更小部分的TextSplitter实例。
        :param processing_rule: 定义如何清理和处理文档的DatasetProcessRule实例。
        :return: 清理和分割后，表示原始文档各个部分的Document对象列表。
        """
        all_documents = []
        for text_doc in text_docs:
            # 根据指定的处理规则清理文档文本
            document_text = self._document_clean(text_doc.page_content, processing_rule)
            text_doc.page_content = document_text

            # 使用指定的分隔器将清理后的文档分割成更小的节点
            documents = splitter.split_documents([text_doc])

            split_documents = []
            for document in documents:
                # 过滤掉空或仅包含空白字符的节点
                if document.page_content is None or not document.page_content.strip():
                    continue
                # 为每个非空节点分配唯一ID并生成哈希值
                doc_id = str(uuid.uuid4())
                hash = helper.generate_text_hash(document.page_content)

                document.metadata['doc_id'] = doc_id
                document.metadata['doc_hash'] = hash

                split_documents.append(document)

            all_documents.extend(split_documents)

        return all_documents

    @staticmethod
    def _document_clean(text: str, processing_rule: DatasetProcessRule) -> str:
        """
        根据处理规则清理文档文本。
        
        :param text: 待清理的文本字符串。
        :param processing_rule: 指定的文档处理规则，包含自动和自定义规则。
        :return: 清理后的文本字符串。
        """
        # 根据处理模式选择相应的规则集
        if processing_rule.mode == "automatic":
            rules = DatasetProcessRule.AUTOMATIC_RULES
        else:
            rules = json.loads(processing_rule.rules) if processing_rule.rules else {}

        # 应用预处理规则
        if 'pre_processing_rules' in rules:
            pre_processing_rules = rules["pre_processing_rules"]
            for pre_processing_rule in pre_processing_rules:
                # 根据规则ID启用相应的清理逻辑
                if pre_processing_rule["id"] == "remove_extra_spaces" and pre_processing_rule["enabled"] is True:
                    # 移除多余空格，包括换行符和各种空白字符
                    pattern = r'\n{3,}'
                    text = re.sub(pattern, '\n\n', text)
                    pattern = r'[\t\f\r\x20\u00a0\u1680\u180e\u2000-\u200a\u202f\u205f\u3000]{2,}'
                    text = re.sub(pattern, ' ', text)
                elif pre_processing_rule["id"] == "remove_urls_emails" and pre_processing_rule["enabled"] is True:
                    # 移除电子邮件地址和URL
                    pattern = r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)'
                    text = re.sub(pattern, '', text)
                    
                    pattern = r'https?://[^\s]+'
                    text = re.sub(pattern, '', text)

        return text

    @staticmethod
    def format_split_text(text):
        regex = r"Q\d+:\s*(.*?)\s*A\d+:\s*([\s\S]*?)(?=Q\d+:|$)"
        matches = re.findall(regex, text, re.UNICODE)

        # 格式化匹配到的问题和答案，去除多余空格并处理换行
        return [
            {
                "question": q,
                "answer": re.sub(r"\n\s*", "\n", a.strip())
            }
            for q, a in matches if q and a
        ]

    def _load(self, index_processor: BaseIndexProcessor, dataset: Dataset,
            dataset_document: DatasetDocument, documents: list[Document]) -> None:
        """
        加载数据集文档，通过嵌入模型生成索引，并更新文档状态为完成。
        
        :param index_processor: 负责处理索引的处理器
        :param dataset: 目标数据集，包含索引技术与嵌入模型等配置
        :param dataset_document: 数据集文档，用于记录数据集的元数据和状态
        :param documents: 需要被索引的文档列表
        :return: None
        """

        # 尝试根据数据集配置的索引技术获取对应的嵌入模型实例
        embedding_model_instance = None
        if dataset.indexing_technique == 'high_quality':
            embedding_model_instance = self.model_manager.get_model_instance(
                tenant_id=dataset.tenant_id,
                provider=dataset.embedding_model_provider,
                model_type=ModelType.TEXT_EMBEDDING,
                model=dataset.embedding_model
            )

        # 按照chunk_size分块处理文档
        indexing_start_at = time.perf_counter()
        tokens = 0
        chunk_size = 10

        # create keyword index
        create_keyword_thread = threading.Thread(target=self._process_keyword_index,
                                                args=(current_app._get_current_object(),
                                                    dataset.id, dataset_document.id, documents))
        create_keyword_thread.start()

        # 如果索引技术为高质量索引，则使用并发执行器处理文档分块的索引生成
        if dataset.indexing_technique == 'high_quality':
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = []
                for i in range(0, len(documents), chunk_size):
                    chunk_documents = documents[i:i + chunk_size]
                    futures.append(executor.submit(self._process_chunk, current_app._get_current_object(), index_processor,
                                                   chunk_documents, dataset,
                                                   dataset_document, embedding_model_instance))

                for future in futures:
                    tokens += future.result()

        create_keyword_thread.join()
        indexing_end_at = time.perf_counter()

        # 更新文档索引状态为完成，并记录处理的token数量、完成时间和索引延迟
        self._update_document_index_status(
            document_id=dataset_document.id,
            after_indexing_status="completed",
            extra_update_params={
                DatasetDocument.tokens: tokens,
                DatasetDocument.completed_at: datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),
                DatasetDocument.indexing_latency: indexing_end_at - indexing_start_at,
                DatasetDocument.error: None,
            }
        )

    @staticmethod
    def _process_keyword_index(flask_app, dataset_id, document_id, documents):
        with flask_app.app_context():
            # 根据数据集ID查询数据集信息
            dataset = Dataset.query.filter_by(id=dataset_id).first()
            if not dataset:
                raise ValueError("no dataset found")  # 如果找不到数据集，则抛出异常
            
            # 为当前数据集创建关键字实例，并处理文档
            keyword = Keyword(dataset)
            keyword.create(documents)
            
            # 如果索引技术不为'high_quality'，则更新文档段的状态为完成
            if dataset.indexing_technique != 'high_quality':
                document_ids = [document.metadata['doc_id'] for document in documents]  # 提取文档ID列表
                
                # 更新状态为完成的文档段
                db.session.query(DocumentSegment).filter(
                    DocumentSegment.document_id == document_id,
                    DocumentSegment.dataset_id == dataset_id,
                    DocumentSegment.index_node_id.in_(document_ids),
                    DocumentSegment.status == "indexing"
                ).update({
                    DocumentSegment.status: "completed",
                    DocumentSegment.enabled: True,
                    DocumentSegment.completed_at: datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                })

                db.session.commit()  # 提交数据库事务

    def _process_chunk(self, flask_app, index_processor, chunk_documents, dataset, dataset_document,
                       embedding_model_instance):
        with flask_app.app_context():
            # 检查文档是否暂停索引
            self._check_document_paused_status(dataset_document.id)

            tokens = 0
            if embedding_model_instance:
                tokens += sum(
                    embedding_model_instance.get_text_embedding_num_tokens(
                        [document.page_content]
                    )
                    for document in chunk_documents
                )

            # 加载索引
            index_processor.load(dataset, chunk_documents, with_keywords=False)

            document_ids = [document.metadata['doc_id'] for document in chunk_documents]
            # 更新数据库中对应文档段的状态为完成，并启用它们
            db.session.query(DocumentSegment).filter(
                DocumentSegment.document_id == dataset_document.id,
                DocumentSegment.dataset_id == dataset.id,
                DocumentSegment.index_node_id.in_(document_ids),
                DocumentSegment.status == "indexing"
            ).update({
                DocumentSegment.status: "completed",
                DocumentSegment.enabled: True,
                DocumentSegment.completed_at: datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            })

            db.session.commit()

            return tokens

    @staticmethod
    def _check_document_paused_status(document_id: str):
        indexing_cache_key = 'document_{}_is_paused'.format(document_id)
        # 从Redis获取键值
        result = redis_client.get(indexing_cache_key)
        if result:
            # 如果找到键值，表示文档被暂停，抛出异常
            raise DocumentIsPausedException()

    @staticmethod
    def _update_document_index_status(document_id: str, after_indexing_status: str,
                                      extra_update_params: Optional[dict] = None) -> None:
        """
        更新文档的索引状态。

        参数:
        - document_id (str): 文档的唯一标识符。
        - after_indexing_status (str): 索引后的文档状态。
        - extra_update_params (Optional[dict]): 除了索引状态外，要更新的文档其他参数。默认为None。

        异常:
        - DocumentIsPausedException: 如果文档当前已暂停。
        - DocumentIsDeletedPausedException: 如果文档不存在或已被删除。
        """

        # 检查文档是否暂停，如果是则抛出异常
        count = DatasetDocument.query.filter_by(id=document_id, is_paused=True).count()
        if count > 0:
            raise DocumentIsPausedException()
        
        # 从数据库中获取文档
        document = DatasetDocument.query.filter_by(id=document_id).first()
        if not document:
            raise DocumentIsDeletedPausedException()

        # 准备更新参数，设置新的索引状态
        update_params = {
            DatasetDocument.indexing_status: after_indexing_status
        }

        # 如果提供额外的更新参数，则将其合并
        if extra_update_params:
            update_params.update(extra_update_params)

        # 更新数据库中文档的索引状态并提交会话
        DatasetDocument.query.filter_by(id=document_id).update(update_params)
        db.session.commit()

    @staticmethod
    def _update_segments_by_document(dataset_document_id: str, update_params: dict) -> None:
        """
        根据文档ID更新文档段落。
        
        此方法根据提供的文档ID及更新参数，更新数据库中文档段落的相应属性。

        参数:
        - dataset_document_id (str): 数据集内文档的唯一标识符。
        - update_params (dict): 包含文档段落待更新属性的字典。

        返回:
        - None: 此方法不返回任何值，直接在数据库中进行更新操作。
        """
        # 使用提供的参数更新数据库中的文档段落
        DocumentSegment.query.filter_by(document_id=dataset_document_id).update(update_params)
        
        # 提交更改到数据库
        db.session.commit()

    @staticmethod
    def batch_add_segments(segments: list[DocumentSegment], dataset: Dataset):
        """
        批量添加段落索引处理

        :param segments: 文档段落列表，每个段落包含文档内容及相关元数据
        :type segments: list[DocumentSegment]
        :param dataset: 数据集对象，包含文档的存储形式等信息
        :type dataset: Dataset
        :return: 无
        """

        # 初始化文档列表
        documents = []
        for segment in segments:
            # 为每个段落创建文档对象
            document = Document(
                page_content=segment.content,
                metadata={
                    "doc_id": segment.index_node_id,
                    "doc_hash": segment.index_node_hash,
                    "document_id": segment.document_id,
                    "dataset_id": segment.dataset_id,
                }
            )
            documents.append(document)
        
        # 根据数据集的文档形式加载索引处理器并处理文档
        index_type = dataset.doc_form
        index_processor = IndexProcessorFactory(index_type).init_index_processor()
        index_processor.load(dataset, documents)

    def _transform(self, index_processor: BaseIndexProcessor, dataset: Dataset,
                text_docs: list[Document], doc_language: str, process_rule: dict) -> list[Document]:
        """
        对给定的文本文档列表进行转换处理。
        
        :param index_processor: 用于转换文本文档的索引处理器实例。
        :param dataset: 包含文档嵌入模型配置信息的数据集对象。
        :param text_docs: 待处理的文档列表，每个文档是一个Document对象。
        :param doc_language: 文档的语言。
        :param process_rule: 文档处理规则的字典。
        :return: 处理后的文档列表，每个文档是一个Document对象。
        """
        # 尝试根据数据集的配置获取嵌入模型实例
        embedding_model_instance = None
        if dataset.indexing_technique == 'high_quality':
            # 如果数据集指定了嵌入模型提供者，则尝试获取特定的模型实例
            if dataset.embedding_model_provider:
                embedding_model_instance = self.model_manager.get_model_instance(
                    tenant_id=dataset.tenant_id,
                    provider=dataset.embedding_model_provider,
                    model_type=ModelType.TEXT_EMBEDDING,
                    model=dataset.embedding_model
                )
            else:
                # 如果未指定嵌入模型提供者，则获取默认的嵌入模型实例
                embedding_model_instance = self.model_manager.get_default_model_instance(
                    tenant_id=dataset.tenant_id,
                    model_type=ModelType.TEXT_EMBEDDING,
                )

        # 使用索引处理器和配置的嵌入模型对文档进行转换处理
        documents = index_processor.transform(text_docs, embedding_model_instance=embedding_model_instance,
                                            process_rule=process_rule, tenant_id=dataset.tenant_id,
                                            doc_language=doc_language)

        return documents

    def _load_segments(self, dataset, dataset_document, documents):
        """
        加载文档段到数据集。
        
        参数:
        - dataset: 数据集对象，表示目标数据集。
        - dataset_document: 数据集文档对象，包含数据集的元数据和创建信息。
        - documents: 文档列表，需要加载到数据集中的文档段。
        
        无返回值。
        """
        # 初始化文档存储，关联数据集和文档
        doc_store = DatasetDocumentStore(
            dataset=dataset,
            user_id=dataset_document.created_by,
            document_id=dataset_document.id
        )

        # 将文档段添加到文档存储中
        doc_store.add_documents(documents)

        # 更新文档索引状态为"indexing"
        cur_time = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        self._update_document_index_status(
            document_id=dataset_document.id,
            after_indexing_status="indexing",
            extra_update_params={
                DatasetDocument.cleaning_completed_at: cur_time,
                DatasetDocument.splitting_completed_at: cur_time,
            }
        )

        # 更新文档段状态为"indexing"
        self._update_segments_by_document(
            dataset_document_id=dataset_document.id,
            update_params={
                DocumentSegment.status: "indexing",
                DocumentSegment.indexing_at: datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            }
        )
        pass


class DocumentIsPausedException(Exception):
    pass


class DocumentIsDeletedPausedException(Exception):
    pass
