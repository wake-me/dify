import os
from collections.abc import Mapping, Sequence
from typing import Any, Optional, TextIO, Union

from pydantic import BaseModel

from core.ops.entities.trace_entity import TraceTaskName
from core.ops.ops_trace_manager import TraceQueueManager, TraceTask
from core.tools.entities.tool_entities import ToolInvokeMessage

_TEXT_COLOR_MAPPING = {
    "blue": "36;1",
    "yellow": "33;1",
    "pink": "38;5;200",
    "green": "32;1",
    "red": "31;1",
}

def get_colored_text(text: str, color: str) -> str:
    """
    获取带颜色的文本字符串。

    参数:
    text: str - 需要着色的文本。
    color: str - 文本的颜色。

    返回:
    str - 带有指定颜色的文本字符串。
    """
    color_str = _TEXT_COLOR_MAPPING[color]
    return f"\u001b[{color_str}m\033[1;3m{text}\u001b[0m"

def print_text(
    text: str, color: Optional[str] = None, end: str = "", file: Optional[TextIO] = None
) -> None:
    """
    打印文本，可以选择颜色和是否在末尾添加特殊字符。

    参数:
    text: str - 需要打印的文本。
    color: Optional[str] = None - 文本的颜色。如果为None，则不使用颜色。
    end: str = "" - 打印文本后的结束字符，默认为空字符串。
    file: Optional[TextIO] = None - 打印的目标文件对象，如果为None，则打印到标准输出。
    
    返回:
    无
    """
    text_to_print = get_colored_text(text, color) if color else text
    print(text_to_print, end=end, file=file)
    if file:
        file.flush()  # 确保所有打印内容都写入文件

class DifyAgentCallbackHandler(BaseModel):
    """
    一个回调处理器类，用于向标准输出打印信息。

    属性:
    color: Optional[str] = '' - 打印文本的颜色，默认为空。
    current_loop: int - 当前循环次数。
    """
    color: Optional[str] = ''
    current_loop: int = 1

    def __init__(self, color: Optional[str] = None) -> None:
        """
        初始化回调处理器。

        参数:
        color: Optional[str] = None - 打印文本的颜色。如果为None，则使用默认颜色。
        """
        super().__init__()
        self.color = color or 'green'  # 如果未指定颜色，则使用默认颜色
        self.current_loop = 1

    def on_tool_start(
        self,
        tool_name: str,
        tool_inputs: Mapping[str, Any],
    ) -> None:
        """
        工具开始执行时的回调函数。

        参数:
        tool_name: str - 工具的名称。
        tool_inputs: dict[str, Any] - 工具的输入参数。
        """
        print_text("\n[on_tool_start] ToolCall:" + tool_name + "\n" + str(tool_inputs) + "\n", color=self.color)

    def on_tool_end(
        self,
        tool_name: str,
        tool_inputs: Mapping[str, Any],
        tool_outputs: Sequence[ToolInvokeMessage],
        message_id: Optional[str] = None,
        timer: Optional[Any] = None,
        trace_manager: Optional[TraceQueueManager] = None
    ) -> None:
        """
        工具结束执行时的回调函数。

        参数:
        tool_name: str - 工具的名称。
        tool_inputs: dict[str, Any] - 工具的输入参数。
        tool_outputs: str - 工具的输出结果。
        """
        print_text("\n[on_tool_end]\n", color=self.color)
        print_text("Tool: " + tool_name + "\n", color=self.color)
        print_text("Inputs: " + str(tool_inputs) + "\n", color=self.color)
        print_text("Outputs: " + str(tool_outputs)[:1000] + "\n", color=self.color)
        print_text("\n")

        if trace_manager:
            trace_manager.add_trace_task(
                TraceTask(
                    TraceTaskName.TOOL_TRACE,
                    message_id=message_id,
                    tool_name=tool_name,
                    tool_inputs=tool_inputs,
                    tool_outputs=tool_outputs,
                    timer=timer,
                )
            )

    def on_tool_error(
        self, error: Union[Exception, KeyboardInterrupt], **kwargs: Any
    ) -> None:
        """
        工具执行出错时的回调函数。

        参数:
        error: Union[Exception, KeyboardInterrupt] - 异常对象。
        **kwargs: Any - 其他传递给回调的参数。
        """
        print_text("\n[on_tool_error] Error: " + str(error) + "\n", color='red')

    def on_agent_start(
        self, thought: str
    ) -> None:
        """
        代理开始执行时的回调函数。

        参数:
        thought: str - 代理开始时的思考内容。
        """
        if thought:
            print_text("\n[on_agent_start] \nCurrent Loop: " + \
                        str(self.current_loop) + \
                        "\nThought: " + thought + "\n", color=self.color)
        else:
            print_text("\n[on_agent_start] \nCurrent Loop: " + str(self.current_loop) + "\n", color=self.color)

    def on_agent_finish(
        self, color: Optional[str] = None, **kwargs: Any
    ) -> None:
        """
        代理结束执行时的回调函数。

        参数:
        color: Optional[str] = None - 打印文本的颜色。如果为None，则使用默认颜色。
        **kwargs: Any - 其他传递给回调的参数。
        """
        print_text("\n[on_agent_finish]\n Loop: " + str(self.current_loop) + "\n", color=self.color)

        self.current_loop += 1

    @property
    def ignore_agent(self) -> bool:
        """
        是否忽略代理回调。

        返回:
        bool - 如果环境变量DEBUG未设置或不为'true'，则返回True。
        """
        return not os.environ.get("DEBUG") or os.environ.get("DEBUG").lower() != 'true'

    @property
    def ignore_chat_model(self) -> bool:
        """
        是否忽略聊天模型回调。

        返回:
        bool - 如果环境变量DEBUG未设置或不为'true'，则返回True。
        """
        return not os.environ.get("DEBUG") or os.environ.get("DEBUG").lower() != 'true'