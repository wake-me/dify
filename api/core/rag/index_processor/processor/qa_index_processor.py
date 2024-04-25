"""Paragraph index processor."""
import logging
import re
import threading
import uuid
from typing import Optional

import pandas as pd
from flask import Flask, current_app
from werkzeug.datastructures import FileStorage

from core.llm_generator.llm_generator import LLMGenerator
from core.rag.cleaner.clean_processor import CleanProcessor
from core.rag.datasource.retrieval_service import RetrievalService
from core.rag.datasource.vdb.vector_factory import Vector
from core.rag.extractor.entity.extract_setting import ExtractSetting
from core.rag.extractor.extract_processor import ExtractProcessor
from core.rag.index_processor.index_processor_base import BaseIndexProcessor
from core.rag.models.document import Document
from libs import helper
from models.dataset import Dataset


class QAIndexProcessor(BaseIndexProcessor):
    """
    QA索引处理器，用于处理和索引问答对文档。
    """
    
    def extract(self, extract_setting: ExtractSetting, **kwargs) -> list[Document]:
        """
        提取文本文档。
        
        参数:
        - extract_setting: 提取设置对象。
        - **kwargs: 可变参数，包括处理规则模式。
        
        返回:
        - 文本文档列表。
        """
        
        # 根据设置提取文本文档
        text_docs = ExtractProcessor.extract(extract_setting=extract_setting,
                                             is_automatic=kwargs.get('process_rule_mode') == "automatic")
        return text_docs

    def transform(self, documents: list[Document], **kwargs) -> list[Document]:
        """
        转换文档，将其拆分为节点并格式化。
        
        参数:
        - documents: 文档列表。
        - **kwargs: 可变参数，包括处理规则、嵌入模型实例等。
        
        返回:
        - 转换后的文档列表。
        """
        
        # 获取拆分器
        splitter = self._get_splitter(processing_rule=kwargs.get('process_rule'),
                                      embedding_model_instance=kwargs.get('embedding_model_instance'))

        # 拆分文本文档为节点
        all_documents = []
        all_qa_documents = []
        for document in documents:
            # 清理文档内容
            document_text = CleanProcessor.clean(document.page_content, kwargs.get('process_rule'))
            document.page_content = document_text

            # 将文档解析为节点
            document_nodes = splitter.split_documents([document])
            split_documents = []
            for document_node in document_nodes:
                # 为节点添加元数据，并清理内容
                if document_node.page_content.strip():
                    doc_id = str(uuid.uuid4())
                    hash = helper.generate_text_hash(document_node.page_content)
                    document_node.metadata['doc_id'] = doc_id
                    document_node.metadata['doc_hash'] = hash
                    page_content = document_node.page_content
                    if page_content.startswith(".") or page_content.startswith("。"):
                        page_content = page_content[1:]
                    document_node.page_content = page_content
                    split_documents.append(document_node)
            all_documents.extend(split_documents)
        
        # 多线程格式化问答文档
        for i in range(0, len(all_documents), 10):
            threads = []
            sub_documents = all_documents[i:i + 10]
            for doc in sub_documents:
                document_format_thread = threading.Thread(target=self._format_qa_document, kwargs={
                    'flask_app': current_app._get_current_object(),
                    'tenant_id': kwargs.get('tenant_id'),
                    'document_node': doc,
                    'all_qa_documents': all_qa_documents,
                    'document_language': kwargs.get('doc_language', 'English')})
                threads.append(document_format_thread)
                document_format_thread.start()
            for thread in threads:
                thread.join()
        return all_qa_documents

    def format_by_template(self, file: FileStorage, **kwargs) -> list[Document]:
        """
        根据模板格式化文件中的文档。
        
        参数:
        - file: 文件存储对象。
        - **kwargs: 可变参数，包括文档语言。
        
        返回:
        - 格式化后的文档列表。
        """
        
        # 检查文件类型
        if not file.filename.endswith('.csv'):
            raise ValueError("Invalid file type. Only CSV files are allowed")

        try:
            # 读取并处理CSV文件内容
            df = pd.read_csv(file)
            text_docs = []
            for index, row in df.iterrows():
                data = Document(page_content=row[0], metadata={'answer': row[1]})
                text_docs.append(data)
            if len(text_docs) == 0:
                raise ValueError("The CSV file is empty.")

        except Exception as e:
            raise ValueError(str(e))
        return text_docs

    def load(self, dataset: Dataset, documents: list[Document], with_keywords: bool = True):
        """
        加载文档到数据集。
        
        参数:
        - dataset: 数据集对象。
        - documents: 文档列表。
        - with_keywords: 是否包含关键词。
        """
        
        # 根据索引技术创建文档向量
        if dataset.indexing_technique == 'high_quality':
            vector = Vector(dataset)
            vector.create(documents)

    def clean(self, dataset: Dataset, node_ids: Optional[list[str]], with_keywords: bool = True):
        """
        清理数据集中的文档或节点。
        
        参数:
        - dataset: 数据集对象。
        - node_ids: 节点ID列表。
        - with_keywords: 是否包含关键词。
        """
        
        # 根据节点ID删除文档向量
        vector = Vector(dataset)
        if node_ids:
            vector.delete_by_ids(node_ids)
        else:
            vector.delete()

    def retrieve(self, retrival_method: str, query: str, dataset: Dataset, top_k: int,
                 score_threshold: float, reranking_model: dict):
        """
        从数据集中检索文档。
        
        参数:
        - retrival_method: 检索方法。
        - query: 查询字符串。
        - dataset: 数据集对象。
        - top_k: 返回结果数量。
        - score_threshold: 分数阈值。
        - reranking_model: 重排模型。
        
        返回:
        - 检索到的文档列表。
        """
        
        # 执行检索并组织结果
        results = RetrievalService.retrieve(retrival_method=retrival_method, dataset_id=dataset.id, query=query,
                                            top_k=top_k, score_threshold=score_threshold,
                                            reranking_model=reranking_model)
        docs = []
        for result in results:
            metadata = result.metadata
            metadata['score'] = result.score
            if result.score > score_threshold:
                doc = Document(page_content=result.page_content, metadata=metadata)
                docs.append(doc)
        return docs

    def _format_qa_document(self, flask_app: Flask, tenant_id: str, document_node, all_qa_documents, document_language):
        """
        格式化问答文档节点。
        
        参数:
        - flask_app: Flask应用对象。
        - tenant_id: 租户ID。
        - document_node: 文档节点对象。
        - all_qa_documents: 所有问答文档列表。
        - document_language: 文档语言。
        """
        
        format_documents = []
        if document_node.page_content is None or not document_node.page_content.strip():
            return
        with flask_app.app_context():
            try:
                # 生成问答模型文档
                response = LLMGenerator.generate_qa_document(tenant_id, document_node.page_content, document_language)
                document_qa_list = self._format_split_text(response)
                qa_documents = []
                for result in document_qa_list:
                    qa_document = Document(page_content=result['question'], metadata=document_node.metadata.copy())
                    doc_id = str(uuid.uuid4())
                    hash = helper.generate_text_hash(result['question'])
                    qa_document.metadata['answer'] = result['answer']
                    qa_document.metadata['doc_id'] = doc_id
                    qa_document.metadata['doc_hash'] = hash
                    qa_documents.append(qa_document)
                format_documents.extend(qa_documents)
            except Exception as e:
                logging.exception(e)

            all_qa_documents.extend(format_documents)

    def _format_split_text(self, text):
        """
        格式化分割文本。
        
        参数:
        - text: 输入文本。
        
        返回:
        - 分割后的问答对列表。
        """
        
        regex = r"Q\d+:\s*(.*?)\s*A\d+:\s*([\s\S]*?)(?=Q\d+:|$)"
        matches = re.findall(regex, text, re.UNICODE)

        return [
            {
                "question": q,
                "answer": re.sub(r"\n\s*", "\n", a.strip())
            }
            for q, a in matches if q and a
        ]