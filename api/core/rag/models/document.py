from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any, Optional

from pydantic import BaseModel, Field


class Document(BaseModel):
    """
    用于存储文本片段及其相关元数据的类。
    
    属性:
        page_content (str): 页面内容。
        metadata (Optional[dict]): 关于页面内容的任意元数据（例如：来源、与其他文档的关系等）。默认为一个空字典。
    """
    page_content: str

    # 用于存储关于页面内容的任意元数据，可以包括来源、与其他文档的关系等
    metadata: Optional[dict] = Field(default_factory=dict)

class BaseDocumentTransformer(ABC):
    """Abstract base class for document transformation systems.

    A document transformation system takes a sequence of Documents and returns a
    sequence of transformed Documents.

    Example:
        .. code-block:: python

            class EmbeddingsRedundantFilter(BaseDocumentTransformer, BaseModel):
                embeddings: Embeddings
                similarity_fn: Callable = cosine_similarity
                similarity_threshold: float = 0.95

                class Config:
                    arbitrary_types_allowed = True

                def transform_documents(
                    self, documents: Sequence[Document], **kwargs: Any
                ) -> Sequence[Document]:
                    stateful_documents = get_stateful_documents(documents)
                    embedded_documents = _get_embeddings_from_stateful_docs(
                        self.embeddings, stateful_documents
                    )
                    included_idxs = _filter_similar_embeddings(
                        embedded_documents, self.similarity_fn, self.similarity_threshold
                    )
                    return [stateful_documents[i] for i in sorted(included_idxs)]

                async def atransform_documents(
                    self, documents: Sequence[Document], **kwargs: Any
                ) -> Sequence[Document]:
                    raise NotImplementedError

    """

    @abstractmethod
    def transform_documents(
        self, documents: Sequence[Document], **kwargs: Any
    ) -> Sequence[Document]:
        """
        转换一系列文档对象。

        此方法接收一个文档对象的序列，并对其进行转换操作，返回转换后的文档对象序列。

        参数:
            documents: 要转换的文档对象序列。每个文档对象都应符合Document类型。

        返回值:
            转换后的文档对象序列。
        """

    @abstractmethod
    async def atransform_documents(
        self, documents: Sequence[Document], **kwargs: Any
    ) -> Sequence[Document]:
        """
        异步地转换一系列文档对象。

        参数:
            documents: 要被转换的文档对象序列。

        返回值:
            转换后的文档对象序列。
        """
