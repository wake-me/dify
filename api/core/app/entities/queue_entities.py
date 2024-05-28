from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, validator

from core.model_runtime.entities.llm_entities import LLMResult, LLMResultChunk
from core.workflow.entities.base_node_data_entities import BaseNodeData
from core.workflow.entities.node_entities import NodeType


class QueueEvent(Enum):
    """
    队列事件枚举类，用于定义不同类型的队列事件。

    属性:
    - LLM_CHUNK: 指示低层次语言模型的数据块事件。
    - TEXT_CHUNK: 指示文本数据块事件。
    - AGENT_MESSAGE: 指示代理消息事件，用于在系统内部传递消息。
    - MESSAGE_REPLACE: 指示消息替换事件，用于替换现有消息。
    - MESSAGE_END: 指示消息结束事件。
    - ADVANCED_CHAT_MESSAGE_END: 指示高级聊天消息结束事件。
    - WORKFLOW_STARTED: 指示工作流开始事件。
    - WORKFLOW_SUCCEEDED: 指示工作流成功完成事件。
    - WORKFLOW_FAILED: 指示工作流失败事件。
    - NODE_STARTED: 指示节点开始事件。
    - NODE_SUCCEEDED: 指示节点成功事件。
    - NODE_FAILED: 指示节点失败事件。
    - RETRIEVER_RESOURCES: 指示检索器资源事件。
    - ANNOTATION_REPLY: 指示注释回复事件。
    - AGENT_THOUGHT: 指示代理思考事件，用于表示代理的内部思考过程。
    - MESSAGE_FILE: 指示消息文件事件，用于处理消息中的文件。
    - ERROR: 指示错误事件。
    - PING: 指示心跳事件，用于检查系统或组件的活性。
    - STOP: 指示停止事件，用于请求停止当前正在进行的操作。
    """
    LLM_CHUNK = "llm_chunk"
    TEXT_CHUNK = "text_chunk"
    AGENT_MESSAGE = "agent_message"
    MESSAGE_REPLACE = "message_replace"
    MESSAGE_END = "message_end"
    ADVANCED_CHAT_MESSAGE_END = "advanced_chat_message_end"
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_SUCCEEDED = "workflow_succeeded"
    WORKFLOW_FAILED = "workflow_failed"
    ITERATION_START = "iteration_start"
    ITERATION_NEXT = "iteration_next"
    ITERATION_COMPLETED = "iteration_completed"
    NODE_STARTED = "node_started"
    NODE_SUCCEEDED = "node_succeeded"
    NODE_FAILED = "node_failed"
    RETRIEVER_RESOURCES = "retriever_resources"
    ANNOTATION_REPLY = "annotation_reply"
    AGENT_THOUGHT = "agent_thought"
    MESSAGE_FILE = "message_file"
    ERROR = "error"
    PING = "ping"
    STOP = "stop"

class AppQueueEvent(BaseModel):
    """
    队列事件实体基类
    """
    event: QueueEvent  # 指定具体的队列事件类型

class QueueLLMChunkEvent(AppQueueEvent):
    """
    LLM数据块队列事件实体类
    """
    event = QueueEvent.LLM_CHUNK
    chunk: LLMResultChunk

class QueueIterationStartEvent(AppQueueEvent):
    """
    QueueIterationStartEvent entity
    """
    event = QueueEvent.ITERATION_START
    node_id: str
    node_type: NodeType
    node_data: BaseNodeData

    node_run_index: int
    inputs: dict = None
    predecessor_node_id: Optional[str] = None
    metadata: Optional[dict] = None

class QueueIterationNextEvent(AppQueueEvent):
    """
    QueueIterationNextEvent entity
    """
    event = QueueEvent.ITERATION_NEXT

    index: int
    node_id: str
    node_type: NodeType

    node_run_index: int
    output: Optional[Any] # output for the current iteration

    @validator('output', pre=True, always=True)
    def set_output(cls, v):
        """
        Set output
        """
        if v is None:
            return None
        if isinstance(v, int | float | str | bool | dict | list):
            return v
        raise ValueError('output must be a valid type')

class QueueIterationCompletedEvent(AppQueueEvent):
    """
    QueueIterationCompletedEvent entity
    """
    event = QueueEvent.ITERATION_COMPLETED

    node_id: str
    node_type: NodeType
    
    node_run_index: int
    outputs: dict

