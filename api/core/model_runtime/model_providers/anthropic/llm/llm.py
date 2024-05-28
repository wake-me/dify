import base64
import json
import mimetypes
from collections.abc import Generator
from typing import Optional, Union, cast

import anthropic
import requests
from anthropic import Anthropic, Stream
from anthropic.types import (
    ContentBlockDeltaEvent,
    Message,
    MessageDeltaEvent,
    MessageStartEvent,
    MessageStopEvent,
    MessageStreamEvent,
    completion_create_params,
)
from anthropic.types.beta.tools import ToolsBetaMessage
from httpx import Timeout

from core.model_runtime.callbacks.base_callback import Callback
from core.model_runtime.entities.llm_entities import LLMResult, LLMResultChunk, LLMResultChunkDelta
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
from core.model_runtime.errors.invoke import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
from core.model_runtime.errors.validate import CredentialsValidateFailedError
from core.model_runtime.model_providers.__base.large_language_model import LargeLanguageModel

# 定义一个ANTHROPIC_BLOCK_MODE_PROMPT常量
# 这是一个多行字符串，用于提示用户应该按照指示生成一个有效的{{block}}对象。
# 字符串中包含了一个占位符{{instructions}}，用于动态插入具体的指示内容。
# 用户被告知，如果不确定{{block}}对象的结构，可以使用{"answer": "$your_answer"}作为默认结构。
ANTHROPIC_BLOCK_MODE_PROMPT = """You should always follow the instructions and output a valid {{block}} object.
The structure of the {{block}} object you can found in the instructions, use {"answer": "$your_answer"} as the default structure
if you are not sure about the structure.

<instructions>
{{instructions}}
</instructions>
"""


