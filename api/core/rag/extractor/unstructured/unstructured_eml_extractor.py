import base64
import logging

from bs4 import BeautifulSoup

from core.rag.extractor.extractor_base import BaseExtractor
from core.rag.models.document import Document

logger = logging.getLogger(__name__)


class UnstructuredEmailExtractor(BaseExtractor):
    """
    用于加载和提取msg文件中的电子邮件内容。
    
    Args:
        file_path (str): 要加载的文件路径。
        api_url (str): 用于处理电子邮件的API URL。
    """

    def __init__(
        self,
        file_path: str,
        api_url: str,
    ):
        """
        初始化提取器，设置文件路径和API URL。
        
        Args:
            file_path (str): 要处理的文件路径。
            api_url (str): 外部API的URL。
        """
        self._file_path = file_path
        self._api_url = api_url

    def extract(self) -> list[Document]:
        """
        从msg文件中提取电子邮件内容，并返回Document对象列表。
        
        Returns:
            list[Document]: 包含电子邮件文本的Document对象列表。
        """
        # 加载电子邮件并根据结构进行分割
        from unstructured.partition.email import partition_email
        elements = partition_email(filename=self._file_path)

        try:
            # 对分割后的每个电子邮件元素进行Base64解码，并清理格式
            for element in elements:
                element_text = element.text.strip()

                # 保证文本长度为4的倍数，以便于Base64解码
                padding_needed = 4 - len(element_text) % 4
                element_text += '=' * padding_needed

                # 解码并使用BeautifulSoup解析电子邮件内容
                element_decode = base64.b64decode(element_text)
                soup = BeautifulSoup(element_decode.decode('utf-8'), 'html.parser')
                element.text = soup.get_text()
        except Exception:
            # 忽略在处理电子邮件内容时出现的任何异常
            pass

        # 将电子邮件内容分割成合适的块，并准备文档列表
        from unstructured.chunking.title import chunk_by_title
        chunks = chunk_by_title(elements, max_characters=2000, combine_text_under_n_chars=2000)
        documents = []
        for chunk in chunks:
            text = chunk.text.strip()
            documents.append(Document(page_content=text))
        return documents