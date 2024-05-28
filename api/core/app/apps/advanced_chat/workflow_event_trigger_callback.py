from typing import Any, Optional

from core.app.apps.base_app_queue_manager import AppQueueManager, PublishFrom
from core.app.entities.queue_entities import (
    AppQueueEvent,
    QueueIterationCompletedEvent,
    QueueIterationNextEvent,
    QueueIterationStartEvent,
    QueueNodeFailedEvent,
    QueueNodeStartedEvent,
    QueueNodeSucceededEvent,
    QueueTextChunkEvent,
    QueueWorkflowFailedEvent,
    QueueWorkflowStartedEvent,
    QueueWorkflowSucceededEvent,
)
from core.workflow.callbacks.base_workflow_callback import BaseWorkflowCallback
from core.workflow.entities.base_node_data_entities import BaseNodeData
from core.workflow.entities.node_entities import NodeType
from models.workflow import Workflow


class WorkflowEventTriggerCallback(BaseWorkflowCallback):
    """
    工作流事件触发回调类，用于在工作流的不同阶段触发相应的事件。

    Attributes:
        queue_manager (AppQueueManager): 队列管理器，用于发布事件。
        workflow (Workflow): 当前工作流实例。
    """

    def __init__(self, queue_manager: AppQueueManager, workflow: Workflow):
        """
        初始化方法。

        Parameters:
            queue_manager (AppQueueManager): 队列管理器，用于发布事件。
            workflow (Workflow): 当前工作流实例。
        """
        self._queue_manager = queue_manager

    def on_workflow_run_started(self) -> None:
        """
        工作流运行开始时触发的事件。
        """
        self._queue_manager.publish(
            QueueWorkflowStartedEvent(),
            PublishFrom.APPLICATION_MANAGER
        )

    def on_workflow_run_succeeded(self) -> None:
        """
        工作流运行成功完成时触发的事件。
        """
        self._queue_manager.publish(
            QueueWorkflowSucceededEvent(),
            PublishFrom.APPLICATION_MANAGER
        )

    def on_workflow_run_failed(self, error: str) -> None:
        """
        工作流运行失败时触发的事件。

        Parameters:
            error (str): 错误信息。
        """
        self._queue_manager.publish(
            QueueWorkflowFailedEvent(
                error=error
            ),
            PublishFrom.APPLICATION_MANAGER
        )

    def on_workflow_node_execute_started(self, node_id: str,
                                         node_type: NodeType,
                                         node_data: BaseNodeData,
                                         node_run_index: int = 1,
                                         predecessor_node_id: Optional[str] = None) -> None:
        """
        工作流节点执行开始时触发的事件。

        Parameters:
            node_id (str): 节点ID。
            node_type (NodeType): 节点类型。
            node_data (BaseNodeData): 节点数据。
            node_run_index (int): 节点运行索引，默认为1。
            predecessor_node_id (Optional[str]): 前驱节点ID，可为None。
        """
        self._queue_manager.publish(
            QueueNodeStartedEvent(
                node_id=node_id,
                node_type=node_type,
                node_data=node_data,
                node_run_index=node_run_index,
                predecessor_node_id=predecessor_node_id
            ),
            PublishFrom.APPLICATION_MANAGER
        )

    def on_workflow_node_execute_succeeded(self, node_id: str,
                                           node_type: NodeType,
                                           node_data: BaseNodeData,
                                           inputs: Optional[dict] = None,
                                           process_data: Optional[dict] = None,
                                           outputs: Optional[dict] = None,
                                           execution_metadata: Optional[dict] = None) -> None:
        """
        工作流节点执行成功完成时触发的事件。

        Parameters:
            node_id (str): 节点ID。
            node_type (NodeType): 节点类型。
            node_data (BaseNodeData): 节点数据。
            inputs (Optional[dict]): 输入数据，可为None。
            process_data (Optional[dict]): 处理数据，可为None。
            outputs (Optional[dict]): 输出数据，可为None。
            execution_metadata (Optional[dict]): 执行元数据，可为None。
        """
        self._queue_manager.publish(
            QueueNodeSucceededEvent(
                node_id=node_id,
                node_type=node_type,
                node_data=node_data,
                inputs=inputs,
                process_data=process_data,
                outputs=outputs,
                execution_metadata=execution_metadata
            ),
            PublishFrom.APPLICATION_MANAGER
        )

    def on_workflow_node_execute_failed(self, node_id: str,
                                        node_type: NodeType,
                                        node_data: BaseNodeData,
                                        error: str,
                                        inputs: Optional[dict] = None,
                                        outputs: Optional[dict] = None,
                                        process_data: Optional[dict] = None) -> None:
        """
        工作流节点执行失败时触发的事件。

        Parameters:
            node_id (str): 节点ID。
            node_type (NodeType): 节点类型。
            node_data (BaseNodeData): 节点数据。
            error (str): 错误信息。
            inputs (Optional[dict]): 输入数据，可为None。
            outputs (Optional[dict]): 输出数据，可为None。
            process_data (Optional[dict]): 处理数据，可为None。
        """
        self._queue_manager.publish(
            QueueNodeFailedEvent(
                node_id=node_id,
                node_type=node_type,
                node_data=node_data,
                inputs=inputs,
                outputs=outputs,
                process_data=process_data,
                error=error
            ),
            PublishFrom.APPLICATION_MANAGER
        )

    def on_node_text_chunk(self, node_id: str, text: str, metadata: Optional[dict] = None) -> None:
        """
        发布文本块事件。

        Parameters:
            node_id (str): 节点ID。
            text (str): 文本内容。
            metadata (Optional[dict]): 元数据，可为None。
        """
        self._queue_manager.publish(
            QueueTextChunkEvent(
                text=text,
                metadata={
                    "node_id": node_id,
                    **metadata
                }
            ), PublishFrom.APPLICATION_MANAGER
        )

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
        self._queue_manager.publish(
            QueueIterationStartEvent(
                node_id=node_id,
                node_type=node_type,
                node_run_index=node_run_index,
                node_data=node_data,
                inputs=inputs,
                predecessor_node_id=predecessor_node_id,
                metadata=metadata
            ),
            PublishFrom.APPLICATION_MANAGER
        )

    def on_workflow_iteration_next(self, node_id: str, 
                                   node_type: NodeType,
                                   index: int, 
                                   node_run_index: int,
                                   output: Optional[Any]) -> None:
        """
        Publish iteration next
        """
        self._queue_manager._publish(
            QueueIterationNextEvent(
                node_id=node_id,
                node_type=node_type,
                index=index,
                node_run_index=node_run_index,
                output=output
            ),
            PublishFrom.APPLICATION_MANAGER
        )

    def on_workflow_iteration_completed(self, node_id: str, 
                                        node_type: NodeType,
                                        node_run_index: int,
                                        outputs: dict) -> None:
        """
        Publish iteration completed
        """
        self._queue_manager._publish(
            QueueIterationCompletedEvent(
                node_id=node_id,
                node_type=node_type,
                node_run_index=node_run_index,
                outputs=outputs
            ),
            PublishFrom.APPLICATION_MANAGER
        )

    def on_event(self, event: AppQueueEvent) -> None:
        """
        发布自定义事件。

        Parameters:
            event (AppQueueEvent): 待发布的事件对象。
        """
        self._queue_manager.publish(
            event,
            PublishFrom.APPLICATION_MANAGER
        )