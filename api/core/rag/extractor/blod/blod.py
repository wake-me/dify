"""Schema for Blobs and Blob Loaders.

The goal is to facilitate decoupling of content loading from content parsing code.

In addition, content loading code should provide a lazy loading interface by default.
"""
from __future__ import annotations

import contextlib
import mimetypes
from abc import ABC, abstractmethod
from collections.abc import Generator, Iterable, Mapping
from io import BufferedReader, BytesIO
from pathlib import PurePath
from typing import Any, Optional, Union

from pydantic import BaseModel, ConfigDict, model_validator

PathLike = Union[str, PurePath]


class Blob(BaseModel):
    """
    用于表示原始数据的Blob类，可以通过引用或值来表示数据。

    提供了不同表示形式的接口，以及帮助解耦数据加载器的开发和原始数据的下游解析。

    受启发于：https://developer.mozilla.org/en-US/docs/Web/API/Blob
    """

    data: Union[bytes, str, None] = None  # Raw data
    mimetype: Optional[str] = None  # Not to be confused with a file extension
    encoding: str = "utf-8"  # Use utf-8 as default encoding, if decoding to string
    # Location where the original content was found
    # Represent location on the local file system
    # Useful for situations where downstream code assumes it must work with file paths
    # rather than in-memory content.
    path: Optional[PathLike] = None
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    @property
    def source(self) -> Optional[str]:
        """
        如果已知，则返回blob的源位置字符串，否则返回None。
        """
        return str(self.path) if self.path else None

    @model_validator(mode="before")
    @classmethod
    def check_blob_is_valid(cls, values: Mapping[str, Any]) -> Mapping[str, Any]:
        """
        验证是否提供了data或path。
        """
        if "data" not in values and "path" not in values:
            raise ValueError("Either data or path must be provided")
        return values

    def as_string(self) -> str:
        """
        以字符串形式读取数据。
        """
        if self.data is None and self.path:
            with open(str(self.path), encoding=self.encoding) as f:
                return f.read()
        elif isinstance(self.data, bytes):
            return self.data.decode(self.encoding)
        elif isinstance(self.data, str):
            return self.data
        else:
            raise ValueError(f"Unable to get string for blob {self}")

    def as_bytes(self) -> bytes:
        """
        以字节形式读取数据。
        """
        if isinstance(self.data, bytes):
            return self.data
        elif isinstance(self.data, str):
            return self.data.encode(self.encoding)
        elif self.data is None and self.path:
            with open(str(self.path), "rb") as f:
                return f.read()
        else:
            raise ValueError(f"Unable to get bytes for blob {self}")

    @contextlib.contextmanager
    def as_bytes_io(self) -> Generator[Union[BytesIO, BufferedReader], None, None]:
        """
        以字节流形式读取数据。
        """
        if isinstance(self.data, bytes):
            yield BytesIO(self.data)
        elif self.data is None and self.path:
            with open(str(self.path), "rb") as f:
                yield f
        else:
            raise NotImplementedError(f"Unable to convert blob {self}")

    @classmethod
    def from_path(
        cls,
        path: PathLike,
        *,
        encoding: str = "utf-8",
        mime_type: Optional[str] = None,
        guess_type: bool = True,
    ) -> Blob:
        """
        从路径对象加载blob。

        Args:
            path: 文件读取的路径对象
            encoding: 如果解码字节为字符串时使用的编码
            mime_type: 如果提供，将设置为数据的mime类型
            guess_type: 如果为True，则会从文件扩展名猜测mime类型

        Returns:
            Blob实例
        """
        if mime_type is None and guess_type:
            _mimetype = mimetypes.guess_type(path)[0] if guess_type else None
        else:
            _mimetype = mime_type
        return cls(data=None, mimetype=_mimetype, encoding=encoding, path=path)

    @classmethod
    def from_data(
        cls,
        data: Union[str, bytes],
        *,
        encoding: str = "utf-8",
        mime_type: Optional[str] = None,
        path: Optional[str] = None,
    ) -> Blob:
        """
        从内存中的数据初始化blob。

        Args:
            data: 与blob关联的内存数据
            encoding: 如果解码字节为字符串时使用的编码
            mime_type: 如果提供，将设置为数据的mime类型
            path: 如果提供，将设置为数据来源的路径

        Returns:
            Blob实例
        """
        return cls(data=data, mimetype=mime_type, encoding=encoding, path=path)

    def __repr__(self) -> str:
        """
        定义blob的表示形式。
        """
        str_repr = f"Blob {id(self)}"
        if self.source:
            str_repr += f" {self.source}"
        return str_repr


class BlobLoader(ABC):
    """
    Blob加载器的抽象接口实现。

    实现者应能够根据某些标准从数据源系统加载原始内容，并懒惰地将原始内容作为Blob对象的流返回。
    """

    @abstractmethod
    def yield_blobs(
        self,
    ) -> Iterable[Blob]:
        """
        返回Blob对象的懒加载器。

        Returns:
            Blob对象的生成器
        """