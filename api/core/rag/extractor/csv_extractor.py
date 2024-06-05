"""Abstract interface for document loader implementations."""
import csv
from typing import Optional

import pandas as pd

from core.rag.extractor.extractor_base import BaseExtractor
from core.rag.extractor.helpers import detect_file_encodings
from core.rag.models.document import Document


class CSVExtractor(BaseExtractor):
    """加载CSV文件。

    Args:
        file_path: 文件加载路径。
    """

    def __init__(
            self,
            file_path: str,
            encoding: Optional[str] = None,
            autodetect_encoding: bool = False,
            source_column: Optional[str] = None,
            csv_args: Optional[dict] = None,
    ):
        """使用文件路径进行初始化。

        Args:
            file_path: 文件路径。
            encoding: 文件编码，默认为None。
            autodetect_encoding: 是否自动检测编码，默认为False。
            source_column: 数据源列名，默认为None。
            csv_args: 传递给csv读取函数的其他参数，默认为空字典。
        """

        self._file_path = file_path
        self._encoding = encoding
        self._autodetect_encoding = autodetect_encoding
        self.source_column = source_column
        self.csv_args = csv_args or {}

    def extract(self) -> list[Document]:
        """将数据加载到文档对象中。

        Returns:
            Document对象列表。
        """

        docs = []
        try:
            # 以指定编码打开CSV文件
            with open(self._file_path, newline="", encoding=self._encoding) as csvfile:
                docs = self._read_from_file(csvfile)
        except UnicodeDecodeError as e:
            if self._autodetect_encoding:
                # 自动检测文件编码并尝试打开
                detected_encodings = detect_file_encodings(self._file_path)
                for encoding in detected_encodings:
                    try:
                        with open(self._file_path, newline="", encoding=encoding.encoding) as csvfile:
                            docs = self._read_from_file(csvfile)
                        break
                    except UnicodeDecodeError:
                        continue
            else:
                # 编码无法识别时抛出错误
                raise RuntimeError(f"Error loading {self._file_path}") from e

        return docs

    def _read_from_file(self, csvfile) -> list[Document]:
        """从文件中读取数据并转换为Document对象。

        Args:
            csvfile: CSV文件对象。

        Returns:
            Document对象列表。
        """

        docs = []
        try:
            # load csv file into pandas dataframe
            df = pd.read_csv(csvfile, on_bad_lines='skip', **self.csv_args)

            # 检查源列是否存在
            if self.source_column and self.source_column not in df.columns:
                raise ValueError(f"Source column '{self.source_column}' not found in CSV file.")

            # 创建Document对象
            for i, row in df.iterrows():
                content = ";".join(f"{col.strip()}: {str(row[col]).strip()}" for col in df.columns)
                source = row[self.source_column] if self.source_column else ''
                metadata = {"source": source, "row": i}
                doc = Document(page_content=content, metadata=metadata)
                docs.append(doc)
        except csv.Error as e:
            # CSV文件读取错误时抛出
            raise e

        return docs
