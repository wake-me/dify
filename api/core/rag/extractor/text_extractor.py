"""Abstract interface for document loader implementations."""
from typing import Optional

from core.rag.extractor.extractor_base import BaseExtractor
from core.rag.extractor.helpers import detect_file_encodings
from core.rag.models.document import Document


class TextExtractor(BaseExtractor):
    """
    用于加载文本文件的提取器类。

    Args:
        file_path (str): 要加载的文件的路径。
    """

    def __init__(
            self,
            file_path: str,
            encoding: Optional[str] = None,
            autodetect_encoding: bool = False
    ):
        """
        初始化提取器，设置文件路径、编码方式和是否自动检测编码。

        Args:
            file_path (str): 文件路径。
            encoding (Optional[str], optional): 文件的编码方式，默认为None。
            autodetect_encoding (bool, optional): 是否自动检测文件的编码，默认为False。
        """
        self._file_path = file_path  # 文件路径
        self._encoding = encoding  # 文件编码
        self._autodetect_encoding = autodetect_encoding  # 是否自动检测编码

    def extract(self) -> list[Document]:
        """
        从文件路径加载文本，返回包含文本内容的Document对象列表。

        Returns:
            list[Document]: 包含从文件中提取的文本内容和元数据的Document对象列表。
        """
        text = ""
        try:
            # 尝试使用指定编码打开文件
            with open(self._file_path, encoding=self._encoding) as f:
                text = f.read()
        except UnicodeDecodeError as e:
            if self._autodetect_encoding:
                # 如果设置为自动检测编码，则尝试检测并使用检测到的编码打开文件
                detected_encodings = detect_file_encodings(self._file_path)
                for encoding in detected_encodings:
                    try:
                        with open(self._file_path, encoding=encoding.encoding) as f:
                            text = f.read()
                        break  # 如果成功打开文件，则跳出循环
                    except UnicodeDecodeError:
                        continue  # 如果打开文件失败，则尝试下一个检测到的编码
            else:
                # 如果未设置自动检测编码且打开文件失败，则抛出运行时错误
                raise RuntimeError(f"Error loading {self._file_path}") from e
        except Exception as e:
            # 处理其他可能的异常
            raise RuntimeError(f"Error loading {self._file_path}") from e

        # 创建并返回包含文本内容和元数据的Document对象
        metadata = {"source": self._file_path}  # 元数据包括文件路径
        return [Document(page_content=text, metadata=metadata)]