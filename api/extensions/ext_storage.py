import os
import shutil
from collections.abc import Generator
from contextlib import closing
from datetime import datetime, timedelta
from typing import Union

import boto3
from azure.storage.blob import AccountSasPermissions, BlobServiceClient, ResourceTypes, generate_account_sas
from botocore.client import Config
from botocore.exceptions import ClientError
from flask import Flask


class Storage:
    def __init__(self):
        self.storage_type = None  # 存储类型
        self.bucket_name = None  # 存储桶名称
        self.client = None  # 客户端对象
        self.folder = None  # 存储目录

    def init_app(self, app: Flask):
        """
        初始化应用程序与存储配置。
        
        参数:
        - app: Flask应用实例，用于获取配置信息。
        
        根据配置的存储类型初始化存储连接或路径。支持的存储类型包括's3'和'azure-blob'，
        以及默认的本地文件存储。对于's3'和'azure-blob'，需要相应的配置信息来建立连接；
        对于本地存储，需要指定存储路径。
        """
        self.storage_type = app.config.get('STORAGE_TYPE')
        if self.storage_type == 's3':
            # 配置S3存储
            self.bucket_name = app.config.get('S3_BUCKET_NAME')
            self.client = boto3.client(
                's3',
                aws_secret_access_key=app.config.get('S3_SECRET_KEY'),
                aws_access_key_id=app.config.get('S3_ACCESS_KEY'),
                endpoint_url=app.config.get('S3_ENDPOINT'),
                region_name=app.config.get('S3_REGION'),
                config=Config(s3={'addressing_style': app.config.get('S3_ADDRESS_STYLE')})
            )
        elif self.storage_type == 'azure-blob':
            # 配置Azure Blob存储
            self.bucket_name = app.config.get('AZURE_BLOB_CONTAINER_NAME')
            sas_token = generate_account_sas(
                account_name=app.config.get('AZURE_BLOB_ACCOUNT_NAME'),
                account_key=app.config.get('AZURE_BLOB_ACCOUNT_KEY'),
                resource_types=ResourceTypes(service=True, container=True, object=True),
                permission=AccountSasPermissions(read=True, write=True, delete=True, list=True, add=True, create=True),
                expiry=datetime.utcnow() + timedelta(hours=1)
            )
            self.client = BlobServiceClient(account_url=app.config.get('AZURE_BLOB_ACCOUNT_URL'),
                                            credential=sas_token)

        else:
            # 配置本地文件存储
            self.folder = app.config.get('STORAGE_LOCAL_PATH')
            if not os.path.isabs(self.folder):
                # 确保存储路径为绝对路径
                self.folder = os.path.join(app.root_path, self.folder)

    def save(self, filename, data):
        """
        根据存储类型将数据保存到指定的文件。
        
        参数:
        - filename: 要保存的文件名。
        - data: 要保存的数据。
        
        说明:
        - 根据`self.storage_type`的值，决定数据是保存到S3、Azure Blob存储，还是本地文件系统。
        """
        if self.storage_type == 's3':
            # 如果存储类型为S3，则使用S3客户端将数据上传到指定的存储桶中。
            self.client.put_object(Bucket=self.bucket_name, Key=filename, Body=data)
        elif self.storage_type == 'azure-blob':
            # 如果存储类型为Azure Blob，则使用Azure客户端将数据上传到指定的容器中。
            blob_container = self.client.get_container_client(container=self.bucket_name)
            blob_container.upload_blob(filename, data)
        else:
            # 如果存储类型既不是S3也不是Azure Blob，则将数据保存到本地文件系统。
            if not self.folder or self.folder.endswith('/'):
                filename = self.folder + filename
            else:
                filename = self.folder + '/' + filename

            # 确保文件所在的文件夹存在，如果不存在则创建。
            folder = os.path.dirname(filename)
            os.makedirs(folder, exist_ok=True)

            # 打开文件，以二进制写入模式将数据写入文件。
            with open(os.path.join(os.getcwd(), filename), "wb") as f:
                f.write(data)

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
        """
        从指定的存储类型（目前支持 s3 和 azure-blob，以及本地文件系统）中加载文件内容。
        
        参数:
        - filename: 需要加载的文件名，对于 s3 和 azure-blob，此名称应包括在存储桶或容器内的路径。
        
        返回值:
        - 文件内容的 bytes 对象。
        
        抛出:
        - FileNotFoundError: 如果文件不存在于指定位置。
        """
        if self.storage_type == 's3':
            # 尝试从 S3 存储桶中获取文件内容
            try:
                with closing(self.client) as client:
                    data = client.get_object(Bucket=self.bucket_name, Key=filename)['Body'].read()
            except ClientError as ex:
                if ex.response['Error']['Code'] == 'NoSuchKey':
                    raise FileNotFoundError("File not found")
                else:
                    raise
        elif self.storage_type == 'azure-blob':
            # 从 Azure Blob 存储中下载文件内容
            blob = self.client.get_container_client(container=self.bucket_name)
            blob = blob.get_blob_client(blob=filename)
            data = blob.download_blob().readall()
        else:
            # 从本地文件系统中读取文件内容
            if not self.folder or self.folder.endswith('/'):
                filename = self.folder + filename
            else:
                filename = self.folder + '/' + filename

            if not os.path.exists(filename):
                raise FileNotFoundError("File not found")

            with open(filename, "rb") as f:
                data = f.read()

        return data

    def load_stream(self, filename: str) -> Generator:
        """
        加载指定文件名的流数据。
        
        根据存储类型（s3或azure-blob或本地文件系统）从相应的存储位置加载文件，并以数据块的形式逐块返回其内容。
        
        参数:
        - filename: str，要加载的文件名。
        
        返回值:
        - Generator，一个生成器，逐块返回文件内容。
        """
        def generate(filename: str = filename) -> Generator:
            # 根据存储类型选择不同的数据加载方式
            if self.storage_type == 's3':
                # 从S3存储桶中加载文件
                try:
                    with closing(self.client) as client:
                        response = client.get_object(Bucket=self.bucket_name, Key=filename)
                        for chunk in response['Body'].iter_chunks():
                            yield chunk
                except ClientError as ex:
                    if ex.response['Error']['Code'] == 'NoSuchKey':
                        raise FileNotFoundError("File not found")
                    else:
                        raise
            elif self.storage_type == 'azure-blob':
                # 从Azure Blob存储中加载文件
                blob = self.client.get_blob_client(container=self.bucket_name, blob=filename)
                with closing(blob.download_blob()) as blob_stream:
                    while chunk := blob_stream.readall(4096):
                        yield chunk
            else:
                # 从本地文件系统加载文件
                if not self.folder or self.folder.endswith('/'):
                    filename = self.folder + filename
                else:
                    filename = self.folder + '/' + filename

                if not os.path.exists(filename):
                    raise FileNotFoundError("File not found")

                with open(filename, "rb") as f:
                    while chunk := f.read(4096):  # 从文件中读取数据块
                        yield chunk

        return generate()

    def download(self, filename, target_filepath):
        """
        下载存储在不同存储服务（如S3或Azure Blob存储）或本地文件系统的文件。
        
        参数:
        - filename: 存储在存储服务或本地文件系统中的文件名称。
        - target_filepath: 文件下载后的目标路径。
        
        返回值: 无。
        """
        if self.storage_type == 's3':
            # 使用S3下载文件
            with closing(self.client) as client:
                client.download_file(self.bucket_name, filename, target_filepath)
        elif self.storage_type == 'azure-blob':
            # 使用Azure Blob存储下载文件
            blob = self.client.get_blob_client(container=self.bucket_name, blob=filename)
            with open(target_filepath, "wb") as my_blob:
                blob_data = blob.download_blob()
                blob_data.readinto(my_blob)
        else:
            # 处理本地文件系统的文件下载
            if not self.folder or self.folder.endswith('/'):
                filename = self.folder + filename
            else:
                filename = self.folder + '/' + filename

            if not os.path.exists(filename):
                raise FileNotFoundError("File not found")

            shutil.copyfile(filename, target_filepath)

    def exists(self, filename):
        """
        检查文件是否存在。
        
        根据存储类型（s3、azure-blob或本地文件系统）在不同的存储位置检查文件是否存在。
        
        参数:
        - filename: 要检查是否存在的文件名。
        
        返回值:
        - 存在则返回True，否则返回False。
        """
        if self.storage_type == 's3':
            # 对于s3存储，尝试获取对象元数据来确认文件存在
            with closing(self.client) as client:
                try:
                    client.head_object(Bucket=self.bucket_name, Key=filename)
                    return True
                except:
                    return False
        elif self.storage_type == 'azure-blob':
            # 对于azure-blob存储，直接调用exists方法检查文件是否存在
            blob = self.client.get_blob_client(container=self.bucket_name, blob=filename)
            return blob.exists()
        else:
            # 对于本地文件系统，拼接文件路径并使用os.path.exists检查文件是否存在
            if not self.folder or self.folder.endswith('/'):
                filename = self.folder + filename
            else:
                filename = self.folder + '/' + filename

            return os.path.exists(filename)

    def delete(self, filename):
        """
        根据存储类型删除文件。
        
        该方法根据实例的存储类型（s3或azure-blob或本地文件系统）来删除指定的文件。
        如果存储类型是s3或azure-blob，将使用相应的API删除对象。
        如果存储类型是本地文件系统，将删除指定路径下的文件。
        
        参数:
        - filename: 需要删除的文件名或路径。对于本地文件系统，如果设置了文件夹路径，则该文件名是相对于该路径的。
        
        返回值:
        - 无
        """
        if self.storage_type == 's3':
            # 使用s3客户端删除对象
            self.client.delete_object(Bucket=self.bucket_name, Key=filename)
        elif self.storage_type == 'azure-blob':
            # 获取blob容器客户端并删除指定的blob
            blob_container = self.client.get_container_client(container=self.bucket_name)
            blob_container.delete_blob(filename)
        else:
            # 处理本地文件系统的文件删除
            if not self.folder or self.folder.endswith('/'):
                filename = self.folder + filename
            else:
                filename = self.folder + '/' + filename
            if os.path.exists(filename):
                # 如果文件存在，则删除它
                os.remove(filename)


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