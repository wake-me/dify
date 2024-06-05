"""Abstract interface for document loader implementations."""
from abc import ABC, abstractmethod
from typing import Optional

from flask import current_app

from core.model_manager import ModelInstance
from core.rag.extractor.entity.extract_setting import ExtractSetting
from core.rag.models.document import Document
from core.rag.splitter.fixed_text_splitter import (
    EnhanceRecursiveCharacterTextSplitter,
    FixedRecursiveCharacterTextSplitter,
)
from core.rag.splitter.text_splitter import TextSplitter
from models.dataset import Dataset, DatasetProcessRule


class BaseIndexProcessor(ABC):
    """提取文件的接口。
    """

    @abstractmethod
    def extract(self, extract_setting: ExtractSetting, **kwargs) -> list[Document]:
        """
        提取文档方法。
        
        参数:
        - extract_setting: 提取设置对象，包含提取相关的配置。
        - **kwargs: 可变的关键字参数，用于提供额外的配置。
        
        返回值:
        - Document列表：提取后的文档对象列表。
        """
        raise NotImplementedError

    @abstractmethod
    def transform(self, documents: list[Document], **kwargs) -> list[Document]:
        """
        转换文档方法。
        
        参数:
        - documents: 文档列表，需要进行转换的文档对象。
        - **kwargs: 可变的关键字参数，用于提供额外的配置。
        
        返回值:
        - Document列表：转换后的文档对象列表。
        """
        raise NotImplementedError

    @abstractmethod
    def load(self, dataset: Dataset, documents: list[Document], with_keywords: bool = True):
        """
        加载数据集中的文档方法。
        
        参数:
        - dataset: 数据集对象，包含需要加载的文档数据。
        - documents: 文档列表，指定需要加载的文档对象。
        - with_keywords: 布尔值，指示是否加载关键词。
        """
        raise NotImplementedError

    def clean(self, dataset: Dataset, node_ids: Optional[list[str]], with_keywords: bool = True):
        """
        清理数据集中的文档方法。
        
        参数:
        - dataset: 数据集对象，包含需要清理的文档数据。
        - node_ids: 字符串列表，指定需要清理的文档节点ID。
        - with_keywords: 布尔值，指示是否清理关键词。
        """
        raise NotImplementedError

    @abstractmethod
    def retrieve(self, retrival_method: str, query: str, dataset: Dataset, top_k: int,
                 score_threshold: float, reranking_model: dict) -> list[Document]:
        """
        检索文档方法。
        
        参数:
        - retrival_method: 字符串，指定检索方法。
        - query: 字符串，查询字符串。
        - dataset: 数据集对象，用于检索的文档数据。
        - top_k: 整数，指定返回的结果数量。
        - score_threshold: 浮点数，检索得分阈值。
        - reranking_model: 字典，重排模型配置。
        
        返回值:
        - Document列表：检索结果的文档对象列表。
        """
        raise NotImplementedError

    def _get_splitter(self, processing_rule: dict,
                      embedding_model_instance: Optional[ModelInstance]) -> TextSplitter:
        """
        根据处理规则获取分割器对象。
        
        参数:
        - processing_rule: 字典，包含分割规则的配置。
        - embedding_model_instance: ModelInstance可选对象，嵌入模型实例。
        
        返回值:
        - TextSplitter对象：用于文本分割的对象。
        """
        if processing_rule['mode'] == "custom":
            # 获取用户自定义分割规则对应的分割器
            rules = processing_rule['rules']
            segmentation = rules["segmentation"]
            max_segmentation_tokens_length = int(current_app.config['INDEXING_MAX_SEGMENTATION_TOKENS_LENGTH'])
            if segmentation["max_tokens"] < 50 or segmentation["max_tokens"] > max_segmentation_tokens_length:
                raise ValueError(f"Custom segment length should be between 50 and {max_segmentation_tokens_length}.")

            separator = segmentation["separator"]
            if separator:
                separator = separator.replace('\\n', '\n')

            character_splitter = FixedRecursiveCharacterTextSplitter.from_encoder(
                chunk_size=segmentation["max_tokens"],
                chunk_overlap=segmentation.get('chunk_overlap', 0),
                fixed_separator=separator,
                separators=["\n\n", "。", ". ", " ", ""],
                embedding_model_instance=embedding_model_instance
            )
        else:
            # 获取自动分割规则对应的分割器
            character_splitter = EnhanceRecursiveCharacterTextSplitter.from_encoder(
                chunk_size=DatasetProcessRule.AUTOMATIC_RULES['segmentation']['max_tokens'],
                chunk_overlap=DatasetProcessRule.AUTOMATIC_RULES['segmentation']['chunk_overlap'],
                separators=["\n\n", "。", ". ", " ", ""],
                embedding_model_instance=embedding_model_instance
            )

        return character_splitter
