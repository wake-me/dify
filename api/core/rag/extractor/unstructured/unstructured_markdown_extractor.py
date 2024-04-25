import logging

from core.rag.extractor.extractor_base import BaseExtractor
from core.rag.models.document import Document

logger = logging.getLogger(__name__)


class UnstructuredMarkdownExtractor(BaseExtractor):
    """
    用于加载md文件的类。

    参数:
        file_path: 要加载的文件的路径。

        remove_hyperlinks: 是否从文本中移除超链接。

        remove_images: 是否从文本中移除图片。

        encoding: 要使用的文件编码。如果为`None`，则将使用默认系统编码加载文件。

        autodetect_encoding: 是否尝试在指定编码失败时自动检测文件编码。
    """

    def __init__(
        self,
        file_path: str,
        api_url: str,
    ):
        """
        使用文件路径初始化。

        参数:
            file_path: 文件路径。
            api_url: API的URL。
        """
        self._file_path = file_path  # 文件路径
        self._api_url = api_url  # API的URL

    def extract(self) -> list[Document]:
        """
        从Markdown文件中提取文档。

        分割Markdown文件内容，然后根据标题将其拆分为多个文档块。每个文档块的内容被封装成一个`Document`对象，并收集在一个列表中返回。

        返回值:
            包含多个`Document`对象的列表，每个对象包含一个文档块的内容。
        """
        # 从Markdown文件分割内容
        from unstructured.partition.md import partition_md

        elements = partition_md(filename=self._file_path)
        # 根据标题拆分内容
        from unstructured.chunking.title import chunk_by_title
        chunks = chunk_by_title(elements, max_characters=2000, combine_text_under_n_chars=2000)
        documents = []
        for chunk in chunks:
            text = chunk.text.strip()  # 获取文本并去除首尾空白
            documents.append(Document(page_content=text))  # 将每个拆分块封装为Document对象

        return documents