import copy
import logging
from collections.abc import Generator
from typing import Optional, Union, cast

import tiktoken
from openai import AzureOpenAI, Stream
from openai.types import Completion
from openai.types.chat import ChatCompletion, ChatCompletionChunk, ChatCompletionMessageToolCall
from openai.types.chat.chat_completion_chunk import ChoiceDeltaFunctionCall, ChoiceDeltaToolCall
from openai.types.chat.chat_completion_message import FunctionCall

from core.model_runtime.entities.llm_entities import LLMMode, LLMResult, LLMResultChunk, LLMResultChunkDelta
from core.model_runtime.entities.message_entities import (
    AssistantPromptMessage,
    ImagePromptMessageContent,
    PromptMessage,
    PromptMessageContentType,
    PromptMessageTool,
    SystemPromptMessage,
    TextPromptMessageContent,
    ToolPromptMessage,
    UserPromptMessage,
)
from core.model_runtime.entities.model_entities import AIModelEntity, ModelPropertyKey
from core.model_runtime.errors.validate import CredentialsValidateFailedError
from core.model_runtime.model_providers.__base.large_language_model import LargeLanguageModel
from core.model_runtime.model_providers.azure_openai._common import _CommonAzureOpenAI
from core.model_runtime.model_providers.azure_openai._constant import LLM_BASE_MODELS, AzureBaseModel

logger = logging.getLogger(__name__)


