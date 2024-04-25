import logging

from core.rag.extractor.extractor_base import BaseExtractor
from core.rag.models.document import Document

logger = logging.getLogger(__name__)


class UnstructuredTextExtractor(BaseExtractor):
    """
    用于加载和提取非结构化文本数据的类。

    Args:
        file_path (str): 要加载的文件路径。
        api_url (str): 用于处理文本的API的URL。
    """

    def __init__(
        self,
        file_path: str,
        api_url: str
    ):
        """
        初始化提取器，设置文件路径和API URL。

        Args:
            file_path (str): 要加载的文件路径。
            api_url (str): 用于处理文本的API的URL。
        """
        self._file_path = file_path  # 文件路径
        self._api_url = api_url  # API的URL


    def extract(self) -> list[Document]:
        """
        从文件中提取文档。

        分割文件文本，按标题分块，并将每块文本作为独立的文档处理。

        Returns:
            list[Document]: 包含多个文档的列表，每个文档是一个包含页面内容的`Document`对象。
        """
        from unstructured.partition.text import partition_text

        # 通过指定的文件路径分割文本
        elements = partition_text(filename=self._file_path)
        from unstructured.chunking.title import chunk_by_title
        # 按标题将文本分块，设定字符限制
        chunks = chunk_by_title(elements, max_characters=2000, combine_text_under_n_chars=2000)
        documents = []
        # 遍历每个分块，创建文档对象
        for chunk in chunks:
            text = chunk.text.strip() # 清除边缘空格
            documents.append(Document(page_content=text)) # 添加到文档列表

        return documents
