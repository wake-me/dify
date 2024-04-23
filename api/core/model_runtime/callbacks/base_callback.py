from abc import ABC
from typing import Optional

from core.model_runtime.entities.llm_entities import LLMResult, LLMResultChunk
from core.model_runtime.entities.message_entities import PromptMessage, PromptMessageTool
from core.model_runtime.model_providers.__base.ai_model import AIModel

_TEXT_COLOR_MAPPING = {
    "blue": "36;1",
    "yellow": "33;1",
    "pink": "38;5;200",
    "green": "32;1",
    "red": "31;1",
}


class Callback(ABC):
    """
    回调基类。
    仅用于LLM（大型语言模型）。
    """
    raise_error: bool = False  # 是否在执行过程中引发错误

    def on_before_invoke(self, llm_instance: AIModel, model: str, credentials: dict,
                         prompt_messages: list[PromptMessage], model_parameters: dict,
                         tools: Optional[list[PromptMessageTool]] = None, stop: Optional[list[str]] = None,
                         stream: bool = True, user: Optional[str] = None) -> None:
        """
        在调用之前执行的回调。

        :param llm_instance: LLM实例
        :param model: 模型名称
        :param credentials: 模型凭证
        :param prompt_messages: 提示信息
        :param model_parameters: 模型参数
        :param tools: 用于工具调用的工具列表
        :param stop: 停止词列表
        :param stream: 是否流式响应
        :param user: 唯一用户ID
        """
        raise NotImplementedError()

    def on_new_chunk(self, llm_instance: AIModel, chunk: LLMResultChunk, model: str, credentials: dict,
                     prompt_messages: list[PromptMessage], model_parameters: dict,
                     tools: Optional[list[PromptMessageTool]] = None, stop: Optional[list[str]] = None,
                     stream: bool = True, user: Optional[str] = None):
        """
        当接收到新数据块时执行的回调。

        :param llm_instance: LLM实例
        :param chunk: 数据块
        :param model: 模型名称
        :param credentials: 模型凭证
        :param prompt_messages: 提示信息
        :param model_parameters: 模型参数
        :param tools: 用于工具调用的工具列表
        :param stop: 停止词列表
        :param stream: 是否流式响应
        :param user: 唯一用户ID
        """
        raise NotImplementedError()

    def on_after_invoke(self, llm_instance: AIModel, result: LLMResult, model: str, credentials: dict,
                        prompt_messages: list[PromptMessage], model_parameters: dict,
                        tools: Optional[list[PromptMessageTool]] = None, stop: Optional[list[str]] = None,
                        stream: bool = True, user: Optional[str] = None) -> None:
        """
        调用后回调方法。

        此方法为调用AI模型之后的回调函数，用于处理调用结果或进行后续操作。需要在子类中实现具体逻辑。

        :param llm_instance: LLM 实例，即调用的AI模型实例。
        :param result: 调用结果，包含模型返回的数据或信息。
        :param model: 模型名称，标识调用的是哪个AI模型。
        :param credentials: 模型凭证，用于认证和访问模型。
        :param prompt_messages: 提示信息列表，可能包含与用户交互所需的提示信息。
        :param model_parameters: 模型参数，用于配置或调整模型的行为。
        :param tools: 工具列表，可用于调用外部工具或服务以辅助处理。
        :param stop: 停止词列表，用于识别并处理那些应该中断处理的词语。
        :param stream: 是否流式响应，标识结果是否应以流的形式返回。
        :param user: 唯一用户ID，标识操作的用户。
        :return: 无返回值。
        """
        raise NotImplementedError()

    def on_invoke_error(self, llm_instance: AIModel, ex: Exception, model: str, credentials: dict,
                        prompt_messages: list[PromptMessage], model_parameters: dict,
                        tools: Optional[list[PromptMessageTool]] = None, stop: Optional[list[str]] = None,
                        stream: bool = True, user: Optional[str] = None) -> None:
        """
        调用错误回调

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
        :return: 无返回值
        """
        raise NotImplementedError()

    def print_text(
            self, text: str, color: Optional[str] = None, end: str = ""
    ) -> None:
        """
        打印带高亮的文本，可以指定文本颜色，且可以自定义结束字符。
        
        参数:
        text: str - 需要打印的文本。
        color: Optional[str] - 文本颜色，如果提供，则会用指定颜色高亮文本，默认为None，表示不使用颜色。
        end: str - 打印文本后的结束字符，默认为空字符串，可以用以替代默认的换行符。
        
        返回值:
        None
        """
        # 根据提供的颜色获取带颜色的文本，若无颜色，则文本不变
        text_to_print = self._get_colored_text(text, color) if color else text
        print(text_to_print, end=end)

    def _get_colored_text(self, text: str, color: str) -> str:
        """
        获取指定颜色的文本。
        
        参数:
        text: str - 需要着色的文本。
        color: str - 文本的颜色代码。
        
        返回值:
        str - 带有指定颜色的文本字符串。
        """
        # 根据颜色代码从映射中获取具体的ANSI颜色码
        color_str = _TEXT_COLOR_MAPPING[color]
        # 使用ANSI转义序列构造带颜色的文本字符串
        return f"\u001b[{color_str}m\033[1;3m{text}\u001b[0m"