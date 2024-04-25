"""Abstract interface for document loader implementations."""

from core.rag.index_processor.constant.index_type import IndexType
from core.rag.index_processor.index_processor_base import BaseIndexProcessor
from core.rag.index_processor.processor.paragraph_index_processor import ParagraphIndexProcessor
from core.rag.index_processor.processor.qa_index_processor import QAIndexProcessor


class IndexProcessorFactory:
    """
    初始化索引处理器工厂类。
    """

    def __init__(self, index_type: str):
        """
        初始化索引处理器工厂实例。

        参数:
        index_type (str): 索引类型标识字符串。
        """
        self._index_type = index_type

    def init_index_processor(self) -> BaseIndexProcessor:
        """
        根据指定的索引类型初始化相应的索引处理器实例。

        返回:
        BaseIndexProcessor: 初始化后的索引处理器实例。

        异常:
        ValueError: 当索引类型未指定或不支持时抛出。
        """
        if not self._index_type:
            raise ValueError("Index type must be specified.")  # 索引类型必须指定

        if self._index_type == IndexType.PARAGRAPH_INDEX.value:
            return ParagraphIndexProcessor()  # 初始化段落索引处理器
        elif self._index_type == IndexType.QA_INDEX.value:
            return QAIndexProcessor()  # 初始化问答索引处理器
        else:
            raise ValueError(f"Index type {self._index_type} is not supported.")  # 指定的索引类型不支持