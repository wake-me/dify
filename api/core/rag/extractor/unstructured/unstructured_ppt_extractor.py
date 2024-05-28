import logging

from core.rag.extractor.extractor_base import BaseExtractor
from core.rag.models.document import Document

logger = logging.getLogger(__name__)


class UnstructuredPPTExtractor(BaseExtractor):
    """
    用于加载msg文件的类。

    Args:
        file_path (str): 要加载的文件路径。
        api_url (str): 用于分区处理的API URL。
    """

    def __init__(
            self,
            file_path: str,
            api_url: str,
            api_key: str
    ):
        """Initialize with file path."""
        self._file_path = file_path
        self._api_url = api_url
        self._api_key = api_key

    def extract(self) -> list[Document]:
        """
        提取文档内容。

        通过调用API，将文件分割为多个部分，并将这些部分组合成一个按页面分隔的文本列表。

        Returns:
            list[Document]: 包含页面内容的Document对象列表。
        """
        # 通过API对文件进行分区处理
        from unstructured.partition.api import partition_via_api

        elements = partition_via_api(filename=self._file_path, api_url=self._api_url, api_key=self._api_key)
        text_by_page = {}
        for element in elements:
            page = element.metadata.page_number
            text = element.text
            if page in text_by_page:
                text_by_page[page] += "\n" + text
            else:
                text_by_page[page] = text

        combined_texts = list(text_by_page.values())  # 获取合并后的文本列表
        documents = []  # 存储Document对象的列表

        # 创建并添加Document对象到列表中
        for combined_text in combined_texts:
            text = combined_text.strip()  # 去除首尾空白
            documents.append(Document(page_content=text))
        
        return documents