import logging

from core.rag.extractor.extractor_base import BaseExtractor
from core.rag.models.document import Document

logger = logging.getLogger(__name__)


class UnstructuredPPTXExtractor(BaseExtractor):
    """
    用于提取非结构化PPTX文件内容的类。

    Args:
        file_path (str): 要加载的文件路径。
        api_url (str): API的URL，用于可能的进一步处理或验证。
    """

    def __init__(
            self,
            file_path: str,
            api_url: str
    ):
        """
        初始化提取器实例。

        Args:
            file_path (str): 文件路径。
            api_url (str): API的URL。
        """
        self._file_path = file_path  # 文件路径
        self._api_url = api_url  # API的URL

    def extract(self) -> list[Document]:
        """
        从PPTX文件中提取文档内容。

        分割PPTX文件的每一页，将它们作为独立的文档返回。首先，使用`partition_pptx`函数将PPTX内容分割成各个元素，
        然后将这些元素按页归类，最后将每页的内容作为一个文档返回。

        Returns:
            list[Document]: 包含文件每一页内容的文档对象列表。
        """
        from unstructured.partition.pptx import partition_pptx

        # 分割PPTX文件
        elements = partition_pptx(filename=self._file_path)
        
        # 按页归类文本
        text_by_page = {}
        for element in elements:
            page = element.metadata.page_number
            text = element.text
            if page in text_by_page:
                text_by_page[page] += "\n" + text
            else:
                text_by_page[page] = text

        # 合并每页的文本
        combined_texts = list(text_by_page.values())
        documents = []
        for combined_text in combined_texts:
            text = combined_text.strip()  # 去除首尾空白
            documents.append(Document(page_content=text))  # 创建文档对象

        return documents
