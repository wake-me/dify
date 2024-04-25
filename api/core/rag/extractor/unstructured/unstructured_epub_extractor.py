import logging

from core.rag.extractor.extractor_base import BaseExtractor
from core.rag.models.document import Document

logger = logging.getLogger(__name__)


class UnstructuredEpubExtractor(BaseExtractor):
    """
    用于加载epub文件的类。

    Args:
        file_path (str): 要加载的文件路径。
        api_url (str, 可选): API的URL，默认为None。
    """

    def __init__(
        self,
        file_path: str,
        api_url: str = None,
    ):
        """
        初始化加载器。

        Args:
            file_path (str): 文件路径。
            api_url (str, 可选): API的URL，默认为None。
        """
        self._file_path = file_path  # 文件路径
        self._api_url = api_url  # API的URL

    def extract(self) -> list[Document]:
        """
        从epub文件中提取文档。

        分割epub文件为多个部分，并根据标题将这些部分组合成文档。每个文档包含的文本由多个部分组成。

        Returns:
            list[Document]: 包含从epub文件提取的文档的列表。每个文档是一个包含页面内容的`Document`对象。
        """
        # 分割epub文件为多个元素
        from unstructured.partition.epub import partition_epub

        elements = partition_epub(filename=self._file_path, xml_keep_tags=True)
        
        # 根据标题将元素组合成 chunks
        from unstructured.chunking.title import chunk_by_title
        chunks = chunk_by_title(elements, max_characters=2000, combine_text_under_n_chars=2000)
        
        documents = []  # 存储提取的文档
        for chunk in chunks:
            text = chunk.text.strip()  # 从chunk中提取文本
            documents.append(Document(page_content=text))  # 将文本添加到文档列表

        return documents