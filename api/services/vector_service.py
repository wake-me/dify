from typing import Optional

from core.rag.datasource.keyword.keyword_factory import Keyword
from core.rag.datasource.vdb.vector_factory import Vector
from core.rag.models.document import Document
from models.dataset import Dataset, DocumentSegment


class VectorService:
    """
    向量服务类，提供文档向量的创建和更新功能。
    """

    @classmethod
    def create_segments_vector(cls, keywords_list: Optional[list[list[str]]],
                               segments: list[DocumentSegment], dataset: Dataset):
        """
        为给定的文档段创建向量索引。

        :param keywords_list: 关键词列表的列表，每个列表包含属于同一文档段的关键词。可选参数。
        :param segments: 文档段列表，每个文档段包含文档的内容和元数据。
        :param dataset: 数据集对象，定义了索引技术等参数。
        """
        # 创建文档对象列表
        documents = []
        for segment in segments:
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

        # 高质量索引技术下，保存向量索引
        if dataset.indexing_technique == 'high_quality':
            vector = Vector(
                dataset=dataset
            )
            vector.add_texts(documents, duplicate_check=True)

        # 保存关键词索引
        keyword = Keyword(dataset)
        if keywords_list and len(keywords_list) > 0:
            keyword.add_texts(documents, keyword_list=keywords_list)
        else:
            keyword.add_texts(documents)

    @classmethod
    def update_segment_vector(cls, keywords: Optional[list[str]], segment: DocumentSegment, dataset: Dataset):
        """
        更新给定文档段的向量索引。

        :param keywords: 关键词列表，为要更新的文档段指定新的关键词。可选参数。
        :param segment: 要更新的文档段对象。
        :param dataset: 数据集对象，定义了索引技术等参数。
        """
        # 格式化新的索引
        document = Document(
            page_content=segment.content,
            metadata={
                "doc_id": segment.index_node_id,
                "doc_hash": segment.index_node_hash,
                "document_id": segment.document_id,
                "dataset_id": segment.dataset_id,
            }
        )

        # 高质量索引技术下，更新向量索引
        if dataset.indexing_technique == 'high_quality':
            vector = Vector(
                dataset=dataset
            )
            vector.delete_by_ids([segment.index_node_id])  # 删除旧的向量索引
            vector.add_texts([document], duplicate_check=True)  # 添加新的向量索引

        # 更新关键词索引
        keyword = Keyword(dataset)
        keyword.delete_by_ids([segment.index_node_id])  # 删除旧的关键词索引

        # 保存更新后的关键词索引
        if keywords and len(keywords) > 0:
            keyword.add_texts([document], keywords_list=[keywords])
        else:
            keyword.add_texts([document])