class AnthropicLargeLanguageModel(LargeLanguageModel):
    def _invoke(self, model: str, credentials: dict,
                prompt_messages: list[PromptMessage], model_parameters: dict,
                tools: Optional[list[PromptMessageTool]] = None, stop: Optional[list[str]] = None,
                stream: bool = True, user: Optional[str] = None) \
            -> Union[LLMResult, Generator]:
        """
        调用大型语言模型

        :param model: 模型名称
        :param credentials: 模型凭证
        :param prompt_messages: 提示信息
        :param model_parameters: 模型参数
        :param tools: 工具调用列表
        :param stop: 停止词列表
        :param stream: 是否流式响应
        :param user: 唯一用户ID
        :return: 全部响应或流式响应块生成器结果
        """
        # 调用模型
        return self._chat_generate(model, credentials, prompt_messages, model_parameters, tools, stop, stream, user)

    def _chat_generate(self, model: str, credentials: dict,
                    prompt_messages: list[PromptMessage], model_parameters: dict, 
                    tools: Optional[list[PromptMessageTool]] = None, stop: Optional[list[str]] = None,
                    stream: bool = True, user: Optional[str] = None) -> Union[LLMResult, Generator]:
        """
        调用llm聊天模型

        :param model: 模型名称
        :param credentials: 凭证信息
        :param prompt_messages: 提示信息
        :param model_parameters: 模型参数
        :param stop: 停止词
        :param stream: 是否流式返回响应
        :param user: 唯一用户ID
        :return: 完整响应或流式响应块生成器结果
        """
        # 将凭证信息转换为模型实例所需的kwargs
        credentials_kwargs = self._to_credential_kwargs(credentials)

        # 将模型参数从anthropic的完成API转换为聊天API
        if 'max_tokens_to_sample' in model_parameters:
            model_parameters['max_tokens'] = model_parameters.pop('max_tokens_to_sample')

        # 初始化模型客户端
        client = Anthropic(**credentials_kwargs)

        extra_model_kwargs = {}
        if stop:
            # 设置停止序列
            extra_model_kwargs['stop_sequences'] = stop

        if user:
            # 设置用户ID元数据
            extra_model_kwargs['metadata'] = completion_create_params.Metadata(user_id=user)

        system, prompt_message_dicts = self._convert_prompt_messages(prompt_messages)

        if system:
            # 设置系统信息
            extra_model_kwargs['system'] = system

        if tools:
            # 转换工具提示信息，并调用聊天工具接口
            extra_model_kwargs['tools'] = [
                self._transform_tool_prompt(tool) for tool in tools
            ]
            response = client.beta.tools.messages.create(
                model=model,
                messages=prompt_message_dicts,
                stream=stream,
                **model_parameters,
                **extra_model_kwargs
            )
        else:
            # 调用聊天模型接口
            response = client.messages.create(
                model=model,
                messages=prompt_message_dicts,
                stream=stream,
                **model_parameters,
                **extra_model_kwargs
            )

        if stream:
            # 处理流式返回响应
            return self._handle_chat_generate_stream_response(model, credentials, response, prompt_messages)

        # 处理非流式返回响应
        return self._handle_chat_generate_response(model, credentials, response, prompt_messages)

    def _code_block_mode_wrapper(self, model: str, credentials: dict, prompt_messages: list[PromptMessage],
                                 model_parameters: dict, tools: Optional[list[PromptMessageTool]] = None,
                                 stop: Optional[list[str]] = None, stream: bool = True, user: Optional[str] = None,
                                 callbacks: list[Callback] = None) -> Union[LLMResult, Generator]:
        """
        Code block mode wrapper for invoking large language model
        """
        if model_parameters.get('response_format'):
            stop = stop or []
            # chat model
            self._transform_chat_json_prompts(
                model=model,
                credentials=credentials,
                prompt_messages=prompt_messages,
                model_parameters=model_parameters,
                tools=tools,
                stop=stop,
                stream=stream,
                user=user,
                response_format=model_parameters['response_format']
            )
            model_parameters.pop('response_format')

            # 调用模型，并返回结果
            return self._invoke(model, credentials, prompt_messages, model_parameters, tools, stop, stream, user)

    def _transform_tool_prompt(self, tool: PromptMessageTool) -> dict:
        """
        将 PromptMessageTool 对象转换为字典格式。
        
        参数:
        - tool: PromptMessageTool 类型，包含需要转换的工具的名称、描述和参数信息。
        
        返回值:
        - 字典类型，包含转换后的工具名称、描述和输入参数 schema。
        """
        return {
            'name': tool.name,  # 工具名称
            'description': tool.description,  # 工具描述
            'input_schema': tool.parameters  # 工具输入参数的 schema
        }

    def _transform_chat_json_prompts(self, model: str, credentials: dict,
                                    prompt_messages: list[PromptMessage], model_parameters: dict,
                                    tools: list[PromptMessageTool] | None = None, stop: list[str] | None = None,
                                    stream: bool = True, user: str | None = None, response_format: str = 'JSON') \
                -> None:
            """
            转换聊天的JSON提示信息
            
            该方法用于调整和转换与模型交互时的提示信息，确保消息格式符合指定的响应格式（如JSON）。
            
            :param model: 用于聊天的模型名称。
            :param credentials: 访问模型所需的凭证信息。
            :param prompt_messages: 待转换的提示消息列表。
            :param model_parameters: 模型参数，用于调整模型的行为。
            :param tools: 与提示信息一起使用的工具列表，可选。
            :param stop: 用于终止聊天的信号词列表，可选。
            :param stream: 是否以流的形式发送消息，True表示连续发送，False表示批量发送，默认为True。
            :param user: 用户的标识信息，可选。
            :param response_format: 希望接收的响应格式，默认为'JSON'。
            :return: 无返回值。
            """
            
            # 确保停止信号包含特定的markdown格式分隔符
            if "```\n" not in stop:
                stop.append("```\n")
            if "\n```" not in stop:
                stop.append("\n```")

            # 检查是否存在系统消息
            if len(prompt_messages) > 0 and isinstance(prompt_messages[0], SystemPromptMessage):
                # 如果存在系统消息，则覆盖系统消息内容，添加针对指定响应格式的指示
                prompt_messages[0] = SystemPromptMessage(
                    content=ANTHROPIC_BLOCK_MODE_PROMPT
                    .replace("{{instructions}}", prompt_messages[0].content)
                    .replace("{{block}}", response_format)
                )
                prompt_messages.append(AssistantPromptMessage(content=f"\n```{response_format}"))
            else:
                # 如果不存在系统消息，则插入一个系统消息，指示用户输出符合指定响应格式的对象
                prompt_messages.insert(0, SystemPromptMessage(
                    content=ANTHROPIC_BLOCK_MODE_PROMPT
                    .replace("{{instructions}}", f"Please output a valid {response_format} object.")
                    .replace("{{block}}", response_format)
                ))
                prompt_messages.append(AssistantPromptMessage(content=f"\n```{response_format}"))

    def get_num_tokens(self, model: str, credentials: dict, prompt_messages: list[PromptMessage],
                       tools: Optional[list[PromptMessageTool]] = None) -> int:
        """
        获取给定提示消息的令牌数量
        
        :param model: 模型名称
        :param credentials: 模型凭证
        :param prompt_messages: 提示消息列表
        :param tools: 工具列表，用于工具调用
        :return: 令牌总数
        """
        # 将消息列表转换为适用于Anthropic的提示格式
        prompt = self._convert_messages_to_prompt_anthropic(prompt_messages)

        # 创建Anthropic客户端实例
        client = Anthropic(api_key="")
        # 计算提示文本中的令牌数量
        tokens = client.count_tokens(prompt)

        # 内部调用工具提示的令牌数量映射
        tool_call_inner_prompts_tokens_map = {
            'claude-3-opus-20240229': 395,
            'claude-3-haiku-20240307': 264,
            'claude-3-sonnet-20240229': 159
        }

        # 如果模型在映射中且指定了工具，则增加相应的令牌数量
        if model in tool_call_inner_prompts_tokens_map and tools:
            tokens += tool_call_inner_prompts_tokens_map[model]

        return tokens

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        验证模型的凭证信息

        :param model: 模型名称
        :param credentials: 模型的凭证信息
        :return: 无返回值
        """
        try:
            # 尝试使用提供的模型和凭证信息生成聊天内容，以验证凭证的有效性
            self._chat_generate(
                model=model,
                credentials=credentials,
                prompt_messages=[
                    UserPromptMessage(content="ping"),  # 向模型发送一个简单的"ping"消息作为测试
                ],
                model_parameters={
                    "temperature": 0,  # 设置模型生成回复时的随机性程度
                    "max_tokens": 20,  # 设置生成消息的最大令牌数
                },
                stream=False  # 不以流模式生成回复
            )
        except Exception as ex:
            # 如果在验证过程中发生异常，则抛出自定义的凭证验证失败异常
            raise CredentialsValidateFailedError(str(ex))

    def _handle_chat_generate_response(self, model: str, credentials: dict, response: Union[Message, ToolsBetaMessage],
                                       prompt_messages: list[PromptMessage]) -> LLMResult:
        """
        处理llm聊天响应。

        :param model: 模型名称
        :param credentials: 凭据信息
        :param response: 响应内容，可以是普通消息或工具使用消息
        :param prompt_messages: 提示消息列表
        :return: llm响应结果，包含模型响应、使用情况等信息
        """
        # 将助手消息转换为提示消息
        assistant_prompt_message = AssistantPromptMessage(
            content='',
            tool_calls=[]
        )

        for content in response.content:
            if content.type == 'text':
                assistant_prompt_message.content += content.text
            elif content.type == 'tool_use':
                tool_call = AssistantPromptMessage.ToolCall(
                    id=content.id,
                    type='function',
                    function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                        name=content.name,
                        arguments=json.dumps(content.input)
                    )
                )
                assistant_prompt_message.tool_calls.append(tool_call)

        # 计算token数量
        if response.usage:
            # 已有使用情况，直接转换
            prompt_tokens = response.usage.input_tokens
            completion_tokens = response.usage.output_tokens
        else:
            # 未有使用情况，计算token数量
            prompt_tokens = self.get_num_tokens(model, credentials, prompt_messages)
            completion_tokens = self.get_num_tokens(model, credentials, [assistant_prompt_message])

        # 计算响应的使用情况
        usage = self._calc_response_usage(model, credentials, prompt_tokens, completion_tokens)

        # 转换响应结果
        response = LLMResult(
            model=response.model,
            prompt_messages=prompt_messages,
            message=assistant_prompt_message,
            usage=usage
        )

        return response

    def _handle_chat_generate_stream_response(self, model: str, credentials: dict,
                                              response: Stream[MessageStreamEvent],
                                              prompt_messages: list[PromptMessage]) -> Generator:
        """
        Handle llm chat stream response

        :param model: model name
        :param response: response
        :param prompt_messages: prompt messages
        :return: llm response chunk generator
        """
        full_assistant_content = ''
        return_model = None
        input_tokens = 0
        output_tokens = 0
        finish_reason = None
        index = 0

        tool_calls: list[AssistantPromptMessage.ToolCall] = []

        for chunk in response:
            if isinstance(chunk, MessageStartEvent):
                if hasattr(chunk, 'content_block'):
                    content_block = chunk.content_block
                    if isinstance(content_block, dict):
                        if content_block.get('type') == 'tool_use':
                            tool_call = AssistantPromptMessage.ToolCall(
                                id=content_block.get('id'),
                                type='function',
                                function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                                    name=content_block.get('name'),
                                    arguments=''
                                )
                            )
                            tool_calls.append(tool_call)
                elif hasattr(chunk, 'delta'):
                    delta = chunk.delta
                    if isinstance(delta, dict) and len(tool_calls) > 0:
                        if delta.get('type') == 'input_json_delta':
                            tool_calls[-1].function.arguments += delta.get('partial_json', '')
                elif chunk.message:
                    return_model = chunk.message.model
                    input_tokens = chunk.message.usage.input_tokens
            elif isinstance(chunk, MessageDeltaEvent):
                output_tokens = chunk.usage.output_tokens
                finish_reason = chunk.delta.stop_reason
            elif isinstance(chunk, MessageStopEvent):
                # transform usage
                usage = self._calc_response_usage(model, credentials, input_tokens, output_tokens)

                # transform empty tool call arguments to {}
                for tool_call in tool_calls:
                    if not tool_call.function.arguments:
                        tool_call.function.arguments = '{}'

                yield LLMResultChunk(
                    model=return_model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(
                        index=index + 1,
                        message=AssistantPromptMessage(
                            content='',
                            tool_calls=tool_calls
                        ),
                        finish_reason=finish_reason,
                        usage=usage
                    )
                )
            elif isinstance(chunk, ContentBlockDeltaEvent):
                chunk_text = chunk.delta.text if chunk.delta.text else ''
                full_assistant_content += chunk_text

                    # 将助手消息转换为提示消息
                    assistant_prompt_message = AssistantPromptMessage(
                        content=chunk_text
                    )

                    index = chunk.index  # 更新索引

                    yield LLMResultChunk(
                        model=return_model,
                        prompt_messages=prompt_messages,
                        delta=LLMResultChunkDelta(
                            index=chunk.index,
                            message=assistant_prompt_message,
                        )
                    )

    def _to_credential_kwargs(self, credentials: dict) -> dict:
        """
        将认证信息转换为模型实例的参数

        :param credentials: 包含认证信息的字典，预期包含 'anthropic_api_key' 和可选的 'anthropic_api_url'
        :return: 一个字典，包含用于模型实例的 api_key, timeout, max_retries，以及可选的 base_url
        """
        # 初始化认证参数字典
        credentials_kwargs = {
            "api_key": credentials['anthropic_api_key'],  # 提取API密钥
            "timeout": Timeout(315.0, read=300.0, write=10.0, connect=5.0),  # 设置超时时间
            "max_retries": 1,  # 设置最大重试次数
        }

        if credentials.get('anthropic_api_url'):
            credentials['anthropic_api_url'] = credentials['anthropic_api_url'].rstrip('/')
            credentials_kwargs['base_url'] = credentials['anthropic_api_url']

        return credentials_kwargs

    def _convert_prompt_messages(self, prompt_messages: list[PromptMessage]) -> tuple[str, list[dict]]:
        """
        将提示消息列表转换为字典列表和系统消息。

        参数:
        - prompt_messages: 提示消息列表，包含系统消息、用户消息、助手消息和工具消息。

        返回值:
        - system: 字符串，合并后的系统消息。
        - prompt_message_dicts: 字典列表，转换后的消息列表，每个消息包含角色（用户或助手）和内容。
        """
        system = ""
        first_loop = True
        # 处理系统提示消息，合并为一个字符串
        for message in prompt_messages:
            if isinstance(message, SystemPromptMessage):
                message.content = message.content.strip()
                if first_loop:
                    system = message.content
                    first_loop = False
                else:
                    system += "\n"
                    system += message.content

        prompt_message_dicts = []
        # 处理用户、助手和工具提示消息，转换为字典格式
        for message in prompt_messages:
            if not isinstance(message, SystemPromptMessage):
                if isinstance(message, UserPromptMessage):
                    # 用户消息转换为字典
                    message = cast(UserPromptMessage, message)
                    if isinstance(message.content, str):
                        message_dict = {"role": "user", "content": message.content}
                        prompt_message_dicts.append(message_dict)
                    else:
                        # 处理包含多个子消息的用户消息
                        sub_messages = []
                        for message_content in message.content:
                            if message_content.type == PromptMessageContentType.TEXT:
                                # 文本类型子消息转换
                                message_content = cast(TextPromptMessageContent, message_content)
                                sub_message_dict = {
                                    "type": "text",
                                    "text": message_content.data
                                }
                                sub_messages.append(sub_message_dict)
                            elif message_content.type == PromptMessageContentType.IMAGE:
                                # 图片类型子消息转换，支持从URL获取图片数据
                                message_content = cast(ImagePromptMessageContent, message_content)
                                if not message_content.data.startswith("data:"):
                                    try:
                                        image_content = requests.get(message_content.data).content
                                        mime_type, _ = mimetypes.guess_type(message_content.data)
                                        base64_data = base64.b64encode(image_content).decode('utf-8')
                                    except Exception as ex:
                                        raise ValueError(f"Failed to fetch image data from url {message_content.data}, {ex}")
                                else:
                                    data_split = message_content.data.split(";base64,")
                                    mime_type = data_split[0].replace("data:", "")
                                    base64_data = data_split[1]

                                if mime_type not in ["image/jpeg", "image/png", "image/gif", "image/webp"]:
                                    raise ValueError(f"Unsupported image type {mime_type}, "
                                                    f"only support image/jpeg, image/png, image/gif, and image/webp")

                                sub_message_dict = {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": mime_type,
                                        "data": base64_data
                                    }
                                }
                                sub_messages.append(sub_message_dict)
                        prompt_message_dicts.append({"role": "user", "content": sub_messages})
                elif isinstance(message, AssistantPromptMessage):
                    # 助手消息转换为字典，包括调用的工具和文本内容
                    message = cast(AssistantPromptMessage, message)
                    content = []
                    if message.tool_calls:
                        for tool_call in message.tool_calls:
                            content.append({
                                "type": "tool_use",
                                "id": tool_call.id,
                                "name": tool_call.function.name,
                                "input": json.loads(tool_call.function.arguments)
                            })
                    if message.content:
                        content.append({
                            "type": "text",
                            "text": message.content
                        })
                    
                    if prompt_message_dicts[-1]["role"] == "assistant":
                        prompt_message_dicts[-1]["content"].extend(content)
                    else:
                        prompt_message_dicts.append({
                            "role": "assistant",
                            "content": content
                        })
                elif isinstance(message, ToolPromptMessage):
                    # 工具消息转换为字典
                    message = cast(ToolPromptMessage, message)
                    message_dict = {
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": message.tool_call_id,
                            "content": message.content
                        }]
                    }
                    prompt_message_dicts.append(message_dict)
                else:
                    raise ValueError(f"Got unknown type {message}")

        return system, prompt_message_dicts

    def _convert_one_message_to_text(self, message: PromptMessage) -> str:
        """
        将单个消息对象转换为字符串表示。

        :param message: 需要转换的消息对象，类型为PromptMessage。
        :return: 消息的字符串表示。

        处理不同类型的PromptMessage，将它们转换为包含人类和助手对话的文本格式。
        """

        # 定义人类和助手的提示符
        human_prompt = "\n\nHuman:"
        ai_prompt = "\n\nAssistant:"
        content = message.content

        # 判断消息类型并处理
        if isinstance(message, UserPromptMessage):
            # 用户消息，文本格式
            message_text = f"{human_prompt} {content}"
            # 如果内容不是列表，认为是直接的文本回复
            if not isinstance(message.content, list):
                message_text = f"{ai_prompt} {content}"
            else:
                # 如果是列表，遍历处理每个子消息
                message_text = ""
                for sub_message in message.content:
                    # 支持文本和图片类型的消息
                    if sub_message.type == PromptMessageContentType.TEXT:
                        message_text += f"{human_prompt} {sub_message.data}"
                    elif sub_message.type == PromptMessageContentType.IMAGE:
                        message_text += f"{human_prompt} [IMAGE]"
        elif isinstance(message, AssistantPromptMessage):
            # 助手消息，文本格式
            if not isinstance(message.content, list):
                message_text = f"{ai_prompt} {content}"
            else:
                # 如果是列表，遍历处理每个子消息
                message_text = ""
                for sub_message in message.content:
                    if sub_message.type == PromptMessageContentType.TEXT:
                        message_text += f"{ai_prompt} {sub_message.data}"
                    elif sub_message.type == PromptMessageContentType.IMAGE:
                        message_text += f"{ai_prompt} [IMAGE]"
        elif isinstance(message, SystemPromptMessage):
            # 系统消息，直接使用内容
            message_text = content
        elif isinstance(message, ToolPromptMessage):
            # 工具消息，格式化为人类发出的消息
            message_text = f"{human_prompt} {message.content}"
        else:
            # 未知类型的消息，抛出异常
            raise ValueError(f"Got unknown type {message}")

        return message_text

    def _convert_messages_to_prompt_anthropic(self, messages: list[PromptMessage]) -> str:
        """
        将消息列表格式化为适用于Anthropic模型的完整提示

        :param messages: 需要合并的PromptMessage列表。
        :return: 合并后的字符串，包含必要的human_prompt和ai_prompt标签。
        """
        # 如果消息列表为空，则直接返回空字符串
        if not messages:
            return ''

        # 复制消息列表，避免修改原始列表
        messages = messages.copy()  
        # 确保列表末尾是一个AssistantPromptMessage，如果不是，则追加一个空的AssistantPromptMessage
        if not isinstance(messages[-1], AssistantPromptMessage):
            messages.append(AssistantPromptMessage(content=""))

        # 将每个消息转换为文本并合并
        text = "".join(
            self._convert_one_message_to_text(message)
            for message in messages
        )

        # 删除可能由"Assistant: "带来的尾部空格
        return text.rstrip()

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        """
        映射模型调用错误到统一错误
        键是抛给调用者的错误类型
        值是模型抛出的错误类型，需要被转换成统一的错误类型给调用者。

        :return: 调用错误映射字典
        """
        return {
            InvokeConnectionError: [
                anthropic.APIConnectionError,
                anthropic.APITimeoutError  # 连接错误相关映射
            ],
            InvokeServerUnavailableError: [
                anthropic.InternalServerError  # 服务器不可用错误相关映射
            ],
            InvokeRateLimitError: [
                anthropic.RateLimitError  # 速率限制错误相关映射
            ],
            InvokeAuthorizationError: [
                anthropic.AuthenticationError,
                anthropic.PermissionDeniedError  # 授权错误相关映射
            ],
            InvokeBadRequestError: [
                anthropic.BadRequestError,
                anthropic.NotFoundError,
                anthropic.UnprocessableEntityError,
                anthropic.APIError  # 请求错误相关映射
            ]
        }
