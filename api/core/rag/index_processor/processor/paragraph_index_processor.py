"""Paragraph index processor."""
import uuid
from typing import Optional

from core.rag.cleaner.clean_processor import CleanProcessor
from core.rag.datasource.keyword.keyword_factory import Keyword
from core.rag.datasource.retrieval_service import RetrievalService
from core.rag.datasource.vdb.vector_factory import Vector
from core.rag.extractor.entity.extract_setting import ExtractSetting
from core.rag.extractor.extract_processor import ExtractProcessor
from core.rag.index_processor.index_processor_base import BaseIndexProcessor
from core.rag.models.document import Document
from libs import helper
from models.dataset import Dataset


class ParagraphIndexProcessor(BaseIndexProcessor):
    """
    段落索引处理器，继承自BaseIndexProcessor，用于处理文档的提取、转换、加载、清理和检索操作。
    """

    def extract(self, extract_setting: ExtractSetting, **kwargs) -> list[Document]:
        """
        提取文档内容。

        :param extract_setting: 提取设置对象，指定提取的配置。
        :param kwargs: 额外的关键字参数，可用于指定处理规则模式。
        :return: 文档列表。
        """
        # 根据设置提取文档，自动处理模式下会自动提取。
        text_docs = ExtractProcessor.extract(extract_setting=extract_setting,
                                             is_automatic=kwargs.get('process_rule_mode') == "automatic")

        return text_docs

    def transform(self, documents: list[Document], **kwargs) -> list[Document]:
        """
        转换文档，将文档分割成多个节点。

        :param documents: 待转换的文档列表。
        :param kwargs: 额外的关键字参数，可用于指定处理规则和嵌入模型实例。
        :return: 转换后的文档节点列表。
        """
        # 获取分割器，根据处理规则和嵌入模型实例。
        splitter = self._get_splitter(processing_rule=kwargs.get('process_rule'),
                                      embedding_model_instance=kwargs.get('embedding_model_instance'))
        all_documents = []
        for document in documents:
            # 对文档内容进行清理。
            document_text = CleanProcessor.clean(document.page_content, kwargs.get('process_rule'))
            document.page_content = document_text
            # 将文档解析成节点。
            document_nodes = splitter.split_documents([document])
            split_documents = []
            for document_node in document_nodes:
                # 为节点生成唯一标识和内容哈希值。
                if document_node.page_content.strip():
                    doc_id = str(uuid.uuid4())
                    hash = helper.generate_text_hash(document_node.page_content)
                    document_node.metadata['doc_id'] = doc_id
                    document_node.metadata['doc_hash'] = hash
                    # 删除分隔符字符。
                    page_content = document_node.page_content
                    if page_content.startswith(".") or page_content.startswith("。"):
                        page_content = page_content[1:].strip()
                    else:
                        page_content = page_content
                    if len(page_content) > 0:
                        document_node.page_content = page_content
                        split_documents.append(document_node)
            all_documents.extend(split_documents)
        return all_documents

    def load(self, dataset: Dataset, documents: list[Document], with_keywords: bool = True):
        """
        加载文档数据到索引中。

        :param dataset: 数据集对象，指定加载的索引技术。
        :param documents: 待加载的文档列表。
        :param with_keywords: 是否同时处理关键词。
        """
        # 高质量索引技术处理。
        if dataset.indexing_technique == 'high_quality':
            vector = Vector(dataset)
            vector.create(documents)
        # 处理关键词。
        if with_keywords:
            keyword = Keyword(dataset)
            keyword.create(documents)

    def clean(self, dataset: Dataset, node_ids: Optional[list[str]], with_keywords: bool = True):
        """
        清理索引数据，可选择性地删除指定节点或全部节点的关键词。

        :param dataset: 数据集对象。
        :param node_ids: 待删除的节点ID列表，若为None则删除全部。
        :param with_keywords: 是否同时清理关键词索引。
        """
        # 高质量索引技术处理。
        if dataset.indexing_technique == 'high_quality':
            vector = Vector(dataset)
            if node_ids:
                vector.delete_by_ids(node_ids)
            else:
                vector.delete()
        # 清理关键词。
        if with_keywords:
            keyword = Keyword(dataset)
            if node_ids:
                keyword.delete_by_ids(node_ids)
            else:
                keyword.delete()

    def retrieve(self, retrival_method: str, query: str, dataset: Dataset, top_k: int,
                 score_threshold: float, reranking_model: dict) -> list[Document]:
        """
        根据查询检索文档。

        :param retrival_method: 检索方法。
        :param query: 查询字符串。
        :param dataset: 数据集对象。
        :param top_k: 返回结果的数量。
        :param score_threshold: 分数阈值，仅返回分数高于此阈值的结果。
        :param reranking_model: 重排名模型。
        :return: 检索到的文档列表。
        """
        # 设置搜索参数并执行检索。
        results = RetrievalService.retrieve(retrival_method=retrival_method, dataset_id=dataset.id, query=query,
                                            top_k=top_k, score_threshold=score_threshold,
                                            reranking_model=reranking_model)
        # 组织检索结果为文档列表。
        docs = []
        for result in results:
            metadata = result.metadata
            metadata['score'] = result.score
            if result.score > score_threshold:
                doc = Document(page_content=result.page_content, metadata=metadata)
                docs.append(doc)
        return docs