class AzureOpenAILargeLanguageModel(_CommonAzureOpenAI, LargeLanguageModel):
    """
    Azure OpenAI大型语言模型类，继承自_CommonAzureOpenAI和LargeLanguageModel。
    支持调用OpenAI的大型语言模型进行聊天或文本完成等任务。
    """

    def _invoke(self, model: str, credentials: dict,
                prompt_messages: list[PromptMessage], model_parameters: dict,
                tools: Optional[list[PromptMessageTool]] = None, stop: Optional[list[str]] = None,
                stream: bool = True, user: Optional[str] = None) \
            -> Union[LLMResult, Generator]:
        """
        调用OpenAI大型语言模型进行处理。

        :param model: 指定的模型名称或标识。
        :param credentials: 包含模型访问凭证的字典。
        :param prompt_messages: 提示消息列表，用于引导模型的响应。
        :param model_parameters: 模型参数字典，用于配置模型的行为。
        :param tools: 可选，提示消息工具列表，用于辅助生成提示消息。
        :param stop: 可选，停止信号列表，用于终止生成过程。
        :param stream: 是否以流式方式返回结果。
        :param user: 可选，模拟用户的标识。
        :return: 根据模型类型返回LLMResult或Generator对象，包含模型生成的结果。
        """
        
        # 获取AI模型实体
        ai_model_entity = self._get_ai_model_entity(credentials.get('base_model_name'), model)

        # 判断模型模式，决定调用的函数
        if ai_model_entity.entity.model_properties.get(ModelPropertyKey.MODE) == LLMMode.CHAT.value:
            # 如果是聊天模型，则调用聊天生成函数
            return self._chat_generate(
                model=model,
                credentials=credentials,
                prompt_messages=prompt_messages,
                model_parameters=model_parameters,
                tools=tools,
                stop=stop,
                stream=stream,
                user=user
            )
        else:
            # 如果是文本完成模型，则调用一般生成函数
            return self._generate(
                model=model,
                credentials=credentials,
                prompt_messages=prompt_messages,
                model_parameters=model_parameters,
                stop=stop,
                stream=stream,
                user=user
            )

    def get_num_tokens(self, model: str, credentials: dict, prompt_messages: list[PromptMessage],
                    tools: Optional[list[PromptMessageTool]] = None) -> int:
        """
        根据提供的模型、凭证和提示信息获取令牌数量。
        
        :param model: 指定的模型名称。
        :param credentials: 包含模型凭证信息的字典。
        :param prompt_messages: 提示信息列表，每个提示信息是一个PromptMessage对象。
        :param tools: 可选，PromptMessageTool工具列表，用于辅助处理提示信息。
        :return: 返回令牌的数量，具体取决于模型类型。
        """

        # 获取模型的模式（聊天模式或文本完成模式）
        model_mode = self._get_ai_model_entity(credentials.get('base_model_name'), model).entity.model_properties.get(
            ModelPropertyKey.MODE)

        if model_mode == LLMMode.CHAT.value:
            # 如果是聊天模型，则基于消息和工具计算令牌数量
            return self._num_tokens_from_messages(credentials, prompt_messages, tools)
        else:
            # 如果是文本完成模型，则只基于第一个提示信息的内容计算令牌数量，不支持工具调用
            return self._num_tokens_from_string(credentials, prompt_messages[0].content)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        验证提供的凭证信息是否有效。

        参数:
        - model: 指定的模型名称。
        - credentials: 包含访问所需凭证的字典。
        
        返回值: 无返回值，但会在验证失败时抛出异常。

        抛出异常:
        - CredentialsValidateFailedError: 当凭证信息缺失或无效时抛出。
        """
        # 检查必需的凭证字段是否存在
        if 'openai_api_base' not in credentials:
            raise CredentialsValidateFailedError('Azure OpenAI API Base Endpoint is required')

        if 'openai_api_key' not in credentials:
            raise CredentialsValidateFailedError('Azure OpenAI API key is required')

        if 'base_model_name' not in credentials:
            raise CredentialsValidateFailedError('Base Model Name is required')

        # 尝试获取AI模型实体以验证模型名称的有效性
        ai_model_entity = self._get_ai_model_entity(credentials.get('base_model_name'), model)

        if not ai_model_entity:
            raise CredentialsValidateFailedError(f'Base Model Name {credentials["base_model_name"]} is invalid')

        try:
            # 使用提供的凭证创建Azure OpenAI客户端
            client = AzureOpenAI(**self._to_credential_kwargs(credentials))

            # 根据模型类型（聊天模型或文本完成模型）执行相应的验证动作
            if ai_model_entity.entity.model_properties.get(ModelPropertyKey.MODE) == LLMMode.CHAT.value:
                # 聊天模型的验证动作
                client.chat.completions.create(
                    messages=[{"role": "user", "content": 'ping'}],
                    model=model,
                    temperature=0,
                    max_tokens=20,
                    stream=False,
                )
            else:
                # 文本完成模型的验证动作
                client.completions.create(
                    prompt='ping',
                    model=model,
                    temperature=0,
                    max_tokens=20,
                    stream=False,
                )
        except Exception as ex:
            # 在验证过程中遇到任何异常都抛出CredentialsValidateFailedError
            raise CredentialsValidateFailedError(str(ex))

    def get_customizable_model_schema(self, model: str, credentials: dict) -> Optional[AIModelEntity]:
        """
        获取可定制模型的架构信息。
        
        参数:
        - model: 模型名称，字符串类型。
        - credentials: 包含认证信息的字典，其中应至少包含'base_model_name'键。
        
        返回值:
        - 如果找到对应的模型实体，则返回AIModelEntity对象；否则返回None。
        """
        # 根据提供的基本模型名称和模型名称获取AI模型实体
        ai_model_entity = self._get_ai_model_entity(credentials.get('base_model_name'), model)
        # 如果找到了模型实体，则返回该实体，否则返回None
        return ai_model_entity.entity if ai_model_entity else None

    def _generate(self, model: str, credentials: dict,
                prompt_messages: list[PromptMessage], model_parameters: dict, stop: Optional[list[str]] = None,
                stream: bool = True, user: Optional[str] = None) -> Union[LLMResult, Generator]:
        """
        生成特定模型的文本内容。

        参数:
        - model: 指定的模型名称。
        - credentials: 用于认证的字典信息。
        - prompt_messages: 提示信息列表，每个提示信息包括内容。
        - model_parameters: 用于模型的参数字典。
        - stop: 可选，停止生成的条件列表。
        - stream: 是否流式处理响应，默认为True。
        - user: 可选，模拟用户的标识。

        返回值:
        - LLMResult 或 Generator: 根据 stream 参数返回单个结果对象或生成器对象。
        """
        
        client = AzureOpenAI(**self._to_credential_kwargs(credentials))

        extra_model_kwargs = {}

        if stop:
            extra_model_kwargs['stop'] = stop

        if user:
            extra_model_kwargs['user'] = user

        # 使用指定的模型和参数进行文本完成
        response = client.completions.create(
            prompt=prompt_messages[0].content,
            model=model,
            stream=stream,
            **model_parameters,
            **extra_model_kwargs
        )

        if stream:
            # 处理流式响应
            return self._handle_generate_stream_response(model, credentials, response, prompt_messages)

        # 处理非流式响应
        return self._handle_generate_response(model, credentials, response, prompt_messages)

    def _handle_generate_response(self, model: str, credentials: dict, response: Completion,
                                prompt_messages: list[PromptMessage]) -> LLMResult:
        """
        处理生成响应的逻辑。
        
        参数:
        - model: 使用的模型名称。
        - credentials: 用于模型访问的凭证。
        - response: 完成度对象，包含生成的文本和其他元数据。
        - prompt_messages: 提示信息列表，用于上下文引用。
        
        返回值:
        - LLMResult对象，封装了模型响应的各种信息，包括生成的文本、使用情况统计等。
        """
        assistant_text = response.choices[0].text  # 获取助手生成的文本

        # 将助手消息转换为提示消息格式
        assistant_prompt_message = AssistantPromptMessage(
            content=assistant_text
        )

        # 计算token数量
        if response.usage:
            # 如果存在使用信息，则直接转换获取token数量
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens
        else:
            # 否则，根据文本内容计算token数量
            prompt_tokens = self._num_tokens_from_string(credentials, prompt_messages[0].content)
            completion_tokens = self._num_tokens_from_string(credentials, assistant_text)

        # 根据模型使用情况计算响应的使用信息
        usage = self._calc_response_usage(model, credentials, prompt_tokens, completion_tokens)

        # 封装结果信息
        result = LLMResult(
            model=response.model,
            prompt_messages=prompt_messages,
            message=assistant_prompt_message,
            usage=usage,
            system_fingerprint=response.system_fingerprint,
        )

        return result

    def _handle_generate_stream_response(self, model: str, credentials: dict, response: Stream[Completion],
                                        prompt_messages: list[PromptMessage]) -> Generator:
        """
        处理生成流式响应的逻辑。
        
        :param model: 使用的模型名称。
        :param credentials: 用户的凭证信息，用于认证和访问权限。
        :param response: 一个流，包含完成信息的多个片段。
        :param prompt_messages: 提示信息列表，用于上下文交互。
        :return: 一个生成器，逐个yield处理后的结果块。
        """
        full_text = ''
        for chunk in response:
            if len(chunk.choices) == 0:
                continue

            delta = chunk.choices[0]

            if delta.finish_reason is None and (delta.text is None or delta.text == ''):
                continue

            # 将助手消息转换为提示消息
            text = delta.text if delta.text else ''
            assistant_prompt_message = AssistantPromptMessage(
                content=text
            )

            full_text += text

            if delta.finish_reason is not None:
                # 计算token数量
                if chunk.usage:
                    # 已提供使用情况
                    prompt_tokens = chunk.usage.prompt_tokens
                    completion_tokens = chunk.usage.completion_tokens
                else:
                    # 根据文本内容计算token数量
                    prompt_tokens = self._num_tokens_from_string(credentials, prompt_messages[0].content)
                    completion_tokens = self._num_tokens_from_string(credentials, full_text)

                # 计算并转换响应的使用情况
                usage = self._calc_response_usage(model, credentials, prompt_tokens, completion_tokens)

                yield LLMResultChunk(
                    model=chunk.model,
                    prompt_messages=prompt_messages,
                    system_fingerprint=chunk.system_fingerprint,
                    delta=LLMResultChunkDelta(
                        index=delta.index,
                        message=assistant_prompt_message,
                        finish_reason=delta.finish_reason,
                        usage=usage
                    )
                )
            else:
                # 未完成的响应片段
                yield LLMResultChunk(
                    model=chunk.model,
                    prompt_messages=prompt_messages,
                    system_fingerprint=chunk.system_fingerprint,
                    delta=LLMResultChunkDelta(
                        index=delta.index,
                        message=assistant_prompt_message,
                    )
                )

    def _chat_generate(self, model: str, credentials: dict,
                    prompt_messages: list[PromptMessage], model_parameters: dict,
                    tools: Optional[list[PromptMessageTool]] = None, stop: Optional[list[str]] = None,
                    stream: bool = True, user: Optional[str] = None) -> Union[LLMResult, Generator]:
        """
        使用指定的模型和参数生成聊天响应。
        
        :param model: 要使用的模型名称。
        :param credentials: 用于访问模型的凭证。
        :param prompt_messages: 提供给模型的提示消息列表。
        :param model_parameters: 用于模型的参数字典，例如响应格式。
        :param tools: 可选，辅助工具列表，提供给模型以增强其功能。
        :param stop: 可选，停止信号列表，用于告诉模型何时停止生成。
        :param stream: 是否流式处理响应。
        :param user: 可选，模拟用户的标识符。
        :return: 根据stream参数，返回LLMResult对象或生成器。
        """
        
        # 使用提供的凭证创建Azure OpenAI客户端
        client = AzureOpenAI(**self._to_credential_kwargs(credentials))

        # 处理模型参数中的响应格式
        response_format = model_parameters.get("response_format")
        if response_format:
            # 默认的响应格式处理
            if response_format == "json_object":
                response_format = {"type": "json_object"}
            else:
                response_format = {"type": "text"}
            model_parameters["response_format"] = response_format

        extra_model_kwargs = {}

        # 如果提供了工具列表，将其配置添加到extra_model_kwargs中
        if tools:
            extra_model_kwargs['functions'] = [{
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters
            } for tool in tools]

        # 如果提供了停止信号，添加到extra_model_kwargs中
        if stop:
            extra_model_kwargs['stop'] = stop

        # 如果提供了用户标识，添加到extra_model_kwargs中
        if user:
            extra_model_kwargs['user'] = user

        # 向模型发送请求，获取响应
        response = client.chat.completions.create(
            messages=[self._convert_prompt_message_to_dict(m) for m in prompt_messages],
            model=model,
            stream=stream,
            **model_parameters,
            **extra_model_kwargs,
        )

        # 根据是否流式处理响应，返回不同的处理结果
        if stream:
            return self._handle_chat_generate_stream_response(model, credentials, response, prompt_messages, tools)

        return self._handle_chat_generate_response(model, credentials, response, prompt_messages, tools)

    def _handle_chat_generate_response(self, model: str, credentials: dict, response: ChatCompletion,
                                    prompt_messages: list[PromptMessage],
                                    tools: Optional[list[PromptMessageTool]] = None) -> LLMResult:
        """
        处理聊天生成响应的逻辑。

        参数:
        - model: 使用的模型名称。
        - credentials: 用于模型访问的凭证。
        - response: 从聊天模型获取的完成响应对象。
        - prompt_messages: 提示消息列表，用于上下文。
        - tools: 可选，工具消息列表，用于提供额外的功能。

        返回值:
        - LLMResult对象，包含处理后的聊天响应信息。
        """

        # 提取助手消息和函数调用信息
        assistant_message = response.choices[0].message
        assistant_message_function_call = assistant_message.function_call

        # 从助手消息中提取函数调用
        function_call = self._extract_response_function_call(assistant_message_function_call)
        tool_calls = [function_call] if function_call else []

        # 将助手消息转换为提示消息格式
        assistant_prompt_message = AssistantPromptMessage(
            content=assistant_message.content,
            tool_calls=tool_calls
        )

        # 计算token数量
        if response.usage:
            # 已存在的使用信息将直接转换token数量
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens
        else:
            # 无使用信息时，计算token数量
            prompt_tokens = self._num_tokens_from_messages(credentials, prompt_messages, tools)
            completion_tokens = self._num_tokens_from_messages(credentials, [assistant_prompt_message])

        # 计算响应的使用信息
        usage = self._calc_response_usage(model, credentials, prompt_tokens, completion_tokens)

        # 转换响应格式
        response = LLMResult(
            model=response.model or model,
            prompt_messages=prompt_messages,
            message=assistant_prompt_message,
            usage=usage,
            system_fingerprint=response.system_fingerprint,
        )

        return response

    def _handle_chat_generate_stream_response(self, model: str, credentials: dict,
                                                response: Stream[ChatCompletionChunk],
                                                prompt_messages: list[PromptMessage],
                                                tools: Optional[list[PromptMessageTool]] = None) -> Generator:
        """
        处理聊天生成流式响应的函数。
        
        参数:
        - model: 字符串，指定用于生成聊天回复的模型。
        - credentials: 字典，包含用于认证的凭证信息。
        - response: Stream[ChatCompletionChunk]，聊天完成块的流式响应。
        - prompt_messages: PromptMessage列表，触发聊天生成的提示消息列表。
        - tools: PromptMessageTool列表，可选，与提示消息相关的工具列表。
        
        返回值:
        - Generator，生成器对象，逐块返回处理后的聊天结果。
        """
        index = 0
        full_assistant_content = ''
        delta_assistant_message_function_call_storage: ChoiceDeltaFunctionCall = None
        real_model = model
        system_fingerprint = None
        completion = ''
        for chunk in response:
            if len(chunk.choices) == 0:
                continue

            delta = chunk.choices[0]

            # 忽略内容为空或功能调用为空的delta
            if delta.delta is None or (
                delta.finish_reason is None
                and (delta.delta.content is None or delta.delta.content == '')
                and delta.delta.function_call is None
            ):
                continue
            
            # 处理流式功能调用
            if delta_assistant_message_function_call_storage is not None:
                if assistant_message_function_call:
                    delta_assistant_message_function_call_storage.arguments += assistant_message_function_call.arguments
                    continue
                else:
                    assistant_message_function_call = delta_assistant_message_function_call_storage
                    delta_assistant_message_function_call_storage = None
            else:
                if assistant_message_function_call:
                    delta_assistant_message_function_call_storage = assistant_message_function_call
                    if delta_assistant_message_function_call_storage.arguments is None:
                        delta_assistant_message_function_call_storage.arguments = ''
                    continue

            # 从响应中提取工具调用信息
            function_call = self._extract_response_function_call(assistant_message_function_call)
            tool_calls = [function_call] if function_call else []

            # 将助手消息转换为提示消息
            assistant_prompt_message = AssistantPromptMessage(
                content=delta.delta.content if delta.delta.content else '',
                tool_calls=tool_calls
            )

            full_assistant_content += delta.delta.content if delta.delta.content else ''

            real_model = chunk.model
            system_fingerprint = chunk.system_fingerprint
            completion += delta.delta.content if delta.delta.content else ''

            yield LLMResultChunk(
                model=real_model,
                prompt_messages=prompt_messages,
                system_fingerprint=system_fingerprint,
                delta=LLMResultChunkDelta(
                    index=index,
                    message=assistant_prompt_message,
                )
            )

            index += 0

        # 计算token数量
        prompt_tokens = self._num_tokens_from_messages(credentials, prompt_messages, tools)

        full_assistant_prompt_message = AssistantPromptMessage(
            content=completion
        )
        completion_tokens = self._num_tokens_from_messages(credentials, [full_assistant_prompt_message])

        # 转换使用情况信息
        usage = self._calc_response_usage(model, credentials, prompt_tokens, completion_tokens)

        yield LLMResultChunk(
            model=real_model,
            prompt_messages=prompt_messages,
            system_fingerprint=system_fingerprint,
            delta=LLMResultChunkDelta(
                index=index,
                message=AssistantPromptMessage(content=''),
                finish_reason='stop',
                usage=usage
            )
        )

    @staticmethod
    def _extract_response_tool_calls(response_tool_calls: list[ChatCompletionMessageToolCall | ChoiceDeltaToolCall]) \
            -> list[AssistantPromptMessage.ToolCall]:
        """
        从响应工具调用列表中提取工具调用信息。

        参数:
        - response_tool_calls: 一个列表，包含ChatCompletionMessageToolCall和ChoiceDeltaToolCall对象，
        这些对象表示与聊天助手交互时调用的工具。

        返回值:
        - 一个列表，包含AssistantPromptMessage.ToolCall对象，这些对象表示经过处理后可用于助手响应的工具调用信息。
        """

        tool_calls = []
        if response_tool_calls:
            # 遍历响应工具调用列表，将每个调用转换为AssistantPromptMessage.ToolCall格式
            for response_tool_call in response_tool_calls:
                function = AssistantPromptMessage.ToolCall.ToolCallFunction(
                    name=response_tool_call.function.name,
                    arguments=response_tool_call.function.arguments
                )

                tool_call = AssistantPromptMessage.ToolCall(
                    id=response_tool_call.id,
                    type=response_tool_call.type,
                    function=function
                )
                tool_calls.append(tool_call)  # 将转换后的工具调用添加到新列表中

        return tool_calls

    @staticmethod
    def _extract_response_function_call(response_function_call: FunctionCall | ChoiceDeltaFunctionCall) \
            -> AssistantPromptMessage.ToolCall:
        """
        从响应函数调用中提取工具调用信息。

        参数:
        - response_function_call: FunctionCall 或 ChoiceDeltaFunctionCall 类型，表示一个函数调用信息。

        返回值:
        - AssistantPromptMessage.ToolCall 类型，表示提取出的工具调用信息。
        """
        tool_call = None
        if response_function_call:
            # 构建 AssistantPromptMessage.ToolCall.Function 对象，存储函数名称和参数
            function = AssistantPromptMessage.ToolCall.ToolCallFunction(
                name=response_function_call.name,
                arguments=response_function_call.arguments
            )

            # 根据函数调用信息，构建 AssistantPromptMessage.ToolCall 对象
            tool_call = AssistantPromptMessage.ToolCall(
                id=response_function_call.name,
                type="function",
                function=function
            )

        return tool_call

    @staticmethod
    def _convert_prompt_message_to_dict(message: PromptMessage) -> dict:
        """
        将提示消息对象转换为字典格式。

        参数:
        - message: PromptMessage, 待转换的消息对象，可以是用户提示消息、助手提示消息、系统提示消息或工具提示消息。

        返回值:
        - dict, 转换后的消息字典，包含消息的角色（用户、助手、系统或工具）和内容。
        """
        
        if isinstance(message, UserPromptMessage):
            # 处理用户提示消息
            message = cast(UserPromptMessage, message)
            if isinstance(message.content, str):
                # 当内容为字符串时直接处理
                message_dict = {"role": "user", "content": message.content}
            else:
                # 当内容为消息列表时，逐个处理并构建子消息字典
                sub_messages = []
                for message_content in message.content:
                    if message_content.type == PromptMessageContentType.TEXT:
                        # 处理文本类型消息内容
                        message_content = cast(TextPromptMessageContent, message_content)
                        sub_message_dict = {
                            "type": "text",
                            "text": message_content.data
                        }
                        sub_messages.append(sub_message_dict)
                    elif message_content.type == PromptMessageContentType.IMAGE:
                        # 处理图片类型消息内容
                        message_content = cast(ImagePromptMessageContent, message_content)
                        sub_message_dict = {
                            "type": "image_url",
                            "image_url": {
                                "url": message_content.data,
                                "detail": message_content.detail.value
                            }
                        }
                        sub_messages.append(sub_message_dict)

                message_dict = {"role": "user", "content": sub_messages}
        elif isinstance(message, AssistantPromptMessage):
            # 处理助手提示消息
            message = cast(AssistantPromptMessage, message)
            message_dict = {"role": "assistant", "content": message.content}
            if message.tool_calls:
                # 如果存在工具调用，添加工具调用信息
                function_call = message.tool_calls[0]
                message_dict["function_call"] = {
                    "name": function_call.function.name,
                    "arguments": function_call.function.arguments,
                }
        elif isinstance(message, SystemPromptMessage):
            # 处理系统提示消息
            message = cast(SystemPromptMessage, message)
            message_dict = {"role": "system", "content": message.content}
        elif isinstance(message, ToolPromptMessage):
            # 处理工具提示消息
            message = cast(ToolPromptMessage, message)
            message_dict = {
                "role": "function",
                "content": message.content,
                "name": message.tool_call_id
            }
        else:
            # 如果消息类型未知，抛出异常
            raise ValueError(f"Got unknown type {message}")

        if message.name:
            # 如果消息具有名称，添加到字典中
            message_dict["name"] = message.name

        return message_dict

    def _num_tokens_from_string(self, credentials: dict, text: str,
                                tools: Optional[list[PromptMessageTool]] = None) -> int:
        """
        根据提供的文本和工具列表计算总令牌数。
        
        :param credentials: 包含模型基本信息的字典，例如基础模型名称。
        :param text: 需要被编码和计算令牌数的文本字符串。
        :param tools: 一个可选的工具列表，每个工具可能会贡献额外的令牌数。
        :return: 计算得到的总令牌数。
        """
        try:
            # 尝试根据提供的模型名称获取编码方式
            encoding = tiktoken.encoding_for_model(credentials['base_model_name'])
        except KeyError:
            # 如果指定的模型名称不存在，则使用默认编码方式
            encoding = tiktoken.get_encoding("cl100k_base")

        # 计算文本的令牌数
        num_tokens = len(encoding.encode(text))

        if tools:
            # 如果提供了工具列表，计算这些工具额外的令牌数并累加
            num_tokens += self._num_tokens_for_tools(encoding, tools)

        return num_tokens

    def _num_tokens_from_messages(self, credentials: dict, messages: list[PromptMessage],
                                tools: Optional[list[PromptMessageTool]] = None) -> int:
        """
        计算gpt-3.5-turbo和gpt-4模型所需的token数量，使用tiktoken包进行计算。

        官方文档: https://github.com/openai/openai-cookbook/blob/
        main/examples/How_to_format_inputs_to_ChatGPT_models.ipynb

        :param credentials: 包含模型基础信息的字典。
        :param messages: 要计算token数量的PromptMessage列表。
        :param tools: 可选，PromptMessageTool工具列表，用于计算额外的token数量。
        :return: 模型输入所需的总token数量。
        """
        model = credentials['base_model_name']
        try:
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            logger.warning("Warning: model not found. Using cl100k_base encoding.")
            model = "cl100k_base"
            encoding = tiktoken.get_encoding(model)

        # 根据模型名称确定每条消息和每个名字对应的token数量
        if model.startswith("gpt-35-turbo-0301"):
            tokens_per_message = 4
            tokens_per_name = -1  # 如果存在名字，则忽略角色
        elif model.startswith("gpt-35-turbo") or model.startswith("gpt-4"):
            tokens_per_message = 3
            tokens_per_name = 1
        else:
            raise NotImplementedError(
                f"get_num_tokens_from_messages() is not presently implemented "
                f"for model {model}."
                "See https://github.com/openai/openai-python/blob/main/chatml.md for "
                "information on how messages are converted to tokens."
            )

        num_tokens = 0
        messages_dict = [self._convert_prompt_message_to_dict(m) for m in messages]  # 将消息列表转换为字典列表
        for message in messages_dict:
            num_tokens += tokens_per_message
            for key, value in message.items():
                # 将消息值转换为字符串，以处理非字符串值（如函数消息）
                if isinstance(value, list):
                    text = ''
                    for item in value:
                        if isinstance(item, dict) and item['type'] == 'text':
                            text += item['text']

                    value = text

                # 计算工具调用和函数调用中的token数量
                if key == "tool_calls":
                    for tool_call in value:
                        for t_key, t_value in tool_call.items():
                            num_tokens += len(encoding.encode(t_key))
                            if t_key == "function":
                                for f_key, f_value in t_value.items():
                                    num_tokens += len(encoding.encode(f_key))
                                    num_tokens += len(encoding.encode(f_value))
                            else:
                                num_tokens += len(encoding.encode(t_key))
                                num_tokens += len(encoding.encode(t_value))
                else:
                    num_tokens += len(encoding.encode(str(value)))

                if key == "name":
                    num_tokens += tokens_per_name

        # 每个回复都会以<im_start>assistant作为前缀，增加3个token
        num_tokens += 3

        if tools:
            num_tokens += self._num_tokens_for_tools(encoding, tools)  # 计算工具相关的token数量

        return num_tokens

    @staticmethod
    def _num_tokens_for_tools(encoding: tiktoken.Encoding, tools: list[PromptMessageTool]) -> int:
        """
        计算给定工具列表的编码令牌总数。

        参数:
        - encoding: tiktoken.Encoding，用于编码不同类型数据的编码器。
        - tools: list[PromptMessageTool]，包含多个PromptMessageTool对象的列表，每个对象代表一个工具。

        返回值:
        - int，工具列表所有编码后的令牌总数。
        """

        num_tokens = 0
        for tool in tools:
            # 为每个工具计算基础类型和功能的令牌数
            num_tokens += len(encoding.encode('type'))
            num_tokens += len(encoding.encode('function'))
            
            # 计算函数对象的令牌数
            num_tokens += len(encoding.encode('name'))
            num_tokens += len(encoding.encode(tool.name))
            num_tokens += len(encoding.encode('description'))
            num_tokens += len(encoding.encode(tool.description))
            
            parameters = tool.parameters
            num_tokens += len(encoding.encode('parameters'))
            if 'title' in parameters:
                # 如果参数中包含标题，则计算标题的令牌数
                num_tokens += len(encoding.encode('title'))
                num_tokens += len(encoding.encode(parameters.get("title")))
            num_tokens += len(encoding.encode('type'))
            num_tokens += len(encoding.encode(parameters.get("type")))
            
            if 'properties' in parameters:
                # 计算属性的令牌数
                num_tokens += len(encoding.encode('properties'))
                for key, value in parameters.get('properties').items():
                    num_tokens += len(encoding.encode(key))
                    for field_key, field_value in value.items():
                        num_tokens += len(encoding.encode(field_key))
                        if field_key == 'enum':
                            # 如果属性包含枚举类型，则为每个枚举值增加额外的令牌数
                            for enum_field in field_value:
                                num_tokens += 3
                                num_tokens += len(encoding.encode(enum_field))
                        else:
                            num_tokens += len(encoding.encode(field_key))
                            num_tokens += len(encoding.encode(str(field_value)))
            if 'required' in parameters:
                # 计算必需参数的令牌数
                num_tokens += len(encoding.encode('required'))
                for required_field in parameters['required']:
                    num_tokens += 3
                    num_tokens += len(encoding.encode(required_field))

        return num_tokens

    @staticmethod
    def _get_ai_model_entity(base_model_name: str, model: str) -> AzureBaseModel:
        """
        根据基础模型名称和模型名称获取AI模型实体。
        
        参数:
        - base_model_name: str，基础模型的名称。
        - model: str，模型的名称。
        
        返回值:
        - AzureBaseModel，如果找到匹配的基础模型实体，则返回其深拷贝；否则返回None。
        """
        # 遍历预定义的LLM基础模型列表
        for ai_model_entity in LLM_BASE_MODELS:
            # 如果找到匹配的基础模型名称
            if ai_model_entity.base_model_name == base_model_name:
                # 创建该模型实体的深拷贝
                ai_model_entity_copy = copy.deepcopy(ai_model_entity)
                # 更新拷贝的模型实体的模型名称和标签
                ai_model_entity_copy.entity.model = model
                ai_model_entity_copy.entity.label.en_US = model
                ai_model_entity_copy.entity.label.zh_Hans = model
                # 返回更新后的模型实体深拷贝
                return ai_model_entity_copy

        # 如果没有找到匹配的基础模型名称，返回None
        return None
