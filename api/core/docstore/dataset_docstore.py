from collections.abc import Sequence
from typing import Any, Optional, cast

from sqlalchemy import func

from core.model_manager import ModelManager
from core.model_runtime.entities.model_entities import ModelType
from core.model_runtime.model_providers.__base.text_embedding_model import TextEmbeddingModel
from core.rag.models.document import Document
from extensions.ext_database import db
from models.dataset import Dataset, DocumentSegment


class DatasetDocumentStore:
    """
    数据集文档存储类，用于管理和存储与数据集相关的文档信息。
    
    参数:
    - dataset: Dataset类型，表示与之相关的数据集。
    - user_id: str类型，表示用户的唯一标识符。
    - document_id: Optional[str]类型，表示文档的唯一标识符，默认为None。
    """

    def __init__(
            self,
            dataset: Dataset,
            user_id: str,
            document_id: Optional[str] = None,
    ):
        self._dataset = dataset  # 与当前存储相关联的数据集
        self._user_id = user_id  # 当前用户的ID
        self._document_id = document_id  # 当前文档的ID

    @classmethod
    def from_dict(cls, config_dict: dict[str, Any]) -> "DatasetDocumentStore":
        """
        从字典配置中创建DatasetDocumentStore实例。
        
        参数:
        - config_dict: dict[str, Any]类型，包含创建实例所需的配置信息。
        
        返回值:
        - 返回一个DatasetDocumentStore实例。
        """
        return cls(**config_dict)

    def to_dict(self) -> dict[str, Any]:
        """
        序列化为字典格式。
        
        返回值:
        - dict[str, Any]类型，包含数据集ID等信息。
        """
        return {
            "dataset_id": self._dataset.id,  # 数据集ID
        }

    @property
    def dateset_id(self) -> Any:
        """
        获取数据集ID的属性。
        
        返回值:
        - 数据集的ID。
        """
        return self._dataset.id

    @property
    def user_id(self) -> Any:
        """
        获取用户ID的属性。
        
        返回值:
        - 用户的ID。
        """
        return self._user_id

    @property
    def docs(self) -> dict[str, Document]:
        """
        获取文档信息的属性。
        
        返回值:
        - dict[str, Document]类型，键为文档ID，值为对应的Document对象。
        """
        # 从数据库查询文档片段信息
        document_segments = db.session.query(DocumentSegment).filter(
            DocumentSegment.dataset_id == self._dataset.id
        ).all()

        output = {}  # 用于存储查询结果的字典
        for document_segment in document_segments:
            doc_id = document_segment.index_node_id  # 文档ID
            output[doc_id] = Document(
                page_content=document_segment.content,  # 页面内容
                metadata={  # 元数据
                    "doc_id": document_segment.index_node_id,
                    "doc_hash": document_segment.index_node_hash,
                    "document_id": document_segment.document_id,
                    "dataset_id": document_segment.dataset_id,
                }
            )

        return output

    def add_documents(
            self, docs: Sequence[Document], allow_update: bool = True
    ) -> None:
        """
        向文档存储中添加一个或多个文档。
        
        :param docs: 一个Document对象的序列，需要被添加到存储中。
        :param allow_update: 是否允许更新已存在的文档，默认为True。
        :return: 无返回值。
        """
        # 查询当前文档中最大位置值
        max_position = db.session.query(func.max(DocumentSegment.position)).filter(
            DocumentSegment.document_id == self._document_id
        ).scalar()

        # 如果没有文档，则最大位置默认为0
        if max_position is None:
            max_position = 0
        embedding_model = None
        # 如果使用的是高质索引技术，则加载嵌入模型
        if self._dataset.indexing_technique == 'high_quality':
            model_manager = ModelManager()
            embedding_model = model_manager.get_model_instance(
                tenant_id=self._dataset.tenant_id,
                provider=self._dataset.embedding_model_provider,
                model_type=ModelType.TEXT_EMBEDDING,
                model=self._dataset.embedding_model
            )

        for doc in docs:
            # 确保传入的对象是Document类型
            if not isinstance(doc, Document):
                raise ValueError("doc must be a Document")

            # 尝试根据doc_id获取文档片段
            segment_document = self.get_document_segment(doc_id=doc.metadata['doc_id'])

            # 如果不允许更新且文档已存在，则抛出异常
            if not allow_update and segment_document:
                raise ValueError(
                    f"doc_id {doc.metadata['doc_id']} already exists. "
                    "Set allow_update to True to overwrite."
                )

            # 使用嵌入模型计算文档嵌入表示（如果存在嵌入模型）
            if embedding_model:
                model_type_instance = embedding_model.model_type_instance
                model_type_instance = cast(TextEmbeddingModel, model_type_instance)
                tokens = model_type_instance.get_num_tokens(
                    model=embedding_model.model,
                    credentials=embedding_model.credentials,
                    texts=[doc.page_content]
                )
            else:
                tokens = 0

            # 如果文档片段不存在，则创建新的文档片段
            if not segment_document:
                max_position += 1

                segment_document = DocumentSegment(
                    tenant_id=self._dataset.tenant_id,
                    dataset_id=self._dataset.id,
                    document_id=self._document_id,
                    index_node_id=doc.metadata['doc_id'],
                    index_node_hash=doc.metadata['doc_hash'],
                    position=max_position,
                    content=doc.page_content,
                    word_count=len(doc.page_content),
                    tokens=tokens,
                    enabled=False,
                    created_by=self._user_id,
                )
                # 如果存在答案信息，则保存到文档片段中
                if 'answer' in doc.metadata and doc.metadata['answer']:
                    segment_document.answer = doc.metadata.pop('answer', '')

                db.session.add(segment_document)
            else:
                # 更新已存在的文档片段信息
                segment_document.content = doc.page_content
                if 'answer' in doc.metadata and doc.metadata['answer']:
                    segment_document.answer = doc.metadata.pop('answer', '')
                segment_document.index_node_hash = doc.metadata['doc_hash']
                segment_document.word_count = len(doc.page_content)
                segment_document.tokens = tokens

            # 提交数据库会话，保存更改
            db.session.commit()

    def document_exists(self, doc_id: str) -> bool:
        """
        检查文档是否存在。
        
        参数:
        doc_id (str): 文档的ID。
        
        返回:
        bool: 如果文档存在，返回True；否则返回False。
        """
        result = self.get_document_segment(doc_id)
        return result is not None

    def get_document(
            self, doc_id: str, raise_error: bool = True
    ) -> Optional[Document]:
        """
        获取指定ID的文档。
        
        参数:
        doc_id (str): 文档的ID。
        raise_error (bool, 可选): 当文档不存在时，是否抛出错误。默认为True。
        
        返回:
        Optional[Document]: 如果找到文档，则返回Document对象；否则，如果raise_error为False，返回None。
        
        抛出:
        ValueError: 如果文档不存在且raise_error为True，则抛出ValueError。
        """
        document_segment = self.get_document_segment(doc_id)

        if document_segment is None:
            if raise_error:
                raise ValueError(f"doc_id {doc_id} not found.")
            else:
                return None

        # 创建并返回Document对象
        return Document(
            page_content=document_segment.content,
            metadata={
                "doc_id": document_segment.index_node_id,
                "doc_hash": document_segment.index_node_hash,
                "document_id": document_segment.document_id,
                "dataset_id": document_segment.dataset_id,
            }
        )

    def delete_document(self, doc_id: str, raise_error: bool = True) -> None:
        """
        删除指定ID的文档。
        
        参数:
        doc_id (str): 文档的ID。
        raise_error (bool, 可选): 当文档不存在时，是否抛出错误。默认为True。
        
        抛出:
        ValueError: 如果文档不存在且raise_error为True，则抛出ValueError。
        """
        document_segment = self.get_document_segment(doc_id)

        if document_segment is None:
            if raise_error:
                raise ValueError(f"doc_id {doc_id} not found.")
            else:
                return None

        # 从数据库中删除文档段并提交更改
        db.session.delete(document_segment)
        db.session.commit()

    def set_document_hash(self, doc_id: str, doc_hash: str) -> None:
        """
        为给定的doc_id设置文档哈希值。
        
        参数:
        doc_id (str): 文档的ID。
        doc_hash (str): 要设置的哈希值。
        """
        document_segment = self.get_document_segment(doc_id)

        if document_segment is None:
            return None

        # 更新文档段的哈希值并提交更改
        document_segment.index_node_hash = doc_hash
        db.session.commit()

    def get_document_hash(self, doc_id: str) -> Optional[str]:
        """
        获取存储的文档哈希值，如果存在的话。
        
        参数:
        doc_id (str): 文档的ID。
        
        返回值:
        Optional[str]: 如果找到文档，则返回其哈希值；如果未找到，则返回None。
        """
        document_segment = self.get_document_segment(doc_id)

        # 如果未找到对应的文档段，则返回None
        if document_segment is None:
            return None

        # 返回文档段的索引节点哈希值
        return document_segment.index_node_hash

    def get_document_segment(self, doc_id: str) -> DocumentSegment:
        """
        从数据库中查询指定文档段。
        
        参数:
        doc_id (str): 要查询的文档段的ID。
        
        返回值:
        DocumentSegment: 查询到的文档段对象。如果未找到，则抛出异常。
        """
        # 执行数据库查询，获取指定文档段
        document_segment = db.session.query(DocumentSegment).filter(
            DocumentSegment.dataset_id == self._dataset.id,
            DocumentSegment.index_node_id == doc_id
        ).first()

        # 直接返回查询结果
        return document_segment