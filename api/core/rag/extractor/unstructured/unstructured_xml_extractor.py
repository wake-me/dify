import logging

from core.rag.extractor.extractor_base import BaseExtractor
from core.rag.models.document import Document

logger = logging.getLogger(__name__)


class UnstructuredXmlExtractor(BaseExtractor):
    """
    用于加载和提取非结构化XML文件中数据的类。

    Args:
        file_path (str): 要加载的文件路径。
        api_url (str): API的URL，用于可能的进一步数据处理或验证。
    """

    def __init__(
        self,
        file_path: str,
        api_url: str
    ):
        """
        初始化提取器，设置文件路径和API URL。

        Args:
            file_path (str): 文件路径。
            api_url (str): API的URL。
        """
        self._file_path = file_path  # 文件路径
        self._api_url = api_url  # API的URL

    def extract(self) -> list[Document]:
        """
        从XML文件中提取文档。

        分割XML文件内容，按标题分块，然后将每块文本作为独立的文档处理。

        Returns:
            list[Document]: 包含从XML文件中提取出的文本的文档列表。
        """
        # 分割XML文件内容
        from unstructured.partition.xml import partition_xml
        elements = partition_xml(filename=self._file_path, xml_keep_tags=True)

        # 按标题分块
        from unstructured.chunking.title import chunk_by_title
        chunks = chunk_by_title(elements, max_characters=2000, combine_text_under_n_chars=2000)

        documents = []
        for chunk in chunks:
            # 提取文本并创建文档对象
            text = chunk.text.strip()
            documents.append(Document(page_content=text))

        return documents