"""Abstract interface for document loader implementations."""
from abc import ABC, abstractmethod


class BaseExtractor(ABC):
    """文件提取接口。

    本类作为提取文件的抽象基类(ABC)，定义了extract()方法作为一个抽象方法，
    要求任何具体实现提供文件提取的逻辑。
    """

    @abstractmethod
    def extract(self):
        """提取文件。

        本方法为一个抽象方法，需要在派生类中予以实现。其目的是提供提取文件的逻辑。
        此处未提供任何实现，直接在BaseExtractor实例上调用此方法将抛出NotImplementedError异常。
        """
        raise NotImplementedError