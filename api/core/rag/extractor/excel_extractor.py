"""Abstract interface for document loader implementations."""
from typing import Optional

import pandas as pd
import xlrd

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
        """解析Excel文件并返回Document对象列表。

        Returns:
            从Excel文件解析得到的Document对象列表。
        """
        # 根据文件扩展名确定文件类型，并调用相应的提取方法
        if self._file_path.endswith('.xls'):
            return self._extract4xls()
        elif self._file_path.endswith('.xlsx'):
            return self._extract4xlsx()

    def _extract4xls(self) -> list[Document]:
        """从.xls文件中提取数据并返回Document对象列表。

        Returns:
            包含从.xls文件中提取数据的Document对象列表。
        """
        wb = xlrd.open_workbook(filename=self._file_path)
        documents = []
        # 遍历工作簿中的所有表单
        for sheet in wb.sheets():
            for row_index, row in enumerate(sheet.get_rows(), start=1):
                row_header = None
                if self.is_blank_row(row):
                    continue
                if row_header is None:
                    row_header = row
                    continue
                # 从每一行中提取数据并创建Document对象
                item_arr = []
                for index, cell in enumerate(row):
                    txt_value = str(cell.value)
                    item_arr.append(f'{row_header[index].value}:{txt_value}')
                item_str = "\n".join(item_arr)
                document = Document(page_content=item_str, metadata={'source': self._file_path})
                documents.append(document)
        return documents

    def _extract4xlsx(self) -> list[Document]:
        """从.xlsx文件中提取数据并返回Document对象列表。

        Returns:
            包含从.xlsx文件中提取数据的Document对象列表。
        """
        data = []
        # 使用Pandas读取Excel文件中的每个工作表
        xls = pd.ExcelFile(self._file_path)
        for sheet_name in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet_name)

            # 移除全为空值的行
            df.dropna(how='all', inplace=True)

            # 为每行数据创建一个Document对象
            for _, row in df.iterrows():
                item = ';'.join(f'{k}:{v}' for k, v in row.items() if pd.notna(v))
                document = Document(page_content=item, metadata={'source': self._file_path})
                data.append(document)
        return data

    @staticmethod
    def is_blank_row(row):
        """
        判断给定行是否为空行。

        Args:
            row: 待检查的行。

        Returns:
            若行为空则返回True，否则返回False。
        """
        # 检查行中是否有非空值的单元格
        for cell in row:
            if cell.value is not None and cell.value != '':
                return False
        return True