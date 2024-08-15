import logging
from mimetypes import guess_extension

from core.file.file_obj import FileTransferMethod, FileType
from core.tools.entities.tool_entities import ToolInvokeMessage
from core.tools.tool_file_manager import ToolFileManager

logger = logging.getLogger(__name__)

class ToolFileMessageTransformer:
    @classmethod
    def transform_tool_invoke_messages(cls, messages: list[ToolInvokeMessage],
                                       user_id: str,
                                       tenant_id: str,
                                       conversation_id: str) -> list[ToolInvokeMessage]:
        """
        转换工具调用消息并处理文件下载。

        此方法处理ToolInvokeMessage对象列表，根据其类型进行转换。
        特别处理图像和二进制大对象(BLOB)类型的消息，尝试下载或存储它们。
        转换后的消息作为列表返回。

        参数:
        - messages: 待转换的ToolInvokeMessage对象列表。
        - user_id: 发起消息转换的用户ID。
        - tenant_id: 用户所属租户的ID。
        - conversation_id: 消息发送所在对话的唯一标识符。

        返回:
        转换后的ToolInvokeMessage对象列表。图像和BLOB类型的消息可能被转换为IMAGE_LINK或LINK类型。
        """

        result = []  # 用于存放转换后的消息

        for message in messages:
            # 针对不同消息类型分别处理
            if message.type == ToolInvokeMessage.MessageType.TEXT:
                result.append(message)  # 直接添加文本消息
            elif message.type == ToolInvokeMessage.MessageType.LINK:
                result.append(message)  # 直接添加链接消息
            elif message.type == ToolInvokeMessage.MessageType.IMAGE:
                # 尝试下载并转换图像消息为IMAGE_LINK类型
                try:
                    file = ToolFileManager.create_file_by_url(
                        user_id=user_id,
                        tenant_id=tenant_id,
                        conversation_id=conversation_id,
                        file_url=message.message
                    )

                    url = f'/files/tools/{file.id}{guess_extension(file.mimetype) or ".png"}'

                    result.append(ToolInvokeMessage(
                        type=ToolInvokeMessage.MessageType.IMAGE_LINK,
                        message=url,
                        save_as=message.save_as,
                        meta=message.meta.copy() if message.meta is not None else {},
                    ))
                except Exception as e:
                    logger.exception(e)
                    # 图像下载失败时的备选文本消息
                    result.append(ToolInvokeMessage(
                        type=ToolInvokeMessage.MessageType.TEXT,
                        message=f"Failed to download image: {message.message}, you can try to download it yourself.",
                        meta=message.meta.copy() if message.meta is not None else {},
                        save_as=message.save_as,
                    ))
            elif message.type == ToolInvokeMessage.MessageType.BLOB:
                # 处理BLOB类型消息，存储并根据MIME类型转换为IMAGE_LINK或LINK类型
                mimetype = message.meta.get('mime_type', 'octet/stream')
                
                if isinstance(message.message, str):
                    message.message = message.message.encode('utf-8')

                file = ToolFileManager.create_file_by_raw(
                    user_id=user_id, tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    file_binary=message.message,
                    mimetype=mimetype
                )

                url = cls.get_tool_file_url(file.id, guess_extension(file.mimetype))

                # 根据MIME类型判断消息类型：如果是图像则为IMAGE_LINK，否则为LINK
                if 'image' in mimetype:
                    result.append(ToolInvokeMessage(
                        type=ToolInvokeMessage.MessageType.IMAGE_LINK,
                        message=url,
                        save_as=message.save_as,
                        meta=message.meta.copy() if message.meta is not None else {},
                    ))
                else:
                    result.append(ToolInvokeMessage(
                        type=ToolInvokeMessage.MessageType.LINK,
                        message=url,
                        save_as=message.save_as,
                        meta=message.meta.copy() if message.meta is not None else {},
                    ))
            elif message.type == ToolInvokeMessage.MessageType.FILE_VAR:
                file_var = message.meta.get('file_var')
                if file_var:
                    if file_var.transfer_method == FileTransferMethod.TOOL_FILE:
                        url = cls.get_tool_file_url(file_var.related_id, file_var.extension)
                        if file_var.type == FileType.IMAGE:
                            result.append(ToolInvokeMessage(
                                type=ToolInvokeMessage.MessageType.IMAGE_LINK,
                                message=url,
                                save_as=message.save_as,
                                meta=message.meta.copy() if message.meta is not None else {},
                            ))
                        else:
                            result.append(ToolInvokeMessage(
                                type=ToolInvokeMessage.MessageType.LINK,
                                message=url,
                                save_as=message.save_as,
                                meta=message.meta.copy() if message.meta is not None else {},
                            ))
            else:
                # 未处理的消息类型直接传递
                result.append(message)

        return result

    @classmethod
    def get_tool_file_url(cls, tool_file_id: str, extension: str) -> str:
        return f'/files/tools/{tool_file_id}{extension or ".bin"}'
