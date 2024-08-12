import logging
from abc import ABC, abstractmethod
from collections.abc import Generator
from typing import Any, Union

from core.app.entities.app_invoke_entities import InvokeFrom
from core.app.entities.task_entities import AppBlockingResponse, AppStreamResponse
from core.errors.error import ModelCurrentlyNotSupportError, ProviderTokenNotInitError, QuotaExceededError
from core.model_runtime.errors.invoke import InvokeError


class AppGenerateResponseConverter(ABC):
    _blocking_response_type: type[AppBlockingResponse]

    @classmethod
    def convert(cls, response: Union[
        AppBlockingResponse,
        Generator[AppStreamResponse, Any, None]
    ], invoke_from: InvokeFrom):
        if invoke_from in [InvokeFrom.DEBUGGER, InvokeFrom.SERVICE_API]:
            if isinstance(response, AppBlockingResponse):
                return cls.convert_blocking_full_response(response)
            else:
                def _generate_full_response() -> Generator[str, Any, None]:
                    for chunk in cls.convert_stream_full_response(response):
                        if chunk == 'ping':
                            yield f'event: {chunk}\n\n'
                        else:
                            yield f'data: {chunk}\n\n'

                return _generate_full_response()
        else:
            if isinstance(response, AppBlockingResponse):
                return cls.convert_blocking_simple_response(response)
            else:
                def _generate_simple_response() -> Generator[str, Any, None]:
                    for chunk in cls.convert_stream_simple_response(response):
                        if chunk == 'ping':
                            yield f'event: {chunk}\n\n'
                        else:
                            yield f'data: {chunk}\n\n'

                return _generate_simple_response()

    @classmethod
    @abstractmethod
    def convert_blocking_full_response(cls, blocking_response: AppBlockingResponse) -> dict[str, Any]:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def convert_blocking_simple_response(cls, blocking_response: AppBlockingResponse) -> dict[str, Any]:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def convert_stream_full_response(cls, stream_response: Generator[AppStreamResponse, None, None]) \
            -> Generator[str, None, None]:
        """
        转换流式类型的完全响应生成器。

        :param stream_response: 流式响应生成器。
        :return: 转换后的完全响应数据生成器。
        """
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def convert_stream_simple_response(cls, stream_response: Generator[AppStreamResponse, None, None]) \
            -> Generator[str, None, None]:
        """
        转换流式类型的简单响应生成器。

        :param stream_response: 流式响应生成器。
        :return: 转换后的简单响应数据生成器。
        """
        raise NotImplementedError

    @classmethod
    def _get_simple_metadata(cls, metadata: dict[str, Any]):
        """
        提取简单的元数据。

        :param metadata: 原始元数据字典。
        :return: 简化后的元数据字典。
        """
        # 清理和简化元数据，移除特定字段或转换格式
        if 'retriever_resources' in metadata:
            metadata['retriever_resources'] = []
            for resource in metadata['retriever_resources']:
                metadata['retriever_resources'].append({
                    'segment_id': resource['segment_id'],
                    'position': resource['position'],
                    'document_name': resource['document_name'],
                    'score': resource['score'],
                    'content': resource['content'],
                })

        # 移除'annotation_reply'和'usage'字段
        if 'annotation_reply' in metadata:
            del metadata['annotation_reply']

        if 'usage' in metadata:
            del metadata['usage']

        return metadata

    @classmethod
    def _error_to_stream_response(cls, e: Exception) -> dict:
        """
        将异常转换为流式响应格式。

        :param e: 异常对象。
        :return: 转换后的流式响应字典。
        """
        # 定义不同异常对应的响应数据
        error_responses = {
            ValueError: {'code': 'invalid_param', 'status': 400},
            ProviderTokenNotInitError: {'code': 'provider_not_initialize', 'status': 400},
            QuotaExceededError: {
                'code': 'provider_quota_exceeded',
                'message': "Your quota for Dify Hosted Model Provider has been exhausted. "
                           "Please go to Settings -> Model Provider to complete your own provider credentials.",
                'status': 400
            },
            ModelCurrentlyNotSupportError: {'code': 'model_currently_not_support', 'status': 400},
            InvokeError: {'code': 'completion_request_error', 'status': 400}
        }

        # 根据异常类型匹配响应数据
        data = None
        for k, v in error_responses.items():
            if isinstance(e, k):
                data = v

        if data:
            data.setdefault('message', getattr(e, 'description', str(e)))
        else:
            logging.error(e)
            data = {
                'code': 'internal_server_error',
                'message': 'Internal Server Error, please contact support.',
                'status': 500
            }

        return data