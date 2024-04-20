import json
from collections.abc import Generator
from typing import cast

from core.app.apps.base_app_generate_response_converter import AppGenerateResponseConverter
from core.app.entities.task_entities import (
    ChatbotAppBlockingResponse,
    ChatbotAppStreamResponse,
    ErrorStreamResponse,
    MessageEndStreamResponse,
    PingStreamResponse,
)


class ChatAppGenerateResponseConverter(AppGenerateResponseConverter):
    _blocking_response_type = ChatbotAppBlockingResponse

    @classmethod
    def convert_blocking_full_response(cls, blocking_response: ChatbotAppBlockingResponse) -> dict:
        """
        转换阻塞式完整响应。
        :param blocking_response: 阻塞式响应对象，包含聊天应用的完整响应信息
        :return: 返回一个字典，包含转换后的消息事件信息
        """
        # 构建并返回一个包含事件信息的字典
        response = {
            'event': 'message',  # 事件类型为消息
            'task_id': blocking_response.task_id,  # 任务ID
            'id': blocking_response.data.id,  # 消息ID
            'message_id': blocking_response.data.message_id,  # 消息的内部ID
            'conversation_id': blocking_response.data.conversation_id,  # 对话ID
            'mode': blocking_response.data.mode,  # 模式
            'answer': blocking_response.data.answer,  # 响应答案
            'metadata': blocking_response.data.metadata,  # 元数据
            'created_at': blocking_response.data.created_at  # 创建时间
        }

        return response

    @classmethod
    def convert_blocking_simple_response(cls, blocking_response: ChatbotAppBlockingResponse) -> dict:
        """
        转换阻塞式简单响应。
        该方法将阻塞式的完整响应转换为简单的响应格式，主要通过提取和转换元数据来实现。

        :param blocking_response: 阻塞响应对象，包含完整的聊天机器人应用响应信息。
        :type blocking_response: ChatbotAppBlockingResponse
        :return: 转换后的简单响应字典，主要包含经过简化处理的元数据。
        :rtype: dict
        """
        # 调用方法将阻塞式完整响应转换为字典格式
        response = cls.convert_blocking_full_response(blocking_response)

        # 提取并转换元数据，以适应简单响应格式
        metadata = response.get('metadata', {})
        response['metadata'] = cls._get_simple_metadata(metadata)

        return response

    @classmethod
    def convert_stream_full_response(cls, stream_response: Generator[ChatbotAppStreamResponse, None, None]) \
            -> Generator[str, None, None]:
        """
        转换流式完整响应。
        :param stream_response: 流式响应，是一个生成器，产生ChatbotAppStreamResponse类型的对象
        :return: 转换后的响应，是一个生成器，产生包含响应信息的JSON字符串
        """
        for chunk in stream_response:
            chunk = cast(ChatbotAppStreamResponse, chunk)  # 将流响应转换为ChatbotAppStreamResponse类型
            sub_stream_response = chunk.stream_response

            # 处理收到的Ping响应
            if isinstance(sub_stream_response, PingStreamResponse):
                yield 'ping'  # 直接返回'ping'字符串
                continue

            response_chunk = {
                'event': sub_stream_response.event.value,  # 事件类型
                'conversation_id': chunk.conversation_id,  # 对话ID
                'message_id': chunk.message_id,  # 消息ID
                'created_at': chunk.created_at  # 创建时间
            }

            # 根据响应类型，更新响应内容
            if isinstance(sub_stream_response, ErrorStreamResponse):
                # 如果是错误响应，则特殊处理
                data = cls._error_to_stream_response(sub_stream_response.err)
                response_chunk.update(data)
            else:
                # 否则，将正常响应的信息转换为字典，并更新到响应内容中
                response_chunk.update(sub_stream_response.to_dict())
            yield json.dumps(response_chunk)  # 将响应内容转换为JSON字符串并返回

    @classmethod
    def convert_stream_simple_response(cls, stream_response: Generator[ChatbotAppStreamResponse, None, None]) \
            -> Generator[str, None, None]:
        """
        转换流式响应为简单格式。
        :param stream_response: 流式响应对象，是一个生成器，产生ChatbotAppStreamResponse类型的对象
        :return: 生成器，每个元素是转换后的简单格式响应字符串
        """
        for chunk in stream_response:
            chunk = cast(ChatbotAppStreamResponse, chunk)
            sub_stream_response = chunk.stream_response

            # 处理Ping类型的流响应，直接返回'ping'
            if isinstance(sub_stream_response, PingStreamResponse):
                yield 'ping'
                continue

            response_chunk = {
                'event': sub_stream_response.event.value,
                'conversation_id': chunk.conversation_id,
                'message_id': chunk.message_id,
                'created_at': chunk.created_at
            }

            # 处理消息结束类型的流响应，更新响应chunk加入简单元数据
            if isinstance(sub_stream_response, MessageEndStreamResponse):
                sub_stream_response_dict = sub_stream_response.to_dict()
                metadata = sub_stream_response_dict.get('metadata', {})
                sub_stream_response_dict['metadata'] = cls._get_simple_metadata(metadata)
                response_chunk.update(sub_stream_response_dict)
            # 处理错误类型的流响应，转换错误信息到响应chunk中
            if isinstance(sub_stream_response, ErrorStreamResponse):
                data = cls._error_to_stream_response(sub_stream_response.err)
                response_chunk.update(data)
            else:
                # 对于其他类型的流响应，转换为字典并更新到响应chunk中
                response_chunk.update(sub_stream_response.to_dict())

            # 将响应chunk转换为JSON字符串并yield
            yield json.dumps(response_chunk)
