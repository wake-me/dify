from collections.abc import Mapping, Sequence
from typing import Any, Union

import requests

from core.app.app_config.entities import FileExtraConfig
from core.file.file_obj import FileBelongsTo, FileTransferMethod, FileType, FileVar
from extensions.ext_database import db
from models.account import Account
from models.model import EndUser, MessageFile, UploadFile
from services.file_service import IMAGE_EXTENSIONS


class MessageFileParser:
    """
    消息文件解析器类，用于解析指定租户和应用的消息文件。

    参数:
    tenant_id (str): 租户标识，用于指定要解析的消息文件所属的租户。
    app_id (str): 应用标识，用于指定要解析的消息文件所属的应用。

    返回:
    None
    """

    def __init__(self, tenant_id: str, app_id: str) -> None:
        self.tenant_id = tenant_id  # 租户标识
        self.app_id = app_id  # 应用标识

    def validate_and_transform_files_arg(self, files: Sequence[Mapping[str, Any]], file_extra_config: FileExtraConfig,
                                         user: Union[Account, EndUser]) -> list[FileVar]:
        """
        验证并转换文件参数

        :param files: 文件列表，每个文件由字典表示，包含文件类型、传输方法等信息
        :param file_extra_config: 文件额外配置对象，包含图片配置等
        :param user: 用户对象，可以是账户或终端用户
        :return: 转换后的文件对象列表
        """
        # 遍历文件列表，逐个验证文件的格式、类型、传输方法等
        for file in files:
            if not isinstance(file, dict):
                raise ValueError('Invalid file format, must be dict')
            if not file.get('type'):
                raise ValueError('Missing file type')
            FileType.value_of(file.get('type'))
            if not file.get('transfer_method'):
                raise ValueError('Missing file transfer method')
            FileTransferMethod.value_of(file.get('transfer_method'))
            if file.get('transfer_method') == FileTransferMethod.REMOTE_URL.value:
                if not file.get('url'):
                    raise ValueError('Missing file url')
                if not file.get('url').startswith('http'):
                    raise ValueError('Invalid file url')
            if file.get('transfer_method') == FileTransferMethod.LOCAL_FILE.value and not file.get('upload_file_id'):
                raise ValueError('Missing file upload_file_id')
            if file.get('transform_method') == FileTransferMethod.TOOL_FILE.value and not file.get('tool_file_id'):
                raise ValueError('Missing file tool_file_id')

        # 将文件列表转换为文件对象
        type_file_objs = self._to_file_objs(files, file_extra_config)

        # 验证转换后的文件对象
        new_files = []
        for file_type, file_objs in type_file_objs.items():
            if file_type == FileType.IMAGE:
                # 获取图片配置并验证图片文件数量是否超出限制
                image_config = file_extra_config.image_config
                if not image_config:
                    continue
                if len(files) > image_config['number_limits']:
                    raise ValueError(f"Number of image files exceeds the maximum limit {image_config['number_limits']}")

                for file_obj in file_objs:
                    # 验证传输方法和文件类型是否有效
                    if file_obj.transfer_method.value not in image_config['transfer_methods']:
                        raise ValueError(f'Invalid transfer method: {file_obj.transfer_method.value}')
                    if file_obj.type != FileType.IMAGE:
                        raise ValueError(f'Invalid file type: {file_obj.type}')

                    if file_obj.transfer_method == FileTransferMethod.REMOTE_URL:
                        # 验证远程URL是否有效且为图片
                        result, error = self._check_image_remote_url(file_obj.url)
                        if result is False:
                            raise ValueError(error)
                    elif file_obj.transfer_method == FileTransferMethod.LOCAL_FILE:
                        # 根据上传文件ID获取上传文件对象，并验证其归属和合法性
                        upload_file = (db.session.query(UploadFile)
                                    .filter(
                            UploadFile.id == file_obj.related_id,
                            UploadFile.tenant_id == self.tenant_id,
                            UploadFile.created_by == user.id,
                            UploadFile.created_by_role == ('account' if isinstance(user, Account) else 'end_user'),
                            UploadFile.extension.in_(IMAGE_EXTENSIONS)
                        ).first())
                        if not upload_file:
                            raise ValueError('Invalid upload file')

                    new_files.append(file_obj)

        # 返回所有验证通过的文件对象
        return new_files

    def transform_message_files(self, files: list[MessageFile], file_extra_config: FileExtraConfig) -> list[FileVar]:
        """
        transform message files

        :param files:
        :param file_extra_config:
        :return:
        """
        # transform files to file objs
        type_file_objs = self._to_file_objs(files, file_extra_config)

        # return all file objs
        return [file_obj for file_objs in type_file_objs.values() for file_obj in file_objs]

    def _to_file_objs(self, files: list[Union[dict, MessageFile]],
                      file_extra_config: FileExtraConfig) -> dict[FileType, list[FileVar]]:
        """
        将文件信息转换为文件对象集合。

        :param files: 文件信息列表，可以是字典或者MessageFile对象。
        :param file_extra_config: 文件额外配置信息。
        :return: 一个字典，键为文件类型（如图片），值为对应类型的文件对象列表。
        """
        # 初始化支持的文件类型及其对应的文件对象列表
        type_file_objs: dict[FileType, list[FileVar]] = {
            # 目前仅支持图片类型
            FileType.IMAGE: []
        }

        # 如果没有文件信息，则直接返回空的文件类型字典
        if not files:
            return type_file_objs

        # 根据文件类型分组，并将文件参数或消息文件转换为FileObj对象
        for file in files:
            # 忽略属于助手的文件
            if isinstance(file, MessageFile):
                if file.belongs_to == FileBelongsTo.ASSISTANT.value:
                    continue

            # 转换文件信息为文件对象
            file_obj = self._to_file_obj(file, file_extra_config)
            # 如果文件类型不在支持的类型列表中，则忽略该文件对象
            if file_obj.type not in type_file_objs:
                continue

            # 将文件对象添加到对应类型的文件对象列表中
            type_file_objs[file_obj.type].append(file_obj)

        return type_file_objs

    def _to_file_obj(self, file: Union[dict, MessageFile], file_extra_config: FileExtraConfig) -> FileVar:
        """
        将文件信息转换为文件对象。

        :param file: 文件信息，可以是一个字典或者MessageFile对象。字典格式时，需要包含文件的传输方法、类型等信息；
                    MessageFile对象时，则直接使用对象中的属性。
        :param file_extra_config: 文件额外配置信息，用于构建FileVar对象。
        :return: 返回一个FileVar类型的文件对象，包含了文件的各种信息，如传输方法、文件类型等。
        """
        if isinstance(file, dict):  # 当传入的file参数是字典时
            # 根据字典中的信息构建FileVar对象
            transfer_method = FileTransferMethod.value_of(file.get('transfer_method'))
            if transfer_method != FileTransferMethod.TOOL_FILE:
                return FileVar(
                    tenant_id=self.tenant_id,
                    type=FileType.value_of(file.get('type')),
                    transfer_method=transfer_method,
                    url=file.get('url') if transfer_method == FileTransferMethod.REMOTE_URL else None,
                    related_id=file.get('upload_file_id') if transfer_method == FileTransferMethod.LOCAL_FILE else None,
                    extra_config=file_extra_config
                )
            return FileVar(
                tenant_id=self.tenant_id,
                type=FileType.value_of(file.get('type')),
                transfer_method=transfer_method,
                url=None,
                related_id=file.get('tool_file_id'),
                extra_config=file_extra_config
            )
        else:  # 当传入的file参数是MessageFile对象时
            # 直接使用MessageFile对象的属性构建FileVar对象
            return FileVar(
                id=file.id,
                tenant_id=self.tenant_id,
                type=FileType.value_of(file.type),
                transfer_method=FileTransferMethod.value_of(file.transfer_method),
                url=file.url,
                related_id=file.upload_file_id or None,
                extra_config=file_extra_config
            )

    def _check_image_remote_url(self, url):
        """
        检查给定的URL是否指向一个有效的图像资源。
        
        参数:
        - url: 待检查的图像资源的URL字符串。
        
        返回值:
        - 一个元组，包含两个元素：第一个元素是布尔值，表示URL是否有效；第二个元素是字符串，描述错误信息或空字符串。
        """
        try:
            # 设置请求头，伪装为Chrome浏览器发送请求
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }

            # 发送HEAD请求检查URL是否可达
            response = requests.head(url, headers=headers, allow_redirects=True)
            if response.status_code in {200, 304}:
                return True, ""
            else:
                # 若状态码非200，表示URL不存在或有其他问题
                return False, "URL does not exist."
        except requests.RequestException as e:
            # 捕捉请求过程中可能出现的异常
            return False, f"Error checking URL: {e}"