class QueueTextChunkEvent(AppQueueEvent):
    """
    文本数据块队列事件实体类
    """
    event = QueueEvent.TEXT_CHUNK  # 定义事件类型为文本数据块
    text: str  # 包含的文本数据
    metadata: Optional[dict] = None  # 可选的元数据信息

class QueueAgentMessageEvent(AppQueueEvent):
    """
    代理消息队列事件实体类
    """
    event = QueueEvent.AGENT_MESSAGE  # 定义事件类型为代理消息
    chunk: LLMResultChunk  # 包含的LLM结果数据块

    
class QueueMessageReplaceEvent(AppQueueEvent):
    """
    QueueMessageReplaceEvent 实体类
    用于表示队列中消息替换事件

    属性:
    text: str - 要替换的消息文本
    """

    event = QueueEvent.MESSAGE_REPLACE
    text: str


class QueueRetrieverResourcesEvent(AppQueueEvent):
    """
    QueueRetrieverResourcesEvent 实体类
    用于表示队列检索资源事件

    属性:
    retriever_resources: list[dict] - 检索到的资源列表，每个资源为一个字典
    """

    event = QueueEvent.RETRIEVER_RESOURCES
    retriever_resources: list[dict]


class QueueAnnotationReplyEvent(AppQueueEvent):
    """
    QueueAnnotationReplyEvent 实体类
    用于表示队列注解回复事件

    属性:
    message_annotation_id: str - 消息注解的ID
    """

    event = QueueEvent.ANNOTATION_REPLY
    message_annotation_id: str


class QueueMessageEndEvent(AppQueueEvent):
    """
    QueueMessageEndEvent 实体类
    用于表示队列消息结束事件

    属性:
    llm_result: Optional[LLMResult] - LLM（Large Language Model）处理结果，可能为空
    """

    event = QueueEvent.MESSAGE_END
    llm_result: Optional[LLMResult] = None


class QueueAdvancedChatMessageEndEvent(AppQueueEvent):
    """
    QueueAdvancedChatMessageEndEvent实体类

    该类继承自AppQueueEvent，代表高级聊天消息结束事件。
    属性:
        event (QueueEvent): 事件类型，此处为QueueEvent.ADVANCED_CHAT_MESSAGE_END。
    """
    event = QueueEvent.ADVANCED_CHAT_MESSAGE_END

class QueueWorkflowStartedEvent(AppQueueEvent):
    """
    QueueWorkflowStartedEvent 实体类
    代表队列工作流开始事件
    """
    event = QueueEvent.WORKFLOW_STARTED  # 指定事件类型为工作流开始

class QueueWorkflowSucceededEvent(AppQueueEvent):
    """
    QueueWorkflowSucceededEvent 实体类
    代表队列工作流成功完成事件
    """
    event = QueueEvent.WORKFLOW_SUCCEEDED  # 指定事件类型为工作流成功

class QueueWorkflowFailedEvent(AppQueueEvent):
    """
    QueueWorkflowFailedEvent 实体类
    代表队列工作流失败事件
    """
    event = QueueEvent.WORKFLOW_FAILED  # 指定事件类型为工作流失败
    error: str  # 错误信息，记录工作流失败的具体原因


class QueueNodeStartedEvent(AppQueueEvent):
    """
    QueueNodeStartedEvent 实体类，表示队列节点开始事件。

    属性:
    - event: 表示事件类型的枚举值，这里为 NODE_STARTED。
    - node_id: 节点的唯一标识符。
    - node_type: 节点的类型，继承自 NodeType。
    - node_data: 节点的数据，继承自 BaseNodeData。
    - node_run_index: 节点运行的索引，默认为 1，表示第一次运行。
    - predecessor_node_id: 前驱节点的ID，可选，默认为 None。
    """
    event = QueueEvent.NODE_STARTED  # 指定事件类型为节点开始事件

    node_id: str
    node_type: NodeType
    node_data: BaseNodeData
    node_run_index: int = 1
    predecessor_node_id: Optional[str] = None


