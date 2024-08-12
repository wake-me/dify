from typing import Optional

from core.app.entities.queue_entities import AppQueueEvent
from core.model_runtime.utils.encoders import jsonable_encoder
from core.workflow.callbacks.base_workflow_callback import WorkflowCallback
from core.workflow.entities.base_node_data_entities import BaseNodeData
from core.workflow.entities.node_entities import NodeType

# 颜色文本映射
# 该字典映射了不同颜色名称到其对应的ANSI转义序列，用于在终端中显示带颜色的文本。
# 键是颜色的名称，值是表示该颜色的ANSI转义序列。转义序列由颜色代码和高亮标志组成。
_TEXT_COLOR_MAPPING = {
    "blue": "36;1",      # 蓝色，高亮
    "yellow": "33;1",    # 黄色，高亮
    "pink": "38;5;200",  # 粉色，高亮
    "green": "32;1",     # 绿色，高亮
    "red": "31;1",       # 红色，高亮
}

class WorkflowLoggingCallback(WorkflowCallback):

    def __init__(self) -> None:
        """
        初始化WorkflowLoggingCallback实例。
        """
        self.current_node_id = None  # 当前执行节点的ID

    def on_workflow_run_started(self) -> None:
        """
        工作流执行开始时的回调函数。
        """
        self.print_text("\n[on_workflow_run_started]", color='pink')

    def on_workflow_run_succeeded(self) -> None:
        """
        工作流执行成功时的回调函数。
        """
        self.print_text("\n[on_workflow_run_succeeded]", color='green')

    def on_workflow_run_failed(self, error: str) -> None:
        """
        工作流执行失败时的回调函数。

        参数:
        - error: 错误信息字符串。
        """
        self.print_text("\n[on_workflow_run_failed]", color='red')

    def on_workflow_node_execute_started(self, node_id: str,
                                         node_type: NodeType,
                                         node_data: BaseNodeData,
                                         node_run_index: int = 1,
                                         predecessor_node_id: Optional[str] = None) -> None:
        """
        工作流节点执行开始时的回调函数。

        参数:
        - node_id: 节点ID字符串。
        - node_type: 节点类型枚举。
        - node_data: 节点数据实例。
        - node_run_index: 节点执行索引，默认值为1。
        - predecessor_node_id: 前驱节点ID，可为None。
        """
        self.print_text("\n[on_workflow_node_execute_started]", color='yellow')
        self.print_node_details(node_id, node_type, node_run_index, predecessor_node_id)

    def on_workflow_node_execute_succeeded(self, node_id: str,
                                           node_type: NodeType,
                                           node_data: BaseNodeData,
                                           inputs: Optional[dict] = None,
                                           process_data: Optional[dict] = None,
                                           outputs: Optional[dict] = None,
                                           execution_metadata: Optional[dict] = None) -> None:
        """
        工作流节点执行成功时的回调函数。

        参数:
        - node_id: 节点ID字符串。
        - node_type: 节点类型枚举。
        - node_data: 节点数据实例。
        - inputs: 输入数据字典，可为None。
        - process_data: 处理数据字典，可为None。
        - outputs: 输出数据字典，可为None。
        - execution_metadata: 执行元数据字典，可为None。
        """
        self.print_text("\n[on_workflow_node_execute_succeeded]", color='green')
        self.print_node_details(node_id, node_type)
        self.print_additional_details(inputs, process_data, outputs, execution_metadata)

    def on_workflow_node_execute_failed(self, node_id: str,
                                        node_type: NodeType,
                                        node_data: BaseNodeData,
                                        error: str,
                                        inputs: Optional[dict] = None,
                                        outputs: Optional[dict] = None,
                                        process_data: Optional[dict] = None) -> None:
        """
        工作流节点执行失败时的回调函数。

        参数:
        - node_id: 节点ID字符串。
        - node_type: 节点类型枚举。
        - node_data: 节点数据实例。
        - error: 错误信息字符串。
        - inputs: 输入数据字典，可为None。
        - outputs: 输出数据字典，可为None。
        - process_data: 处理数据字典，可为None。
        """
        self.print_text("\n[on_workflow_node_execute_failed]", color='red')
        self.print_node_details(node_id, node_type)
        self.print_additional_details(inputs, process_data, outputs, error)

    def on_node_text_chunk(self, node_id: str, text: str, metadata: Optional[dict] = None) -> None:
        """
        发布文本块的回调函数。

        参数:
        - node_id: 节点ID字符串。
        - text: 要发布的文本字符串。
        - metadata: 元数据字典，可为None。
        """
        if not self.current_node_id or self.current_node_id != node_id:
            self.current_node_id = node_id
            self.print_text('\n[on_node_text_chunk]')
            self.print_node_metadata(node_id, metadata)

        self.print_text(text, color="pink", end="")

    def on_workflow_iteration_started(self, 
                                      node_id: str,
                                      node_type: NodeType,
                                      node_run_index: int = 1,
                                      node_data: Optional[BaseNodeData] = None,
                                      inputs: dict = None,
                                      predecessor_node_id: Optional[str] = None,
                                      metadata: Optional[dict] = None) -> None:
        """
        Publish iteration started
        """
        self.print_text("\n[on_workflow_iteration_started]", color='blue')
        self.print_text(f"Node ID: {node_id}", color='blue')

    def on_workflow_iteration_next(self, node_id: str, 
                                   node_type: NodeType,
                                   index: int, 
                                   node_run_index: int,
                                   output: Optional[dict]) -> None:
        """
        Publish iteration next
        """
        self.print_text("\n[on_workflow_iteration_next]", color='blue')

    def on_workflow_iteration_completed(self, node_id: str, 
                                        node_type: NodeType,
                                        node_run_index: int,
                                        outputs: dict) -> None:
        """
        Publish iteration completed
        """
        self.print_text("\n[on_workflow_iteration_completed]", color='blue')

    def on_event(self, event: AppQueueEvent) -> None:
        """
        发布事件的回调函数。

        参数:
        - event: 应用队列事件实例。
        """
        self.print_text("\n[on_workflow_event]", color='blue')
        self.print_text(f"Event: {jsonable_encoder(event)}", color='blue')

    def print_text(
            self, text: str, color: Optional[str] = None, end: str = "\n"
    ) -> None:
        """
        打印带高亮和无结束字符的文本。

        参数:
        - text: 要打印的文本字符串。
        - color: 文本颜色，可为None。
        - end: 文本结束字符，默认为换行符。
        """
        text_to_print = self._get_colored_text(text, color) if color else text
        print(f'{text_to_print}', end=end)

    def _get_colored_text(self, text: str, color: str) -> str:
        """
        获取带颜色的文本。

        参数:
        - text: 要着色的文本字符串。
        - color: 文本颜色。

        返回:
        - 带有颜色代码的文本字符串。
        """
        color_str = _TEXT_COLOR_MAPPING[color]
        return f"\u001b[{color_str}m\033[1;3m{text}\u001b[0m"
