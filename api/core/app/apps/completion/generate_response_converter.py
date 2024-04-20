import json
from collections.abc import Generator
from typing import cast

from core.app.apps.base_app_generate_response_converter import AppGenerateResponseConverter
from core.app.entities.task_entities import (
    CompletionAppBlockingResponse,
    CompletionAppStreamResponse,
    ErrorStreamResponse,
    MessageEndStreamResponse,
    PingStreamResponse,
)


class CompletionAppGenerateResponseConverter(AppGenerateResponseConverter):
    _blocking_response_type = CompletionAppBlockingResponse

    @classmethod
    def convert_blocking_full_response(cls, blocking_response: CompletionAppBlockingResponse) -> dict:
        """
        转换阻塞式完整响应。
        :param blocking_response: 阻塞式响应对象，包含任务的完整信息。
        :return: 返回一个字典，包含转换后的消息事件信息。
        """
        # 创建响应字典，包含关键信息
        response = {
            'event': 'message',  # 事件类型为消息
            'task_id': blocking_response.task_id,  # 任务ID
            'id': blocking_response.data.id,  # 消息ID
            'message_id': blocking_response.data.message_id,  # 消息的内部ID
            'mode': blocking_response.data.mode,  # 模式信息
            'answer': blocking_response.data.answer,  # 响应答案
            'metadata': blocking_response.data.metadata,  # 元数据
            'created_at': blocking_response.data.created_at  # 创建时间
        }

        return response

    @classmethod
    def convert_blocking_simple_response(cls, blocking_response: CompletionAppBlockingResponse) -> dict:
        """
        转换阻塞式简单响应。
        :param blocking_response: 阻塞式响应对象
        :type blocking_response: CompletionAppBlockingResponse
        :return: 转换后的简单响应字典
        :rtype: dict
        """
        # 将阻塞式完整响应对象转换为字典
        response = cls.convert_blocking_full_response(blocking_response)

        # 获取原有元数据，若无则默认为空字典
        metadata = response.get('metadata', {})
        # 将元数据转换为简单的元数据格式
        response['metadata'] = cls._get_simple_metadata(metadata)

        return response

    @classmethod
    def convert_stream_full_response(cls, stream_response: Generator[CompletionAppStreamResponse, None, None]) \
            -> Generator[str, None, None]:
        """
        转换流式完整响应。
        :param stream_response: 流式响应，是一个生成器，逐块返回响应数据
        :return: 转换后的响应生成器，每块响应被转换为JSON字符串
        """
        for chunk in stream_response:
            chunk = cast(CompletionAppStreamResponse, chunk)  # 将chunk强制转换为CompletionAppStreamResponse类型
            sub_stream_response = chunk.stream_response

            # 处理收到的Ping响应
            if isinstance(sub_stream_response, PingStreamResponse):
                yield 'ping'  # 直接产生"ping"字符串
                continue

            response_chunk = {
                'event': sub_stream_response.event.value,  # 初始化响应块，包含事件名
                'message_id': chunk.message_id,  # 消息ID
                'created_at': chunk.created_at  # 创建时间
            }

            # 根据响应类型，更新响应块内容
            if isinstance(sub_stream_response, ErrorStreamResponse):
                data = cls._error_to_stream_response(sub_stream_response.err)  # 将错误信息转换为响应数据
                response_chunk.update(data)
            else:
                response_chunk.update(sub_stream_response.to_dict())  # 使用to_dict方法将响应内容转换为字典，并更新到响应块
            yield json.dumps(response_chunk)  # 将响应块转换为JSON字符串并产生

    @classmethod
    def convert_stream_simple_response(cls, stream_response: Generator[CompletionAppStreamResponse, None, None]) \
            -> Generator[str, None, None]:
        """
        转换流式简单响应。
        :param stream_response: 流式响应，是一个生成器，逐块返回响应内容
        :return: 转换后的响应生成器，每块响应被转换为JSON字符串
        """
        for chunk in stream_response:
            chunk = cast(CompletionAppStreamResponse, chunk)  # 将流响应块强制转换为CompletionAppStreamResponse类型
            sub_stream_response = chunk.stream_response

            # 处理Ping类型的流响应
            if isinstance(sub_stream_response, PingStreamResponse):
                yield 'ping'  # 直接产生"ping"字符串
                continue

            response_chunk = {
                'event': sub_stream_response.event.value,  # 初始化响应块，包含事件名
                'message_id': chunk.message_id,
                'created_at': chunk.created_at
            }

            # 处理消息结束类型的流响应
            if isinstance(sub_stream_response, MessageEndStreamResponse):
                sub_stream_response_dict = sub_stream_response.to_dict()
                metadata = sub_stream_response_dict.get('metadata', {})
                # 简化metadata信息
                sub_stream_response_dict['metadata'] = cls._get_simple_metadata(metadata)
                response_chunk.update(sub_stream_response_dict)
            # 处理错误类型的流响应
            if isinstance(sub_stream_response, ErrorStreamResponse):
                data = cls._error_to_stream_response(sub_stream_response.err)
                response_chunk.update(data)
            else:
                # 对于其他类型的响应，将其转换为字典并更新到响应块中
                response_chunk.update(sub_stream_response.to_dict())

            yield json.dumps(response_chunk)  # 将响应块转换为JSON字符串并产生
