import logging
import os
import re
import time
from abc import abstractmethod
from collections.abc import Generator
from typing import Optional, Union

from pydantic import ConfigDict

from core.model_runtime.callbacks.base_callback import Callback
from core.model_runtime.callbacks.logging_callback import LoggingCallback
from core.model_runtime.entities.llm_entities import LLMMode, LLMResult, LLMResultChunk, LLMResultChunkDelta, LLMUsage
from core.model_runtime.entities.message_entities import (
    AssistantPromptMessage,
    PromptMessage,
    PromptMessageContentType,
    PromptMessageTool,
    SystemPromptMessage,
    UserPromptMessage,
)
from core.model_runtime.entities.model_entities import (
    ModelPropertyKey,
    ModelType,
    ParameterRule,
    ParameterType,
    PriceType,
)
from core.model_runtime.model_providers.__base.ai_model import AIModel

logger = logging.getLogger(__name__)


class LargeLanguageModel(AIModel):
    """
    大规模语言模型的模型类。
    """

    model_type: ModelType = ModelType.LLM

    # pydantic configs
    model_config = ConfigDict(protected_namespaces=())

    def invoke(self, model: str, credentials: dict,
               prompt_messages: list[PromptMessage], model_parameters: Optional[dict] = None,
               tools: Optional[list[PromptMessageTool]] = None, stop: Optional[list[str]] = None,
               stream: bool = True, user: Optional[str] = None, callbacks: list[Callback] = None) \
            -> Union[LLMResult, Generator]:
        """
        调用大规模语言模型。

        :param model: 模型名称。
        :param credentials: 模型凭证。
        :param prompt_messages: 提示信息列表。
        :param model_parameters: 模型参数，可选。
        :param tools: 工具列表，用于工具调用，可选。
        :param stop: 停止词列表，可选。
        :param stream: 是否流式返回响应，默认为True。
        :param user: 唯一的用户ID，可选。
        :param callbacks: 回调列表，可选。
        :return: 全部响应或流式响应块生成器结果。
        """
        # 验证并过滤模型参数
        if model_parameters is None:
            model_parameters = {}

        model_parameters = self._validate_and_filter_model_parameters(model, model_parameters, credentials)

        self.started_at = time.perf_counter()

        callbacks = callbacks or []

        # 如果环境变量DEBUG为True，添加日志回调
        if bool(os.environ.get("DEBUG", 'False').lower() == 'true'):
            callbacks.append(LoggingCallback())

        # 触发调用前的回调
        self._trigger_before_invoke_callbacks(
            model=model,
            credentials=credentials,
            prompt_messages=prompt_messages,
            model_parameters=model_parameters,
            tools=tools,
            stop=stop,
            stream=stream,
            user=user,
            callbacks=callbacks
        )

        try:
            # 根据模型参数中的response_format决定调用方式
            if "response_format" in model_parameters:
                result = self._code_block_mode_wrapper(
                    model=model,
                    credentials=credentials,
                    prompt_messages=prompt_messages,
                    model_parameters=model_parameters,
                    tools=tools,
                    stop=stop,
                    stream=stream,
                    user=user,
                    callbacks=callbacks
                )
            else:
                result = self._invoke(model, credentials, prompt_messages, model_parameters, tools, stop, stream, user)
        except Exception as e:
            # 触发调用错误的回调
            self._trigger_invoke_error_callbacks(
                model=model,
                ex=e,
                credentials=credentials,
                prompt_messages=prompt_messages,
                model_parameters=model_parameters,
                tools=tools,
                stop=stop,
                stream=stream,
                user=user,
                callbacks=callbacks
            )

            raise self._transform_invoke_error(e)

        # 根据是否流式返回处理结果
        if stream and isinstance(result, Generator):
            return self._invoke_result_generator(
                model=model,
                result=result,
                credentials=credentials,
                prompt_messages=prompt_messages,
                model_parameters=model_parameters,
                tools=tools,
                stop=stop,
                stream=stream,
                user=user,
                callbacks=callbacks
            )
        else:
            # 触发调用后的回调
            self._trigger_after_invoke_callbacks(
                model=model,
                result=result,
                credentials=credentials,
                prompt_messages=prompt_messages,
                model_parameters=model_parameters,
                tools=tools,
                stop=stop,
                stream=stream,
                user=user,
                callbacks=callbacks
            )

        return result

    def _code_block_mode_wrapper(self, model: str, credentials: dict, prompt_messages: list[PromptMessage],
                            model_parameters: dict, tools: Optional[list[PromptMessageTool]] = None,
                            stop: Optional[list[str]] = None, stream: bool = True, user: Optional[str] = None,
                            callbacks: list[Callback] = None) -> Union[LLMResult, Generator]:
        """
        Code block 模式包装器，确保响应是一个带有输出 Markdown 引用的代码块

        :param model: 模型名称
        :param credentials: 模型凭证
        :param prompt_messages: 提示信息
        :param model_parameters: 模型参数
        :param tools: 工具调用
        :param stop: 停止词
        :param stream: 是否流式响应
        :param user: 唯一用户ID
        :param callbacks: 回调
        :return: 完整响应或流式响应块生成器结果
        """

        # 定义代码块提示信息模板
        block_prompts = """You should always follow the instructions and output a valid {{block}} object.
The structure of the {{block}} object you can found in the instructions, use {"answer": "$your_answer"} as the default structure
if you are not sure about the structure.

<instructions>
{{instructions}}
</instructions>
"""

        # 检查并处理响应格式设置
        code_block = model_parameters.get("response_format", "")
        if not code_block:
            return self._invoke(
                model=model,
                credentials=credentials,
                prompt_messages=prompt_messages,
                model_parameters=model_parameters,
                tools=tools,
                stop=stop,
                stream=stream,
                user=user
            )
        
        # 从模型参数中移除响应格式设置，并更新停止词
        model_parameters.pop("response_format")
        stop = stop or []
        stop.extend(["\n```", "```\n"])
        block_prompts = block_prompts.replace("{{block}}", code_block)

        # 检查并插入系统提示信息
        if len(prompt_messages) > 0 and isinstance(prompt_messages[0], SystemPromptMessage):
            # 重写系统提示信息
            prompt_messages[0] = SystemPromptMessage(
                content=block_prompts
                    .replace("{{instructions}}", prompt_messages[0].content)
            )
        else:
            # 插入系统提示信息
            prompt_messages.insert(0, SystemPromptMessage(
                content=block_prompts
                    .replace("{{instructions}}", f"Please output a valid {code_block} object.")
            ))

        # 检查并更新最后一个提示信息，以确保其以代码块格式结束
        if len(prompt_messages) > 0 and isinstance(prompt_messages[-1], UserPromptMessage):
            # add ```JSON\n to the last text message
            if isinstance(prompt_messages[-1].content, str):
                prompt_messages[-1].content += f"\n```{code_block}\n"
            elif isinstance(prompt_messages[-1].content, list):
                for i in range(len(prompt_messages[-1].content) - 1, -1, -1):
                    if prompt_messages[-1].content[i].type == PromptMessageContentType.TEXT:
                        prompt_messages[-1].content[i].data += f"\n```{code_block}\n"
                        break
        else:
            # 添加用户消息以结束代码块
            prompt_messages.append(UserPromptMessage(
                content=f"```{code_block}\n"
            ))

        # 调用内部方法进行处理，并根据响应类型进行流式处理
        response = self._invoke(
            model=model,
            credentials=credentials,
            prompt_messages=prompt_messages,
            model_parameters=model_parameters,
            tools=tools,
            stop=stop,
            stream=stream,
            user=user
        )

        # 对流式响应进行额外的代码块格式处理
        if isinstance(response, Generator):
            first_chunk = next(response)
            def new_generator():
                yield first_chunk
                yield from response

            if first_chunk.delta.message.content and first_chunk.delta.message.content.startswith("`"):
                return self._code_block_mode_stream_processor_with_backtick(
                    model=model,
                    prompt_messages=prompt_messages,
                    input_generator=new_generator()
                )
            else:
                return self._code_block_mode_stream_processor(
                    model=model,
                    prompt_messages=prompt_messages,
                    input_generator=new_generator()
                )
        
        return response

    def _code_block_mode_stream_processor(self, model: str, prompt_messages: list[PromptMessage], 
                                        input_generator: Generator[LLMResultChunk, None, None]
                                        ) -> Generator[LLMResultChunk, None, None]:
        """
        Code block模式流处理器，确保响应是一个带有输出Markdown引用的代码块。

        :param model: 模型名称
        :param prompt_messages: 提示信息列表
        :param input_generator: 输入生成器，产生LLMResultChunk对象
        :return: 输出生成器，产生处理后的LLMResultChunk对象
        """
        state = "normal"  # 当前处理状态：正常、在反引号中、跳过内容
        backtick_count = 0  # 反引号计数，用于识别代码块开始和结束

        # 遍历输入生成器中的每个片段
        for piece in input_generator:
            # 如果片段中包含内容，则清空内容并直接产出，准备处理下一个片段
            if piece.delta.message.content:
                content = piece.delta.message.content
                piece.delta.message.content = ""
                yield piece
                piece = content
            else:
                yield piece
                continue  # 忽略空内容的片段

            new_piece = ""  # 用于构建处理后的新内容

            # 根据当前状态处理片段中的每个字符
            for char in piece:
                if state == "normal":
                    if char == "`":
                        state = "in_backticks"
                        backtick_count = 1
                    else:
                        new_piece += char
                elif state == "in_backticks":
                    if char == "`":
                        backtick_count += 1
                        if backtick_count == 3:
                            state = "skip_content"
                            backtick_count = 0
                    else:
                        new_piece += "`" * backtick_count + char
                        state = "normal"
                        backtick_count = 0
                elif state == "skip_content":
                    if char.isspace():
                        state = "normal"  # 当遇到空格时，结束跳过内容的状态，返回正常状态

            # 如果处理后的新内容不为空，则产出一个新的LLMResultChunk对象
            if new_piece:
                yield LLMResultChunk(
                    model=model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(
                        index=0,
                        message=AssistantPromptMessage(
                            content=new_piece,
                            tool_calls=[]
                        ),
                    )
                )

    def _code_block_mode_stream_processor_with_backtick(self, model: str, prompt_messages: list, 
                                            input_generator:  Generator[LLMResultChunk, None, None]) \
                                        ->  Generator[LLMResultChunk, None, None]:
        """
        Code block模式流处理器，确保响应是一个带有输出Markdown引用的代码块。此版本跳过开头三反引号后跟随的语言标识符。

        :param model: 模型名称
        :param prompt_messages: 提示信息列表
        :param input_generator: 输入生成器，产生LLMResultChunk对象
        :return: 输出生成器，产生处理后的LLMResultChunk对象
        """
        state = "search_start"  # 当前处理状态
        backtick_count = 0  # 反引号计数

        for piece in input_generator:
            if piece.delta.message.content:
                content = piece.delta.message.content
                # 重置内容，确保只处理和产生相关部分
                piece.delta.message.content = ""
                # 在处理之前产生一个内容被清空的piece，以保持生成器结构
                yield piece
                piece = content
            else:
                # 直接产生没有内容的piece
                yield piece
                continue

            if state == "done":
                continue

            new_piece = ""
            for char in piece:
                if state == "search_start":
                    if char == "`":
                        backtick_count += 1
                        if backtick_count == 3:
                            state = "skip_language"
                            backtick_count = 0
                    else:
                        backtick_count = 0
                elif state == "skip_language":
                    # 跳过直到第一个换行符的所有内容，标志着语言标识符的结束
                    if char == "\n":
                        state = "in_code_block"
                elif state == "in_code_block":
                    if char == "`":
                        backtick_count += 1
                        if backtick_count == 3:
                            state = "done"
                            break
                    else:
                        if backtick_count > 0:
                            # 如果计数了反引号但仍在收集内容，则是一个错误的开始
                            new_piece += "`" * backtick_count
                            backtick_count = 0
                        new_piece += char

                elif state == "done":
                    break

            if new_piece:
                # 仅产生代码块内的内容
                yield LLMResultChunk(
                    model=model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(
                        index=0,
                        message=AssistantPromptMessage(
                            content=new_piece,
                            tool_calls=[]
                        ),
                    )
                )

    def _invoke_result_generator(self, model: str, result: Generator, credentials: dict,
                                    prompt_messages: list[PromptMessage], model_parameters: dict,
                                    tools: Optional[list[PromptMessageTool]] = None,
                                    stop: Optional[list[str]] = None, stream: bool = True,
                                    user: Optional[str] = None, callbacks: list[Callback] = None) -> Generator:
        """
        调用结果生成器。

        :param model: 使用的模型名称。
        :param result: 结果生成器，用于迭代获取结果片段。
        :param credentials: 用于模型调用的凭证信息。
        :param prompt_messages: 与模型交互时的提示信息列表。
        :param model_parameters: 模型调用时的参数。
        :param tools: 辅助工具列表，用于在与模型交互时提供额外的功能。
        :param stop: 停止信号列表，用于在满足特定条件时终止生成器的迭代。
        :param stream: 是否流式处理结果，默认为True。
        :param user: 用户标识，用于标识调用结果生成器的用户。
        :param callbacks: 在处理结果时触发的回调列表。
        :return: 返回一个生成器，该生成器迭代处理结果并触发相应的回调函数。
        """
        # 初始化提示消息和使用信息
        prompt_message = AssistantPromptMessage(
            content=""
        )
        usage = None
        system_fingerprint = None
        real_model = model

        try:
            # 迭代处理结果生成器中的每个片段
            for chunk in result:
                yield chunk

                # 触发处理每个结果片段的回调
                self._trigger_new_chunk_callbacks(
                    chunk=chunk,
                    model=model,
                    credentials=credentials,
                    prompt_messages=prompt_messages,
                    model_parameters=model_parameters,
                    tools=tools,
                    stop=stop,
                    stream=stream,
                    user=user,
                    callbacks=callbacks
                )

                # 更新提示消息和追踪模型使用信息
                prompt_message.content += chunk.delta.message.content
                real_model = chunk.model
                if chunk.delta.usage:
                    usage = chunk.delta.usage

                # 更新系统指纹信息
                if chunk.system_fingerprint:
                    system_fingerprint = chunk.system_fingerprint
        except Exception as e:
            # 将捕获到的异常转换为适当的错误并抛出
            raise self._transform_invoke_error(e)

        # 触发调用结果处理完成后的回调
        self._trigger_after_invoke_callbacks(
            model=model,
            result=LLMResult(
                model=real_model,
                prompt_messages=prompt_messages,
                message=prompt_message,
                usage=usage if usage else LLMUsage.empty_usage(),
                system_fingerprint=system_fingerprint
            ),
            credentials=credentials,
            prompt_messages=prompt_messages,
            model_parameters=model_parameters,
            tools=tools,
            stop=stop,
            stream=stream,
            user=user,
            callbacks=callbacks
        )

    @abstractmethod
    def _invoke(self, model: str, credentials: dict,
                prompt_messages: list[PromptMessage], model_parameters: dict,
                tools: Optional[list[PromptMessageTool]] = None, stop: Optional[list[str]] = None,
                stream: bool = True, user: Optional[str] = None) \
            -> Union[LLMResult, Generator]:
        """
        调用大型语言模型

        :param model: 模型名称
        :param credentials: 模型凭证
        :param prompt_messages: 提示信息列表
        :param model_parameters: 模型参数
        :param tools: 工具列表，用于工具调用
        :param stop: 停止词列表
        :param stream: 是否流式返回响应
        :param user: 唯一的用户ID
        :return: 全部响应或流式响应片段生成器结果
        """
        raise NotImplementedError
    
    @abstractmethod
    def get_num_tokens(self, model: str, credentials: dict, prompt_messages: list[PromptMessage],
                    tools: Optional[list[PromptMessageTool]] = None) -> int:
        """
        获取给定提示消息的令牌数量

        :param model: 模型名称
        :param credentials: 模型凭证
        :param prompt_messages: 提示消息列表
        :param tools: 工具列表，用于工具调用（可选）
        :return: 返回令牌数量
        """
        raise NotImplementedError

    def enforce_stop_tokens(self, text: str, stop: list[str]) -> str:
        """
        当遇到任何停止词时，立即截断文本。
        
        参数:
        text: str - 需要进行截断处理的文本字符串。
        stop: list[str] - 停止词列表，一旦文本中出现这些词，就会被截断。
        
        返回值:
        str - 截断后的文本字符串。
        """
        # 使用正则表达式根据停止词列表截断文本，只截断第一个遇到的停止词
        return re.split("|".join(stop), text, maxsplit=1)[0]

    def _llm_result_to_stream(self, result: LLMResult) -> Generator:
        """
        将llm结果转换为流

        :param result: llm结果
        :return: 流
        """
        index = 0  # 初始化索引

        tool_calls = result.message.tool_calls  # 提取工具调用信息

        # 遍历结果中的每个单词
        for word in result.message.content:
            # 为最后一个单词设置工具调用信息，否则设置为空列表
            assistant_prompt_message = AssistantPromptMessage(
                content=word,
                tool_calls=tool_calls if index == (len(result.message.content) - 1) else []
            )

            # 生成并返回每个单词对应的LLMResultChunk对象
            yield LLMResultChunk(
                model=result.model,
                prompt_messages=result.prompt_messages,
                system_fingerprint=result.system_fingerprint,
                delta=LLMResultChunkDelta(
                    index=index,
                    message=assistant_prompt_message,
                )
            )

            index += 1  # 更新索引
            time.sleep(0.01)  # 每处理一个单词短暂停顿

    def get_parameter_rules(self, model: str, credentials: dict) -> list[ParameterRule]:
        """
        获取参数规则

        :param model: 模型名称
        :param credentials: 模型凭证
        :return: 参数规则列表
        """
        # 根据模型名称和凭证获取模型架构
        model_schema = self.get_model_schema(model, credentials)
        if model_schema:
            # 如果模型架构存在，则返回其参数规则
            return model_schema.parameter_rules

        # 如果模型架构不存在，返回空列表
        return []

    def get_model_mode(self, model: str, credentials: Optional[dict] = None) -> LLMMode:
        """
        获取模型模式

        :param model: 模型名称
        :param credentials: 模型凭证，可选
        :return: 模型模式
        """
        # 根据模型名称和凭证获取模型架构
        model_schema = self.get_model_schema(model, credentials)

        # 默认模式为聊天模式
        mode = LLMMode.CHAT
        # 如果模型架构存在且指定了模式，则更新模式
        if model_schema and model_schema.model_properties.get(ModelPropertyKey.MODE):
            mode = LLMMode.value_of(model_schema.model_properties[ModelPropertyKey.MODE])

        return mode

    def _calc_response_usage(self, model: str, credentials: dict, prompt_tokens: int, completion_tokens: int) -> LLMUsage:
        """
        计算响应使用情况

        :param model: 模型名称
        :param credentials: 模型凭证
        :param prompt_tokens: 提示令牌数量
        :param completion_tokens: 完成令牌数量
        :return: 使用情况
        """
        # 获取提示价格信息
        prompt_price_info = self.get_price(
            model=model,
            credentials=credentials,
            price_type=PriceType.INPUT,
            tokens=prompt_tokens,
        )

        # 获取完成价格信息
        completion_price_info = self.get_price(
            model=model,
            credentials=credentials,
            price_type=PriceType.OUTPUT,
            tokens=completion_tokens
        )

        # 转换使用情况
        usage = LLMUsage(
            prompt_tokens=prompt_tokens,
            prompt_unit_price=prompt_price_info.unit_price,
            prompt_price_unit=prompt_price_info.unit,
            prompt_price=prompt_price_info.total_amount,
            completion_tokens=completion_tokens,
            completion_unit_price=completion_price_info.unit_price,
            completion_price_unit=completion_price_info.unit,
            completion_price=completion_price_info.total_amount,
            total_tokens=prompt_tokens + completion_tokens,
            total_price=prompt_price_info.total_amount + completion_price_info.total_amount,
            currency=prompt_price_info.currency,
            latency=time.perf_counter() - self.started_at
        )

        return usage

    def _trigger_before_invoke_callbacks(self, model: str, credentials: dict,
                                         prompt_messages: list[PromptMessage], model_parameters: dict,
                                         tools: Optional[list[PromptMessageTool]] = None,
                                         stop: Optional[list[str]] = None, stream: bool = True,
                                         user: Optional[str] = None, callbacks: list[Callback] = None) -> None:
        """
        触发调用前的回调函数。

        :param model: 模型名称
        :param credentials: 模型凭证
        :param prompt_messages: 提示信息列表
        :param model_parameters: 模型参数
        :param tools: 工具列表，用于工具调用
        :param stop: 停止词列表
        :param stream: 是否流式响应
        :param user: 唯一用户ID
        :param callbacks: 回调函数列表
        """

        # 如果提供了回调函数列表，则遍历每个回调函数进行调用
        if callbacks:
            for callback in callbacks:
                try:
                    # 调用回调函数的on_before_invoke方法
                    callback.on_before_invoke(
                        llm_instance=self,
                        model=model,
                        credentials=credentials,
                        prompt_messages=prompt_messages,
                        model_parameters=model_parameters,
                        tools=tools,
                        stop=stop,
                        stream=stream,
                        user=user
                    )
                except Exception as e:
                    # 根据回调函数的设置，决定是否抛出异常
                    if callback.raise_error:
                        raise e
                    else:
                        # 如果不抛出异常，则记录警告信息
                        logger.warning(f"Callback {callback.__class__.__name__} on_before_invoke failed with error {e}")

    def _trigger_new_chunk_callbacks(self, chunk: LLMResultChunk, model: str, credentials: dict,
                                    prompt_messages: list[PromptMessage], model_parameters: dict,
                                    tools: Optional[list[PromptMessageTool]] = None,
                                    stop: Optional[list[str]] = None, stream: bool = True,
                                    user: Optional[str] = None, callbacks: list[Callback] = None) -> None:
        """
        触发新的数据块回调。

        :param chunk: 数据块对象，包含模型输出的结果片段。
        :param model: 模型名称，标识使用的是哪个语言模型。
        :param credentials: 模型认证信息，用于访问和使用模型。
        :param prompt_messages: 提示信息列表，可能包含与数据块相关的输入提示。
        :param model_parameters: 模型参数，用于配置模型的行为。
        :param tools: 工具列表，用于调用与工具相关的功能。
        :param stop: 停止词列表，用于指示何时停止生成输出。
        :param stream: 是否流式响应，控制输出是否一次性返回或分段返回。
        :param user: 唯一的用户ID，用于标识请求的用户。
        :param callbacks: 回调列表，包含需要被触发的回调函数对象。
        :return: 无返回值。
        """
        if callbacks:
            # 遍历回调列表，依次调用每个回调函数
            for callback in callbacks:
                try:
                    callback.on_new_chunk(
                        llm_instance=self,
                        chunk=chunk,
                        model=model,
                        credentials=credentials,
                        prompt_messages=prompt_messages,
                        model_parameters=model_parameters,
                        tools=tools,
                        stop=stop,
                        stream=stream,
                        user=user
                    )
                except Exception as e:
                    # 处理回调函数执行时产生的异常
                    if callback.raise_error:
                        raise e
                    else:
                        logger.warning(f"Callback {callback.__class__.__name__} on_new_chunk failed with error {e}")

    def _trigger_after_invoke_callbacks(self, model: str, result: LLMResult, credentials: dict,
                                            prompt_messages: list[PromptMessage], model_parameters: dict,
                                            tools: Optional[list[PromptMessageTool]] = None,
                                            stop: Optional[list[str]] = None, stream: bool = True,
                                            user: Optional[str] = None, callbacks: list[Callback] = None) -> None:
        """
        触发调用后回调

        :param model: 模型名称
        :param result: 结果
        :param credentials: 模型凭证
        :param prompt_messages: 提示信息
        :param model_parameters: 模型参数
        :param tools: 工具调用支持
        :param stop: 停止词
        :param stream: 是否为流式响应
        :param user: 唯一用户ID
        :param callbacks: 回调列表
        """

        # 如果存在回调列表，则遍历执行每个回调函数
        if callbacks:
            for callback in callbacks:
                try:
                    # 执行回调函数的 on_after_invoke 方法，并传递相关参数
                    callback.on_after_invoke(
                        llm_instance=self,
                        result=result,
                        model=model,
                        credentials=credentials,
                        prompt_messages=prompt_messages,
                        model_parameters=model_parameters,
                        tools=tools,
                        stop=stop,
                        stream=stream,
                        user=user
                    )
                except Exception as e:
                    # 根据回调函数的 raise_error 属性决定是否抛出异常
                    if callback.raise_error:
                        raise e
                    else:
                        # 如果不抛出异常，则记录警告信息
                        logger.warning(f"Callback {callback.__class__.__name__} on_after_invoke failed with error {e}")

    def _trigger_invoke_error_callbacks(self, model: str, ex: Exception, credentials: dict,
                                            prompt_messages: list[PromptMessage], model_parameters: dict,
                                            tools: Optional[list[PromptMessageTool]] = None,
                                            stop: Optional[list[str]] = None, stream: bool = True,
                                            user: Optional[str] = None, callbacks: list[Callback] = None) -> None:
        """
        触发调用错误回调函数
        
        :param model: 模型名称
        :param ex: 异常对象
        :param credentials: 模型认证信息
        :param prompt_messages: 提示信息列表
        :param model_parameters: 模型参数
        :param tools: 工具列表，用于工具调用
        :param stop: 停止词列表
        :param stream: 是否为流式响应
        :param user: 唯一用户ID
        :param callbacks: 回调函数列表
        """

        # 如果存在回调函数，则遍历执行每个回调
        if callbacks:
            for callback in callbacks:
                try:
                    # 执行回调函数的on_invoke_error方法，并传递相关参数
                    callback.on_invoke_error(
                        llm_instance=self,
                        ex=ex,
                        model=model,
                        credentials=credentials,
                        prompt_messages=prompt_messages,
                        model_parameters=model_parameters,
                        tools=tools,
                        stop=stop,
                        stream=stream,
                        user=user
                    )
                except Exception as e:
                    # 如果回调函数设置为出现错误时抛出异常，则重新抛出错误；否则记录警告信息
                    if callback.raise_error:
                        raise e
                    else:
                        logger.warning(f"Callback {callback.__class__.__name__} on_invoke_error failed with error {e}")

    def _validate_and_filter_model_parameters(self, model: str, model_parameters: dict, credentials: dict) -> dict:
        """
        验证并过滤模型参数

        :param model: 模型名称
        :param model_parameters: 模型参数
        :param credentials: 模型凭证
        :return: 过滤后的模型参数字典
        """
        # 根据模型和凭证获取参数规则
        parameter_rules = self.get_parameter_rules(model, credentials)

        # 验证并过滤模型参数
        filtered_model_parameters = {}
        for parameter_rule in parameter_rules:
            parameter_name = parameter_rule.name
            parameter_value = model_parameters.get(parameter_name)
            if parameter_value is None:
                # 如果参数值为None，尝试使用模板值变量名替代
                if parameter_rule.use_template and parameter_rule.use_template in model_parameters:
                    parameter_value = model_parameters[parameter_rule.use_template]
                else:
                    # 判断参数是否必需，若非必需则跳过，若是必需但无默认值，则抛出异常
                    if parameter_rule.required:
                        if parameter_rule.default is not None:
                            filtered_model_parameters[parameter_name] = parameter_rule.default
                            continue
                        else:
                            raise ValueError(f"Model Parameter {parameter_name} is required.")
                    else:
                        continue

            # 根据参数规则验证参数值类型及范围
            if parameter_rule.type == ParameterType.INT:
                if not isinstance(parameter_value, int):
                    raise ValueError(f"Model Parameter {parameter_name} should be int.")

                # 验证整型参数的取值范围
                if parameter_rule.min is not None and parameter_value < parameter_rule.min:
                    raise ValueError(
                        f"Model Parameter {parameter_name} should be greater than or equal to {parameter_rule.min}.")

                if parameter_rule.max is not None and parameter_value > parameter_rule.max:
                    raise ValueError(
                        f"Model Parameter {parameter_name} should be less than or equal to {parameter_rule.max}.")
            elif parameter_rule.type == ParameterType.FLOAT:
                if not isinstance(parameter_value, float | int):
                    raise ValueError(f"Model Parameter {parameter_name} should be float.")

                # 验证浮点型参数的精度和取值范围
                if parameter_rule.precision is not None:
                    if parameter_rule.precision == 0:
                        if parameter_value != int(parameter_value):
                            raise ValueError(f"Model Parameter {parameter_name} should be int.")
                    else:
                        if parameter_value != round(parameter_value, parameter_rule.precision):
                            raise ValueError(
                                f"Model Parameter {parameter_name} should be round to {parameter_rule.precision} decimal places.")

                if parameter_rule.min is not None and parameter_value < parameter_rule.min:
                    raise ValueError(
                        f"Model Parameter {parameter_name} should be greater than or equal to {parameter_rule.min}.")

                if parameter_rule.max is not None and parameter_value > parameter_rule.max:
                    raise ValueError(
                        f"Model Parameter {parameter_name} should be less than or equal to {parameter_rule.max}.")
            elif parameter_rule.type == ParameterType.BOOLEAN:
                if not isinstance(parameter_value, bool):
                    raise ValueError(f"Model Parameter {parameter_name} should be bool.")
            elif parameter_rule.type == ParameterType.STRING:
                if not isinstance(parameter_value, str):
                    raise ValueError(f"Model Parameter {parameter_name} should be string.")

                # 验证字符串参数是否符合指定选项
                if parameter_rule.options and parameter_value not in parameter_rule.options:
                    raise ValueError(f"Model Parameter {parameter_name} should be one of {parameter_rule.options}.")
            else:
                raise ValueError(f"Model Parameter {parameter_name} type {parameter_rule.type} is not supported.")

            filtered_model_parameters[parameter_name] = parameter_value

        return filtered_model_parameters
