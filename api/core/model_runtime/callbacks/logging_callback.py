import json
import logging
import sys
from typing import Optional

from core.model_runtime.callbacks.base_callback import Callback
from core.model_runtime.entities.llm_entities import LLMResult, LLMResultChunk
from core.model_runtime.entities.message_entities import PromptMessage, PromptMessageTool
from core.model_runtime.model_providers.__base.ai_model import AIModel

logger = logging.getLogger(__name__)

class LoggingCallback(Callback):
    def on_before_invoke(self, llm_instance: AIModel, model: str, credentials: dict,
                        prompt_messages: list[PromptMessage], model_parameters: dict,
                        tools: Optional[list[PromptMessageTool]] = None, stop: Optional[list[str]] = None,
                        stream: bool = True, user: Optional[str] = None) -> None:
        """
        在调用AI模型之前执行的回调函数。

        :param llm_instance: LLM实例
        :param model: 模型名称
        :param credentials: 模型认证信息
        :param prompt_messages: 提示信息列表
        :param model_parameters: 模型参数
        :param tools: 工具列表，用于工具调用
        :param stop: 停止词列表
        :param stream: 是否流式响应
        :param user: 唯一用户ID
        """
        # 打印调用前的基本信息
        self.print_text("\n[on_llm_before_invoke]\n", color='blue')
        self.print_text(f"Model: {model}\n", color='blue')
        self.print_text("Parameters:\n", color='blue')
        # 打印模型参数
        for key, value in model_parameters.items():
            self.print_text(f"\t{key}: {value}\n", color='blue')

        # 如果有停止词，打印停止词
        if stop:
            self.print_text(f"\tstop: {stop}\n", color='blue')

        # 如果有工具，打印工具信息
        if tools:
            self.print_text("\tTools:\n", color='blue')
            for tool in tools:
                self.print_text(f"\t\t{tool.name}\n", color='blue')

        # 打印是否流式响应
        self.print_text(f"Stream: {stream}\n", color='blue')

        # 如果有用户ID，打印用户ID
        if user:
            self.print_text(f"User: {user}\n", color='blue')

        # 打印提示信息
        self.print_text("Prompt messages:\n", color='blue')
        for prompt_message in prompt_messages:
            if prompt_message.name:
                self.print_text(f"\tname: {prompt_message.name}\n", color='blue')

            self.print_text(f"\trole: {prompt_message.role.value}\n", color='blue')
            self.print_text(f"\tcontent: {prompt_message.content}\n", color='blue')

        # 如果是流式响应，额外打印信息
        if stream:
            self.print_text("\n[on_llm_new_chunk]")

    def on_new_chunk(self, llm_instance: AIModel, chunk: LLMResultChunk, model: str, credentials: dict,
                    prompt_messages: list[PromptMessage], model_parameters: dict,
                    tools: Optional[list[PromptMessageTool]] = None, stop: Optional[list[str]] = None,
                    stream: bool = True, user: Optional[str] = None):
        """
        当接收到新的数据块时的回调函数。

        :param llm_instance: LLM 实例
        :param chunk: 数据块，包含LLM的结果
        :param model: 模型名称
        :param credentials: 模型的认证信息
        :param prompt_messages: 提示信息列表
        :param model_parameters: 模型参数
        :param tools: 用于调用工具的列表
        :param stop: 停止词列表
        :param stream: 是否流式响应
        :param user: 唯一的用户ID
        """
        # 将接收到的数据块内容输出到标准输出
        sys.stdout.write(chunk.delta.message.content)
        sys.stdout.flush()

    def on_after_invoke(self, llm_instance: AIModel, result: LLMResult, model: str, credentials: dict,
                        prompt_messages: list[PromptMessage], model_parameters: dict,
                        tools: Optional[list[PromptMessageTool]] = None, stop: Optional[list[str]] = None,
                        stream: bool = True, user: Optional[str] = None) -> None:
        """
        调用后回调函数

        :param llm_instance: LLM实例
        :param result: 结果对象
        :param model: 模型名称
        :param credentials: 模型凭证
        :param prompt_messages: 提示信息列表
        :param model_parameters: 模型参数
        :param tools: 工具调用列表，用于工具调用
        :param stop: 停止词列表
        :param stream: 是否流式响应
        :param user: 唯一用户ID
        """
        # 打印调用后的基础信息
        self.print_text("\n[on_llm_after_invoke]\n", color='yellow')
        self.print_text(f"Content: {result.message.content}\n", color='yellow')

        # 如果有工具调用，打印工具调用的详细信息
        if result.message.tool_calls:
            self.print_text("Tool calls:\n", color='yellow')
            for tool_call in result.message.tool_calls:
                self.print_text(f"\t{tool_call.id}\n", color='yellow')
                self.print_text(f"\t{tool_call.function.name}\n", color='yellow')
                self.print_text(f"\t{json.dumps(tool_call.function.arguments)}\n", color='yellow')

        # 打印模型、使用情况和系统指纹信息
        self.print_text(f"Model: {result.model}\n", color='yellow')
        self.print_text(f"Usage: {result.usage}\n", color='yellow')
        self.print_text(f"System Fingerprint: {result.system_fingerprint}\n", color='yellow')

    def on_invoke_error(self, llm_instance: AIModel, ex: Exception, model: str, credentials: dict,
                        prompt_messages: list[PromptMessage], model_parameters: dict,
                        tools: Optional[list[PromptMessageTool]] = None, stop: Optional[list[str]] = None,
                        stream: bool = True, user: Optional[str] = None) -> None:
        """
        调用错误回调函数

        :param llm_instance: LLM实例
        :param ex: 异常对象
        :param model: 模型名称
        :param credentials: 模型认证信息
        :param prompt_messages: 提示信息列表
        :param model_parameters: 模型参数
        :param tools: 工具列表，用于工具调用
        :param stop: 停止词列表
        :param stream: 是否为流式响应
        :param user: 唯一用户ID
        """
        # 打印错误提示文本
        self.print_text("\n[on_llm_invoke_error]\n", color='red')
        # 记录异常日志
        logger.exception(ex)
