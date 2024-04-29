"""Document loader helpers."""

import concurrent.futures
from typing import NamedTuple, Optional, cast


# 定义一个文件编码信息的命名元组
class FileEncoding(NamedTuple):
    """
    表示文件编码的命名元组。

    参数:
    - encoding: Optional[str] - 文件的编码格式。
    - confidence: float - 对编码格式的置信度。
    - language: Optional[str] - 文件的语言。

    返回值:
    - 无
    """

    encoding: Optional[str]
    """文件的编码格式。"""
    confidence: float
    """对编码格式的置信度。"""
    language: Optional[str]
    """文件的语言。"""

def detect_file_encodings(file_path: str, timeout: int = 5) -> list[FileEncoding]:
    """
    尝试检测文件的编码。

    返回一个`FileEncoding`元组的列表，其中包含按置信度排序的检测到的编码。

    参数:
        file_path: 需要检测编码的文件的路径。
        timeout: 编码检测的超时时间（秒）。

    返回值:
        检测到的编码列表，按置信度从高到低排序。
    """
    import chardet

    def read_and_detect(file_path: str) -> list[dict]:
        """
        读取文件并使用chardet库检测文件的编码。

        参数:
            file_path: 需要检测编码的文件路径。

        返回值:
            检测到的编码信息字典列表。
        """
        with open(file_path, "rb") as f:
            rawdata = f.read()
        return cast(list[dict], chardet.detect_all(rawdata))

    # 使用并发执行器以异步方式检测文件编码
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(read_and_detect, file_path)
        try:
            encodings = future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(
                f"Timeout reached while detecting encoding for {file_path}"
            )

    # 如果所有检测结果都没有给出编码信息，则抛出运行时错误
    if all(encoding["encoding"] is None for encoding in encodings):
        raise RuntimeError(f"Could not detect encoding for {file_path}")
    # 筛选出有编码信息的结果，并转换为`FileEncoding`对象列表返回
    return [FileEncoding(**enc) for enc in encodings if enc["encoding"] is not None]
