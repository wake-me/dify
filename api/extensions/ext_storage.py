from collections.abc import Generator
from typing import Union

from flask import Flask

from extensions.storage.aliyun_storage import AliyunStorage
from extensions.storage.azure_storage import AzureStorage
from extensions.storage.google_storage import GoogleStorage
from extensions.storage.local_storage import LocalStorage
from extensions.storage.oci_storage import OCIStorage
from extensions.storage.s3_storage import S3Storage
from extensions.storage.tencent_storage import TencentStorage


class Storage:
    def __init__(self):
        self.storage_runner = None

    def init_app(self, app: Flask):
        storage_type = app.config.get("STORAGE_TYPE")
        if storage_type == "s3":
            self.storage_runner = S3Storage(app=app)
        elif storage_type == "azure-blob":
            self.storage_runner = AzureStorage(app=app)
        elif storage_type == "aliyun-oss":
            self.storage_runner = AliyunStorage(app=app)
        elif storage_type == "google-storage":
            self.storage_runner = GoogleStorage(app=app)
        elif storage_type == "tencent-cos":
            self.storage_runner = TencentStorage(app=app)
        elif storage_type == "oci-storage":
            self.storage_runner = OCIStorage(app=app)
        else:
            self.storage_runner = LocalStorage(app=app)

    def save(self, filename, data):
        self.storage_runner.save(filename, data)

    def load(self, filename: str, stream: bool = False) -> Union[bytes, Generator]:
        """
        根据指定的文件名加载文件内容。
        
        参数:
        - filename: str，要加载的文件的名称。
        - stream: bool，是否以流模式加载文件。默认为False，如果为True，则以流模式加载。
        
        返回值:
        - Union[bytes, Generator]，根据stream参数的不同，返回内容不同。
        如果stream为True，返回一个生成器（Generator），用于逐块读取文件内容。
        如果stream为False，返回文件的全部内容（bytes）。
        """
        if stream:
            # 以流模式加载文件
            return self.load_stream(filename)
        else:
            # 一次性加载文件全部内容
            return self.load_once(filename)

    def load_once(self, filename: str) -> bytes:
        return self.storage_runner.load_once(filename)

    def load_stream(self, filename: str) -> Generator:
        return self.storage_runner.load_stream(filename)

    def download(self, filename, target_filepath):
        self.storage_runner.download(filename, target_filepath)

    def exists(self, filename):
        return self.storage_runner.exists(filename)

    def delete(self, filename):
        return self.storage_runner.delete(filename)


# 创建一个Storage实例
storage = Storage()

def init_app(app: Flask):
    """
    初始化Flask应用。

    参数:
    - app: Flask应用实例，即将被初始化的Flask应用。

    返回值:
    - 无
    """
    storage.init_app(app)  # 使用storage实例初始化Flask应用