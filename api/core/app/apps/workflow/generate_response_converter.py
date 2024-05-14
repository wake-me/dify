import json
from collections.abc import Generator
from typing import cast

from core.app.apps.base_app_generate_response_converter import AppGenerateResponseConverter
from core.app.entities.task_entities import (
    ErrorStreamResponse,
    NodeFinishStreamResponse,
    NodeStartStreamResponse,
    PingStreamResponse,
    WorkflowAppBlockingResponse,
    WorkflowAppStreamResponse,
)


class WorkflowAppGenerateResponseConverter(AppGenerateResponseConverter):
    _blocking_response_type = WorkflowAppBlockingResponse

    @classmethod
    def convert_blocking_full_response(cls, blocking_response: WorkflowAppBlockingResponse) -> dict:
        """
        转换阻塞式完整响应。
        :param blocking_response: 阻塞响应对象，包含完整的 WorkflowApp 阻塞响应信息。
        :return: 返回一个字典，包含从阻塞响应对象中转换得到的数据。
        """
        return blocking_response.to_dict()  # 将阻塞响应对象转换为字典格式

    @classmethod
    def convert_blocking_simple_response(cls, blocking_response: WorkflowAppBlockingResponse) -> dict:
        """
        转换阻塞式简单响应。
        :param blocking_response: 阻塞响应对象，类型为 WorkflowAppBlockingResponse
        :return: 转换后的字典结果
        """
        # 调用类方法将阻塞式完整响应转换为字典
        return cls.convert_blocking_full_response(blocking_response)

    @classmethod
    def convert_stream_full_response(cls, stream_response: Generator[WorkflowAppStreamResponse, None, None]) \
            -> Generator[str, None, None]:
        """
        转换流式完整响应。
        :param stream_response: 流式响应，是一个生成器，逐块返回WorkflowAppStreamResponse对象
        :return: 转换后的响应，是一个生成器，逐块返回字符串形式的响应数据
        """
        for chunk in stream_response:
            chunk = cast(WorkflowAppStreamResponse, chunk)  # 将流响应转换为WorkflowAppStreamResponse类型
            sub_stream_response = chunk.stream_response

            # 处理心跳响应
            if isinstance(sub_stream_response, PingStreamResponse):
                yield 'ping'  # 返回'ping'表示心跳
                continue

            response_chunk = {
                'event': sub_stream_response.event.value,  # 事件名称
                'workflow_run_id': chunk.workflow_run_id,  # 工作流运行ID
            }

            # 根据响应类型进行不同的处理
            if isinstance(sub_stream_response, ErrorStreamResponse):
                # 错误响应处理
                data = cls._error_to_stream_response(sub_stream_response.err)
                response_chunk.update(data)
            else:
                # 其他类型的响应处理
                response_chunk.update(sub_stream_response.to_dict())
            yield json.dumps(response_chunk)  # 将响应块转换为JSON字符串并返回

    @classmethod
    def convert_stream_simple_response(cls, stream_response: Generator[WorkflowAppStreamResponse, None, None]) \
            -> Generator[str, None, None]:
        """
        转换流式简单响应。
        :param stream_response: 流式响应，是一个生成器，产生WorkflowAppStreamResponse类型的对象
        :return: 返回一个生成器，该生成器产生字符串类型的响应信息
        """
        for chunk in stream_response:
            chunk = cast(WorkflowAppStreamResponse, chunk)
            sub_stream_response = chunk.stream_response

            if isinstance(sub_stream_response, PingStreamResponse):
                yield 'ping'
                continue

            response_chunk = {
                'event': sub_stream_response.event.value,
                'workflow_run_id': chunk.workflow_run_id,
            }

            if isinstance(sub_stream_response, ErrorStreamResponse):
                data = cls._error_to_stream_response(sub_stream_response.err)
                response_chunk.update(data)
            elif isinstance(sub_stream_response, NodeStartStreamResponse | NodeFinishStreamResponse):
                response_chunk.update(sub_stream_response.to_ignore_detail_dict())
            else:
                response_chunk.update(sub_stream_response.to_dict())
            yield json.dumps(response_chunk)
