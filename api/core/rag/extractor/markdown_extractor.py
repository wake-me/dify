"""Abstract interface for document loader implementations."""
import re
from typing import Optional, cast

from core.rag.extractor.extractor_base import BaseExtractor
from core.rag.extractor.helpers import detect_file_encodings
from core.rag.models.document import Document


class MarkdownExtractor(BaseExtractor):
    """
    用于加载 Markdown 文件的类。

    Args:
        file_path (str): 要加载的文件路径。
        remove_hyperlinks (bool, optional): 是否移除超链接，默认为 True。
        remove_images (bool, optional): 是否移除图片，默认为 True。
        encoding (Optional[str], optional): 文件的编码格式，默认为 None，如果为 None，则会自动检测编码。
        autodetect_encoding (bool, optional): 是否自动检测文件的编码，默认为 True。
    """

    def __init__(
            self,
            file_path: str,
            remove_hyperlinks: bool = True,
            remove_images: bool = True,
            encoding: Optional[str] = None,
            autodetect_encoding: bool = True,
    ):
        """
        初始化 MarkdownExtractor 实例。

        Args:
            file_path (str): 要加载的文件路径。
            remove_hyperlinks (bool, optional): 是否在提取内容时移除超链接，默认为 True。
            remove_images (bool, optional): 是否在提取内容时移除图片，默认为 True。
            encoding (Optional[str], optional): 指定文件的编码，默认为 None。如果为 None，则会尝试自动检测编码。
            autodetect_encoding (bool, optional): 是否开启自动检测文件编码的功能，默认为 True。
        """
        self._file_path = file_path
        self._remove_hyperlinks = remove_hyperlinks
        self._remove_images = remove_images
        self._encoding = encoding
        self._autodetect_encoding = autodetect_encoding

    def extract(self) -> list[Document]:
        """
        从文件路径加载 Markdown 内容，并将其转换为 Document 对象列表。

        Returns:
            list[Document]: 包含从 Markdown 文件提取的文档内容的列表。每个元素都是一个 Document 实例，
            其中包含 page_content 属性，该属性包含了提取的文本内容。
        """
        # 从文件中解析出标题和内容的元组列表
        tups = self.parse_tups(self._file_path)
        documents = []
        # 遍历解析得到的元组，根据是否有标题，将内容包装成 Document 对象
        for header, value in tups:
            value = value.strip()  # 移除前后空白
            if header is None:
                # 如果没有标题，则直接将内容作为页面内容
                documents.append(Document(page_content=value))
            else:
                # 如果有标题，则在内容前添加标题
                documents.append(Document(page_content=f"\n\n{header}\n{value}"))

        return documents
    def markdown_to_tups(self, markdown_text: str) -> list[tuple[Optional[str], str]]:
        """
        将 Markdown 文本转换为元组列表的字典形式。

        每个元组包含一个可选的标题（字符串）和该标题下的文本（字符串）。标题根据在 Markdown 中的级别进行递进，
        从一级标题到六级标题，使用数字 # 进行标识。这个方法将所有的标题和相应的文本内容捕获，并以标题为键，
        文本为值的形式存储在列表中的元组里。

        参数:
            markdown_text: str - 输入的 Markdown 文本。

        返回值:
            list[tuple[Optional[str], str]] - 包含标题和对应文本的元组列表。每个元组的第一个元素是标题（可能是 None），
            第二个元素是该标题下的文本内容。
        """

        # 初始化用于存储转换结果的列表
        markdown_tups: list[tuple[Optional[str], str]] = []
        # 将 Markdown 文本按行分割
        lines = markdown_text.split("\n")

        # 用于当前标题和文本内容的临时变量
        current_header = None
        current_text = ""

        # 遍历分割后的每行文本
        for line in lines:
            # 检查当前行是否为标题
            header_match = re.match(r"^#+\s", line)
            if header_match:
                # 如果是标题，则将之前的标题和文本内容添加到结果列表中
                if current_header is not None:
                    markdown_tups.append((current_header, current_text))

                # 更新当前标题和文本内容
                current_header = line
                current_text = ""
            else:
                # 如果不是标题，则将当前行添加到当前文本内容中
                current_text += line + "\n"
        # 将最后一部分的标题和文本内容添加到结果列表中
        markdown_tups.append((current_header, current_text))

        # 如果存在标题，则处理标题和文本，移除标题中的 # 字符和文本中的 HTML 标签
        if current_header is not None:
            markdown_tups = [
                (re.sub(r"#", "", cast(str, key)).strip(), re.sub(r"<.*?>", "", value))
                for key, value in markdown_tups
            ]
        else:
            # 如果没有标题，则仅处理文本，移除换行符
            markdown_tups = [
                (key, re.sub("\n", "", value)) for key, value in markdown_tups
            ]

        return markdown_tups

    def remove_images(self, content: str) -> str:
        """
        从给定的 Markdown 内容中移除所有图片。

        本函数利用正则表达式查找并移除提供的 Markdown 内容中所有形式为 '[[image_path]]' 的图片占位符。

        参数:
        - content (str): 需要移除图片的 Markdown 内容。

        返回:
        - str: 去掉所有图片后的修改后 Markdown 内容。
        """
        # 匹配双括号包围的图片路径模式
        pattern = r"!{1}\[\[(.*)\]\]"
        # 将所有匹配到的模式替换为空字符串
        content = re.sub(pattern, "", content)
        return content

    def remove_hyperlinks(self, content: str) -> str:
        """
        从给定的内容中移除超链接。

        该函数利用正则表达式查找并移除内容中形如 `[链接文字](链接地址)` 的超链接模式，
        只保留链接的文字部分。

        参数:
        - content (str): 包含待处理超链接的文本内容。

        返回:
        - str: 已移除所有超链接的处理后内容。
        """
        # 定义用于查找超链接的正则表达式模式
        pattern = r"\[(.*?)\]\((.*?)\)"
        # 使用 re.sub 替换超链接，仅保留其文字部分
        content = re.sub(pattern, r"\1", content)
        return content

    def parse_tups(self, filepath: str) -> list[tuple[Optional[str], str]]:
        """
        从指定文件解析内容，并将其转换成元组列表。

        参数:
        filepath: str - 需要解析的文件的路径。

        返回值:
        list[tuple[Optional[str], str]] - 元组列表，每个元组包含一个可选的字符串和一个字符串。
        """
        content = ""
        try:
            # 尝试以预设编码打开文件
            with open(filepath, encoding=self._encoding) as f:
                content = f.read()
        except UnicodeDecodeError as e:
            # 如果出现编码错误，根据配置自动检测并尝试使用检测到的编码打开文件
            if self._autodetect_encoding:
                detected_encodings = detect_file_encodings(filepath)
                for encoding in detected_encodings:
                    try:
                        with open(filepath, encoding=encoding.encoding) as f:
                            content = f.read()
                        break
                    except UnicodeDecodeError:
                        continue
            else:
                # 如果不自动检测编码，则直接抛出错误
                raise RuntimeError(f"Error loading {filepath}") from e
        except Exception as e:
            # 处理打开文件时的其他异常
            raise RuntimeError(f"Error loading {filepath}") from e

        # 根据配置移除超链接
        if self._remove_hyperlinks:
            content = self.remove_hyperlinks(content)

        # 根据配置移除图片
        if self._remove_images:
            content = self.remove_images(content)

        # 将解析的内容转换成元组列表并返回
        return self.markdown_to_tups(content)
