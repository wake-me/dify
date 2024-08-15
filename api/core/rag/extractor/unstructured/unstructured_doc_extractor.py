import logging
import os

from core.rag.extractor.extractor_base import BaseExtractor
from core.rag.models.document import Document

logger = logging.getLogger(__name__)


class UnstructuredWordExtractor(BaseExtractor):
    """
    使用非结构化方法加载Word文档的加载器。
    
    Attributes:
        file_path (str): 文档文件的路径。
        api_url (str): 用于处理文档的API的URL。
    """

    def __init__(
            self,
            file_path: str,
            api_url: str,
    ):
        """
        初始化加载器。
        
        Args:
            file_path (str): 文档文件的路径。
            api_url (str): 用于处理文档的API的URL。
        """
        self._file_path = file_path
        self._api_url = api_url

    def extract(self) -> list[Document]:
        """
        从Word文档中提取内容并分割成多个文档对象。
        
        Returns:
            list[Document]: 包含文档内容的Document对象列表。
        """
        # 导入unstructured包的版本信息和文件类型检测工具
        from unstructured.__version__ import __version__ as __unstructured_version__
        from unstructured.file_utils.filetype import FileType, detect_filetype

        # 将unstructured包的版本号转换为元组格式，便于比较
        unstructured_version = tuple(
            int(x) for x in __unstructured_version__.split(".")
        )

        # 检查文件扩展名以确定是否为.doc文件
        try:
            import magic  # noqa: F401

            is_doc = detect_filetype(self._file_path) == FileType.DOC
        except ImportError:
            _, extension = os.path.splitext(str(self._file_path))
            is_doc = extension == ".doc"

        # 若文件为.doc且unstructured版本低于0.4.11，则抛出错误
        if is_doc and unstructured_version < (0, 4, 11):
            raise ValueError(
                f"You are on unstructured version {__unstructured_version__}. "
                "Partitioning .doc files is only supported in unstructured>=0.4.11. "
                "Please upgrade the unstructured package and try again."
            )

        # 根据文件类型（.doc或.docx），调用不同的分割方法
        if is_doc:
            from unstructured.partition.doc import partition_doc

            elements = partition_doc(filename=self._file_path)
        else:
            from unstructured.partition.docx import partition_docx

            elements = partition_docx(filename=self._file_path)

        # 根据标题对分割后的元素进行分块，以便生成多个文档对象
        from unstructured.chunking.title import chunk_by_title
        chunks = chunk_by_title(elements, max_characters=2000, combine_text_under_n_chars=2000)
        
        # 遍历分块结果，创建并填充Document对象列表
        documents = []
        for chunk in chunks:
            text = chunk.text.strip()
            documents.append(Document(page_content=text))
        return documents
