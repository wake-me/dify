"""Abstract interface for document loader implementations."""
from collections.abc import Iterator
from typing import Optional

from core.rag.extractor.blod.blod import Blob
from core.rag.extractor.extractor_base import BaseExtractor
from core.rag.models.document import Document
from extensions.ext_storage import storage


class PdfExtractor(BaseExtractor):
    """
    用于加载PDF文件的类。

    Args:
        file_path: 文件加载路径。
        file_cache_key: 可选；文件缓存的键名。
    """

    def __init__(
            self,
            file_path: str,
            file_cache_key: Optional[str] = None
    ):
        """
        初始化加载器。

        Args:
            file_path: 文件路径。
            file_cache_key: 可选；用于缓存文件的键名。
        """
        self._file_path = file_path  # 文件路径
        self._file_cache_key = file_cache_key  # 缓存键名

    def extract(self) -> list[Document]:
        """
        从PDF中提取文本内容。

        Returns:
            Document列表，每个文档包含页面内容和元数据。
        """
        plaintext_file_key = ''  # 文本文件键名初始化
        plaintext_file_exists = False  # 缓存中是否存在文本文件的标志
        # 尝试从缓存加载文本
        if self._file_cache_key:
            try:
                text = storage.load(self._file_cache_key).decode('utf-8')
                plaintext_file_exists = True
                # 如果缓存加载成功，直接返回包含缓存文本的文档
                return [Document(page_content=text)]
            except FileNotFoundError:
                pass  # 如果文件未找到，则继续从PDF加载
        documents = list(self.load())  # 加载PDF文档页面
        text_list = [document.page_content for document in documents]  # 提取所有页面的文本
        text = "\n\n".join(text_list)  # 将页面文本合并

        # 缓存合并后的文本
        if not plaintext_file_exists and plaintext_file_key:
            storage.save(plaintext_file_key, text.encode('utf-8'))

        return documents  # 返回解析后的文档列表

    def load(
            self,
    ) -> Iterator[Document]:
        """
        懒加载PDF文件的页面。

        Returns:
            Document迭代器，每个文档包含一个页面的内容和元数据。
        """
        blob = Blob.from_path(self._file_path)  # 从路径加载Blob对象
        yield from self.parse(blob)  # 解析Blob对象并yield每个页面的Document

    def parse(self, blob: Blob) -> Iterator[Document]:
        """
        懒惰地解析PDF Blob对象。

        Args:
            blob: PDF数据的Blob对象。

        Returns:
            Document迭代器，包含PDF页面的内容和元数据。
        """
        import pypdfium2  # 引入pypdfium2库用于解析PDF

        with blob.as_bytes_io() as file_path:  # 将Blob对象作为二进制IO
            pdf_reader = pypdfium2.PdfDocument(file_path, autoclose=True)  # 创建PDF阅读器
            try:
                for page_number, page in enumerate(pdf_reader):  # 遍历PDF页面
                    text_page = page.get_textpage()  # 获取文本页面
                    content = text_page.get_text_range()  # 提取文本范围
                    text_page.close()  # 关闭文本页面
                    page.close()  # 关闭PDF页面
                    metadata = {"source": blob.source, "page": page_number}  # 创建元数据
                    yield Document(page_content=content, metadata=metadata)  # yield文档对象
            finally:
                pdf_reader.close()  # 最终确保关闭PDF阅读器