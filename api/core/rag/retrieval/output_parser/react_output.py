from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple, Union


@dataclass
class ReactAction:
    """
    描述一个ReactAction执行的动作的完整信息。

    属性:
        tool (str): 执行的工具名称。
        tool_input (Union[str, dict]): 传递给工具的输入。
        log (str): 关于动作的附加日志信息。
    """

    tool: str
    tool_input: Union[str, dict]
    log: str

class ReactFinish(NamedTuple):
    """
    ReactFinish动作最终的返回值。

    属性:
        return_values (dict): 返回值字典。
        log (str): 关于返回值的附加日志信息。
    """

    return_values: dict
    log: str