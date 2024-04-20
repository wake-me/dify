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


class AgentChatAppGenerateResponseConverter(AppGenerateResponseConverter):
    _blocking_response_type = ChatbotAppBlockingResponse

    @classmethod
    def convert_blocking_full_response(cls, blocking_response: ChatbotAppBlockingResponse) -> dict:
        """
        转换阻塞式完整响应。
        :param blocking_response: 阻塞式响应对象
        :return: 转换后的完整响应字典
        """
        response = {
            'event': 'message',
            'task_id': blocking_response.task_id,
            'id': blocking_response.data.id,
            'message_id': blocking_response.data.message_id,
            'conversation_id': blocking_response.data.conversation_id,
            'mode': blocking_response.data.mode,
            'answer': blocking_response.data.answer,
            'metadata': blocking_response.data.metadata,
            'created_at': blocking_response.data.created_at
        }

        return response

    @classmethod
    def convert_blocking_simple_response(cls, blocking_response: ChatbotAppBlockingResponse) -> dict:
        """
        转换阻塞式简单响应。
        :param blocking_response: 阻塞式响应对象
        :return: 转换后的简单响应字典
        """
        response = cls.convert_blocking_full_response(blocking_response)

        metadata = response.get('metadata', {})
        response['metadata'] = cls._get_simple_metadata(metadata)  # 简化元数据

        return response

    @classmethod
    def convert_stream_full_response(cls, stream_response: Generator[ChatbotAppStreamResponse, None, None]) \
            -> Generator[str, None, None]:
        """
        转换流式完整响应。
        :param stream_response: 流式响应生成器
        :return: 转换后的流式响应字符串生成器
        """
        for chunk in stream_response:
            chunk = cast(ChatbotAppStreamResponse, chunk)
            sub_stream_response = chunk.stream_response

            # 处理心跳消息
            if isinstance(sub_stream_response, PingStreamResponse):
                yield 'ping'
                continue

            response_chunk = {
                'event': sub_stream_response.event.value,
                'conversation_id': chunk.conversation_id,
                'message_id': chunk.message_id,
                'created_at': chunk.created_at
            }

            # 错误响应处理
            if isinstance(sub_stream_response, ErrorStreamResponse):
                data = cls._error_to_stream_response(sub_stream_response.err)
                response_chunk.update(data)
            else:
                response_chunk.update(sub_stream_response.to_dict())
            yield json.dumps(response_chunk)

    @classmethod
    def convert_stream_simple_response(cls, stream_response: Generator[ChatbotAppStreamResponse, None, None]) \
            -> Generator[str, None, None]:
        """
        转换流式简单响应。
        :param stream_response: 流式响应生成器
        :return: 转换后的流式简单响应字符串生成器
        """
        for chunk in stream_response:
            chunk = cast(ChatbotAppStreamResponse, chunk)
            sub_stream_response = chunk.stream_response

            # 心跳消息处理
            if isinstance(sub_stream_response, PingStreamResponse):
                yield 'ping'
                continue

            response_chunk = {
                'event': sub_stream_response.event.value,
                'conversation_id': chunk.conversation_id,
                'message_id': chunk.message_id,
                'created_at': chunk.created_at
            }

            # 流结束消息处理
            if isinstance(sub_stream_response, MessageEndStreamResponse):
                sub_stream_response_dict = sub_stream_response.to_dict()
                metadata = sub_stream_response_dict.get('metadata', {})
                sub_stream_response_dict['metadata'] = cls._get_simple_metadata(metadata)
                response_chunk.update(sub_stream_response_dict)
            # 错误响应处理
            if isinstance(sub_stream_response, ErrorStreamResponse):
                data = cls._error_to_stream_response(sub_stream_response.err)
                response_chunk.update(data)
            else:
                response_chunk.update(sub_stream_response.to_dict())

            yield json.dumps(response_chunk)
