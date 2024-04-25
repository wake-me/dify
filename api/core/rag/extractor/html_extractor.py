"""Abstract interface for document loader implementations."""
from bs4 import BeautifulSoup

from core.rag.extractor.extractor_base import BaseExtractor
from core.rag.models.document import Document


class HtmlExtractor(BaseExtractor):
    """
    用于加载HTML文件的类。

    Args:
        file_path (str): 要加载的文件的路径。
    """

    def __init__(
        self,
        file_path: str
    ):
        """
        初始化HtmlExtractor实例。

        Args:
            file_path (str): 要加载的HTML文件的路径。
        """
        self._file_path = file_path  # 存储文件路径

    def extract(self) -> list[Document]:
        """
        从HTML文件中提取内容。

        Returns:
            Document列表: 包含从HTML文件中提取到的内容的文档对象列表。
        """
        return [Document(page_content=self._load_as_text())]  # 创建并返回包含提取内容的文档对象列表

    def _load_as_text(self) -> str:
        """
        从HTML文件中加载文本内容。

        Returns:
            str: 从HTML文件中提取到的文本内容。
        """
        with open(self._file_path, "rb") as fp:  # 以二进制读取模式打开文件
            soup = BeautifulSoup(fp, 'html.parser')  # 使用BeautifulSoup解析HTML
            text = soup.get_text()  # 从HTML中提取文本
            text = text.strip() if text else ''  # 去除文本两端的空白字符，若文本为空则设为空字符串

        return text  # 返回提取到的文本