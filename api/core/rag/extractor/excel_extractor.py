"""Abstract interface for document loader implementations."""
import os
from typing import Optional

import pandas as pd

from core.rag.extractor.extractor_base import BaseExtractor
from core.rag.models.document import Document


class ExcelExtractor(BaseExtractor):
    """加载Excel文件。

    Args:
        file_path: 要加载文件的路径。
    """

    def __init__(
            self,
            file_path: str,
            encoding: Optional[str] = None,
            autodetect_encoding: bool = False
    ):
        """初始化，传入文件路径。

        Args:
            file_path: 待加载Excel文件的路径。
            encoding: 文件编码。若未指定，默认为None。
            autodetect_encoding: 是否自动检测文件编码。
        """
        self._file_path = file_path
        self._encoding = encoding
        self._autodetect_encoding = autodetect_encoding

    def extract(self) -> list[Document]:
        """ Load from Excel file in xls or xlsx format using Pandas."""
        documents = []
        # Determine the file extension
        file_extension = os.path.splitext(self._file_path)[-1].lower()
        # Read each worksheet of an Excel file using Pandas
        if file_extension == '.xlsx':
            excel_file = pd.ExcelFile(self._file_path, engine='openpyxl')
        elif file_extension == '.xls':
            excel_file = pd.ExcelFile(self._file_path, engine='xlrd')
        else:
            raise ValueError(f"Unsupported file extension: {file_extension}")
        for sheet_name in excel_file.sheet_names:
            df: pd.DataFrame = excel_file.parse(sheet_name=sheet_name)

            # 移除全为空值的行
            df.dropna(how='all', inplace=True)

            # transform each row into a Document
            documents += [Document(page_content=';'.join(f'"{k}":"{v}"' for k, v in row.items() if pd.notna(v)),
                                   metadata={'source': self._file_path},
                                   ) for _, row in df.iterrows()]

        return documents
