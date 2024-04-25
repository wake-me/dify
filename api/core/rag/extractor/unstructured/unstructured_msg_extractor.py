import logging

from core.rag.extractor.extractor_base import BaseExtractor
from core.rag.models.document import Document

logger = logging.getLogger(__name__)


class UnstructuredMsgExtractor(BaseExtractor):
    """
    用于加载msg文件的类。

    Args:
        file_path (str): 要加载的文件路径。
        api_url (str): API的URL，用于后续处理或验证（本代码示例中未使用，但预留此参数以扩展功能）。
    """

    def __init__(
        self,
        file_path: str,
        api_url: str
    ):
        """
        初始化加载器，设置文件路径和API URL。

        Args:
            file_path (str): 文件路径。
            api_url (str): API的URL。
        """
        self._file_path = file_path  # 文件路径
        self._api_url = api_url  # API的URL

    def extract(self) -> list[Document]:
        """
        从msg文件中提取文档。

        分割文件内容为多个部分（chunk），然后将每个部分作为独立的文档处理。每个文档包含文件中的一段文本。

        Returns:
            list[Document]: 包含从msg文件中提取的文本的文档列表。
        """
        # 从msg文件分割内容
        from unstructured.partition.msg import partition_msg

        elements = partition_msg(filename=self._file_path)
        # 按标题分割内容，并组合一定字符数之内的文本
        from unstructured.chunking.title import chunk_by_title
        chunks = chunk_by_title(elements, max_characters=2000, combine_text_under_n_chars=2000)
        
        documents = []  # 存储提取的文档
        for chunk in chunks:
            text = chunk.text.strip()  # 清除文本两端的空白字符
            documents.append(Document(page_content=text))  # 将文本添加到文档列表

        return documents