class QueueNodeSucceededEvent(AppQueueEvent):
    """
    QueueNodeSucceededEvent实体类，用于表示队列节点成功事件。
    
    属性:
    - event: 事件类型，固定为NODE_SUCCEEDED。
    - node_id: 节点ID，标识哪个节点成功了。
    - node_type: 节点类型，表明节点的类别（如任务节点、数据节点等）。
    - node_data: 节点数据，包含节点的详细信息。
    - inputs: 输入数据字典，记录了节点执行时的输入参数（可选）。
    - process_data: 过程数据字典，记录了节点执行过程中的中间数据（可选）。
    - outputs: 输出数据字典，记录了节点执行后的输出结果（可选）。
    - execution_metadata: 执行元数据字典，记录了节点执行的相关元数据，如执行时间、执行者等（可选）。
    - error: 错误信息，如果在节点执行过程中发生错误，则会记录错误信息（可选）。
    """
    event = QueueEvent.NODE_SUCCEEDED  # 事件类型，表示节点成功

    node_id: str
    node_type: NodeType
    node_data: BaseNodeData

    inputs: Optional[dict] = None
    process_data: Optional[dict] = None
    outputs: Optional[dict] = None
    execution_metadata: Optional[dict] = None

    error: Optional[str] = None


class QueueNodeFailedEvent(AppQueueEvent):
    """
    QueueNodeFailedEvent 实体类，表示队列中节点失败的事件。

    属性:
    - event: 事件类型，固定为 NODE_FAILED。
    - node_id: 节点的唯一标识ID。
    - node_type: 节点的类型，继承自 NodeType。
    - node_data: 节点的数据，继承自 BaseNodeData。
    - inputs: 节点的输入参数，为字典类型，可为空。
    - outputs: 节点的输出结果，为字典类型，可为空。
    - process_data: 节点处理过程中的数据，为字典类型，可为空。
    - error: 错误信息，描述节点失败的原因。
    """
    event = QueueEvent.NODE_FAILED  # 事件类型：节点失败

    node_id: str
    node_type: NodeType
    node_data: BaseNodeData

    inputs: Optional[dict] = None  # 节点输入参数
    outputs: Optional[dict] = None  # 节点输出结果
    process_data: Optional[dict] = None  # 节点处理数据

    error: str  # 错误信息


class QueueAgentThoughtEvent(AppQueueEvent):
    """
    QueueAgentThoughtEvent 实体类
    用于表示队列中的代理思考事件

    属性:
    event (QueueEvent): 事件类型，此处为 AGENT_THOUGHT
    agent_thought_id (str): 代理思考事件的唯一标识符
    """
    event = QueueEvent.AGENT_THOUGHT
    agent_thought_id: str


class QueueMessageFileEvent(AppQueueEvent):
    """
    QueueMessageFileEvent 实体类
    用于表示队列中的消息文件事件

    属性:
    event (QueueEvent): 事件类型，此处为 MESSAGE_FILE
    message_file_id (str): 消息文件的唯一标识符
    """
    event = QueueEvent.MESSAGE_FILE
    message_file_id: str


class QueueErrorEvent(AppQueueEvent):
    """
    QueueErrorEvent 实体类
    用于表示队列中的错误事件

    属性:
    event (QueueEvent): 事件类型，此处为 ERROR
    error (Any): 错误信息或异常对象
    """
    event = QueueEvent.ERROR
    error: Any


class QueuePingEvent(AppQueueEvent):
    """
    QueuePingEvent 实体类，用于表示队列中的 Ping 事件。
    """
    event = QueueEvent.PING  # 事件类型为 Ping

class QueueStopEvent(AppQueueEvent):
    """
    QueueStopEvent 实体类，用于表示队列中的停止事件。
    """
    class StopBy(Enum):
        """
        停止原因枚举类。
        """
        USER_MANUAL = "user-manual"  # 用户手动停止
        ANNOTATION_REPLY = "annotation-reply"  # 注释回复停止
        OUTPUT_MODERATION = "output-moderation"  # 输出审核停止
        INPUT_MODERATION = "input-moderation"  # 输入审核停止

    event = QueueEvent.STOP  # 事件类型为停止
    stopped_by: StopBy  # 停止原因枚举

class QueueMessage(BaseModel):
    """
    QueueMessage 实体类，代表队列消息的基类。
    """
    task_id: str  # 任务ID
    app_mode: str  # 应用模式
    event: AppQueueEvent  # 事件类型

class MessageQueueMessage(QueueMessage):
    """
    MessageQueueMessage 实体类，用于表示消息队列中的消息。
    """
    message_id: str  # 消息ID
    conversation_id: str  # 对话ID

class WorkflowQueueMessage(QueueMessage):
    """
    WorkflowQueueMessage 实体类，用于表示工作流队列中的消息。
    """
    pass  # 该类作为工作流消息的基类，可能在子类中具体实现属性。