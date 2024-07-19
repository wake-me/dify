from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from core.model_runtime.entities.llm_entities import LLMResult, LLMUsage
from core.model_runtime.utils.encoders import jsonable_encoder
from core.workflow.entities.base_node_data_entities import BaseNodeData
from core.workflow.entities.node_entities import NodeType
from core.workflow.nodes.answer.entities import GenerateRouteChunk
from models.workflow import WorkflowNodeExecutionStatus


class WorkflowStreamGenerateNodes(BaseModel):
    """
    WorkflowStreamGenerateNodes entity
    """
    end_node_id: str
    stream_node_ids: list[str]


class ChatflowStreamGenerateRoute(BaseModel):
    """
    ChatflowStreamGenerateRoute entity
    """

    answer_node_id: str
    generate_route: list[GenerateRouteChunk]
    current_route_position: int = 0


class NodeExecutionInfo(BaseModel):
    """
    NodeExecutionInfo 实体类

    参数:
    - workflow_node_execution_id: 工作流节点执行ID，类型为str
    - node_type: 节点类型，类型为NodeType
    - start_at: 开始时间，类型为float（Unix时间戳）
    """

    workflow_node_execution_id: str
    node_type: NodeType
    start_at: float

class TaskState(BaseModel):
    """
    任务状态实体类，作为任务状态的基础模型。
    """
    metadata: dict = {}  # 用于存储任务的元数据

class EasyUITaskState(TaskState):
    """
    EasyUI任务状态实体类，继承自TaskState，用于特定的EasyUI任务状态。
    """
    llm_result: LLMResult  # 存储LLM（Large Language Model）任务的结果

class WorkflowTaskState(TaskState):
    """
    工作流任务状态实体类，继承自TaskState，用于管理工作流任务的状态。
    """
    answer: str = ""  # 存储任务的答案
    workflow_run_id: Optional[str] = None  # 工作流运行的ID，可为空
    start_at: Optional[float] = None  # 任务开始时间，以浮点数表示的时间戳，可为空
    total_tokens: int = 0  # 任务处理的总token数
    total_steps: int = 0  # 任务的总步骤数
    
    # 存储运行过的节点执行信息，以节点ID为键，NodeExecutionInfo为值的字典
    ran_node_execution_infos: dict[str, NodeExecutionInfo] = {}
    latest_node_execution_info: Optional[NodeExecutionInfo] = None

    current_stream_generate_state: Optional[WorkflowStreamGenerateNodes] = None

    iteration_nested_node_ids: list[str] = None


class AdvancedChatTaskState(WorkflowTaskState):
    """
    AdvancedChatTaskState 实体类，用于表示高级聊天任务的状态。
    
    属性:
    - usage: LLMUsage 类型，表示任务的使用情况。
    - current_stream_generate_state: Optional[StreamGenerateRoute] 类型，表示当前流生成的状态，可以为 None。
    """
    usage: LLMUsage

    current_stream_generate_state: Optional[ChatflowStreamGenerateRoute] = None


class StreamEvent(Enum):
    """
    流事件枚举类，用于定义不同类型的流事件。

    属性:
    - PING: 心跳事件
    - ERROR: 错误事件
    - MESSAGE: 消息事件
    - MESSAGE_END: 消息结束事件
    - MESSAGE_FILE: 消息文件事件
    - MESSAGE_REPLACE: 消息替换事件
    - AGENT_THOUGHT: 代理思考事件
    - AGENT_MESSAGE: 代理消息事件
    - WORKFLOW_STARTED: 工作流开始事件
    - WORKFLOW_FINISHED: 工作流结束事件
    - NODE_STARTED: 节点开始事件
    - NODE_FINISHED: 节点结束事件
    - TEXT_CHUNK: 文本块事件
    - TEXT_REPLACE: 文本替换事件
    """
    PING = "ping"
    ERROR = "error"
    MESSAGE = "message"
    MESSAGE_END = "message_end"
    TTS_MESSAGE = "tts_message"
    TTS_MESSAGE_END = "tts_message_end"
    MESSAGE_FILE = "message_file"
    MESSAGE_REPLACE = "message_replace"
    AGENT_THOUGHT = "agent_thought"
    AGENT_MESSAGE = "agent_message"
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_FINISHED = "workflow_finished"
    NODE_STARTED = "node_started"
    NODE_FINISHED = "node_finished"
    ITERATION_STARTED = "iteration_started"
    ITERATION_NEXT = "iteration_next"
    ITERATION_COMPLETED = "iteration_completed"
    TEXT_CHUNK = "text_chunk"
    TEXT_REPLACE = "text_replace"

class StreamResponse(BaseModel):
    """
    StreamResponse 实体类
    用于表示流响应的基本结构

    属性:
    - event: StreamEvent 类型，表示事件的类型
    - task_id: 字符串类型，表示任务的唯一标识符

    方法:
    - to_dict: 将 StreamResponse 实例转换为字典格式
    返回值:
        - dict: 表示 StreamResponse 实例的字典表示
    """
    event: StreamEvent
    task_id: str

    def to_dict(self) -> dict:
        # 将当前实例转换为符合 JSON 格式的编码字典
        return jsonable_encoder(self)


class ErrorStreamResponse(StreamResponse):
    """
    ErrorStreamResponse 实体类
    用于表示错误类型的流响应

    属性:
    - event: StreamEvent 类型，固定为 ERROR 事件
    - err: Exception 类型，表示发生的异常错误

    配置:
    - Config: 允许任意类型的属性设置
    """
    event: StreamEvent = StreamEvent.ERROR
    err: Exception
    model_config = ConfigDict(arbitrary_types_allowed=True)


class MessageStreamResponse(StreamResponse):
    """
    MessageStreamResponse 实体类
    用于表示消息类型的流响应

    属性:
    - event: StreamEvent 类型，固定为 MESSAGE 事件
    - id: 字符串类型，表示消息的唯一标识符
    - answer: 字符串类型，表示消息的内容
    """
    event: StreamEvent = StreamEvent.MESSAGE
    id: str
    answer: str


class MessageAudioStreamResponse(StreamResponse):
    """
    MessageStreamResponse entity
    """
    event: StreamEvent = StreamEvent.TTS_MESSAGE
    audio: str


class MessageAudioEndStreamResponse(StreamResponse):
    """
    MessageStreamResponse entity
    """
    event: StreamEvent = StreamEvent.TTS_MESSAGE_END
    audio: str


class MessageEndStreamResponse(StreamResponse):
    """
    MessageEndStreamResponse 实体类
    用于表示消息流结束的响应

    属性:
    event (StreamEvent): 流事件类型，这里固定为 MESSAGE_END
    id (str): 消息的唯一标识符
    metadata (dict): 消息的元数据，默认为空字典
    """
    event: StreamEvent = StreamEvent.MESSAGE_END
    id: str
    metadata: dict = {}


class MessageFileStreamResponse(StreamResponse):
    """
    MessageFileStreamResponse 实体类
    用于表示消息流中的文件响应

    属性:
    event (StreamEvent): 流事件类型，这里固定为 MESSAGE_FILE
    id (str): 文件的唯一标识符
    type (str): 文件的类型
    belongs_to (str): 文件所属的类别或标识
    url (str): 文件的访问URL
    """
    event: StreamEvent = StreamEvent.MESSAGE_FILE
    id: str
    type: str
    belongs_to: str
    url: str


class MessageReplaceStreamResponse(StreamResponse):
    """
    MessageReplaceStreamResponse 实体类
    用于表示消息替换的流响应

    属性:
    - event: StreamEvent 类型，事件类型，此处为MESSAGE_REPLACE
    - answer: str 类型，替换后的消息内容
    """

    event: StreamEvent = StreamEvent.MESSAGE_REPLACE
    answer: str

class AgentThoughtStreamResponse(StreamResponse):
    """
    AgentThoughtStreamResponse 实体类
    用于表示代理思考的流响应

    属性:
    - event: StreamEvent 类型，事件类型，此处为AGENT_THOUGHT
    - id: str 类型，思考的唯一标识符
    - position: int 类型，思考的位置
    - thought: Optional[str] 类型，思考的内容，可为空
    - observation: Optional[str] 类型，观察结果，可为空
    - tool: Optional[str] 类型，使用的工具，可为空
    - tool_labels: Optional[dict] 类型，工具的标签，可为空
    - tool_input: Optional[str] 类型，工具的输入，可为空
    - message_files: Optional[list[str]] 类型，消息文件列表，可为空
    """

    event: StreamEvent = StreamEvent.AGENT_THOUGHT
    id: str
    position: int
    thought: Optional[str] = None
    observation: Optional[str] = None
    tool: Optional[str] = None
    tool_labels: Optional[dict] = None
    tool_input: Optional[str] = None
    message_files: Optional[list[str]] = None

class AgentMessageStreamResponse(StreamResponse):
    """
    AgentMessageStreamResponse 实体类
    用于表示代理消息的流响应

    属性:
    - event: StreamEvent 类型，事件类型，此处为AGENT_MESSAGE
    - id: str 类型，消息的唯一标识符
    - answer: str 类型，消息内容
    """

    event: StreamEvent = StreamEvent.AGENT_MESSAGE
    id: str
    answer: str


class WorkflowStartStreamResponse(StreamResponse):
    """
    WorkflowStartStreamResponse 实体类
    用于表示工作流启动流响应的实体

    属性:
    - event: StreamEvent 类型，表示事件类型，这里固定为工作流启动事件
    - workflow_run_id: 字符串类型，表示工作流运行的唯一标识符
    - data: Data 类型，包含工作流启动的具体数据信息
    """

    class Data(BaseModel):
        """
        Data 实体类
        包含工作流启动时的具体数据信息

        属性:
        - id: 字符串类型，表示事件的唯一标识符
        - workflow_id: 字符串类型，表示工作流的唯一标识符
        - sequence_number: 整型，表示事件的序列号
        - inputs: 字典类型，表示工作流的输入参数
        - created_at: 整型，表示事件创建的时间戳
        """
        id: str
        workflow_id: str
        sequence_number: int
        inputs: dict
        created_at: int

    event: StreamEvent = StreamEvent.WORKFLOW_STARTED  # 表示事件类型为工作流启动
    workflow_run_id: str  # 工作流运行的唯一标识符
    data: Data  # 包含工作流启动的具体数据信息


class WorkflowFinishStreamResponse(StreamResponse):
    """
    WorkflowFinishStreamResponse 实体类，用于表示工作流完成流响应。

    属性:
    - event: StreamEvent，工作流完成事件。
    - workflow_run_id: str，工作流运行的唯一标识符。
    - data: Data，包含工作流完成的详细数据。
    """

    class Data(BaseModel):
        """
        Data 实体类，包含工作流完成的具体信息。

        属性:
        - id: str，工作流实例的唯一标识符。
        - workflow_id: str，所属工作流的唯一标识符。
        - sequence_number: int，事件序列号。
        - status: str，工作流的完成状态。
        - outputs: Optional[dict] = None，工作流的输出结果。
        - error: Optional[str] = None，工作流运行中的错误信息。
        - elapsed_time: float，工作流运行总时间（秒）。
        - total_tokens: int，工作流中处理的令牌总数。
        - total_steps: int，工作流中的总步骤数。
        - created_by: Optional[dict] = None，创建工作流实例的用户信息。
        - created_at: int，工作流实例创建的时间戳。
        - finished_at: int，工作流实例完成的时间戳。
        - files: Optional[list[dict]] = [], 工作流产生的文件列表。
        """
        id: str
        workflow_id: str
        sequence_number: int
        status: str
        outputs: Optional[dict] = None
        error: Optional[str] = None
        elapsed_time: float
        total_tokens: int
        total_steps: int
        created_by: Optional[dict] = None
        created_at: int
        finished_at: int
        files: Optional[list[dict]] = []

    event: StreamEvent = StreamEvent.WORKFLOW_FINISHED
    workflow_run_id: str
    data: Data


class NodeStartStreamResponse(StreamResponse):
    """
    NodeStartStreamResponse 实体类，用于表示节点启动流响应。
    """

    class Data(BaseModel):
        """
        Data 实体类，用于包含节点启动流响应中的数据信息。
        """
        id: str  # 实体ID
        node_id: str  # 节点ID
        node_type: str  # 节点类型
        title: str  # 节点标题
        index: int  # 节点索引位置
        predecessor_node_id: Optional[str] = None  # 前驱节点ID，可能为空
        inputs: Optional[dict] = None  # 输入数据，以字典形式，可能为空
        created_at: int  # 创建时间戳
        extras: dict = {}  # 额外信息，以字典形式，默认为空

    event: StreamEvent = StreamEvent.NODE_STARTED
    workflow_run_id: str
    data: Data

    def to_ignore_detail_dict(self):
        return {
            "event": self.event.value,
            "task_id": self.task_id,
            "workflow_run_id": self.workflow_run_id,
            "data": {
                "id": self.data.id,
                "node_id": self.data.node_id,
                "node_type": self.data.node_type,
                "title": self.data.title,
                "index": self.data.index,
                "predecessor_node_id": self.data.predecessor_node_id,
                "inputs": None,
                "created_at": self.data.created_at,
                "extras": {}
            }
        }


class NodeFinishStreamResponse(StreamResponse):
    """
    NodeFinishStreamResponse实体类，用于表示节点完成流式响应。
    """

    class Data(BaseModel):
        """
        数据实体类，包含有关完成的节点的详细信息。
        """
        id: str  # 实体ID
        node_id: str  # 节点ID
        node_type: str  # 节点类型
        title: str  # 节点标题
        index: int  # 节点索引
        predecessor_node_id: Optional[str] = None  # 前驱节点ID
        inputs: Optional[dict] = None  # 输入数据
        process_data: Optional[dict] = None  # 处理数据
        outputs: Optional[dict] = None  # 输出数据
        status: str  # 状态（如：成功、失败）
        error: Optional[str] = None  # 错误信息（如果有）
        elapsed_time: float  # 执行时间（秒）
        execution_metadata: Optional[dict] = None  # 执行元数据
        created_at: int  # 创建时间戳
        finished_at: int  # 完成时间戳
        files: Optional[list[dict]] = []  # 附件列表

    event: StreamEvent = StreamEvent.NODE_FINISHED
    workflow_run_id: str
    data: Data

    def to_ignore_detail_dict(self):
        return {
            "event": self.event.value,
            "task_id": self.task_id,
            "workflow_run_id": self.workflow_run_id,
            "data": {
                "id": self.data.id,
                "node_id": self.data.node_id,
                "node_type": self.data.node_type,
                "title": self.data.title,
                "index": self.data.index,
                "predecessor_node_id": self.data.predecessor_node_id,
                "inputs": None,
                "process_data": None,
                "outputs": None,
                "status": self.data.status,
                "error": None,
                "elapsed_time": self.data.elapsed_time,
                "execution_metadata": None,
                "created_at": self.data.created_at,
                "finished_at": self.data.finished_at,
                "files": []
            }
        }


class IterationNodeStartStreamResponse(StreamResponse):
    """
    NodeStartStreamResponse entity
    """

    class Data(BaseModel):
        """
        Data entity
        """
        id: str
        node_id: str
        node_type: str
        title: str
        created_at: int
        extras: dict = {}
        metadata: dict = {}
        inputs: dict = {}

    event: StreamEvent = StreamEvent.ITERATION_STARTED
    workflow_run_id: str
    data: Data


class IterationNodeNextStreamResponse(StreamResponse):
    """
    NodeStartStreamResponse entity
    """

    class Data(BaseModel):
        """
        Data entity
        """
        id: str
        node_id: str
        node_type: str
        title: str
        index: int
        created_at: int
        pre_iteration_output: Optional[Any] = None
        extras: dict = {}

    event: StreamEvent = StreamEvent.ITERATION_NEXT
    workflow_run_id: str
    data: Data


class IterationNodeCompletedStreamResponse(StreamResponse):
    """
    NodeCompletedStreamResponse entity
    """

    class Data(BaseModel):
        """
        Data entity
        """
        id: str
        node_id: str
        node_type: str
        title: str
        outputs: Optional[dict] = None
        created_at: int
        extras: dict = None
        inputs: dict = None
        status: WorkflowNodeExecutionStatus
        error: Optional[str] = None
        elapsed_time: float
        total_tokens: int
        execution_metadata: Optional[dict] = None
        finished_at: int
        steps: int

    event: StreamEvent = StreamEvent.ITERATION_COMPLETED
    workflow_run_id: str
    data: Data


class TextChunkStreamResponse(StreamResponse):
    """
    TextChunkStreamResponse 实体类
    用于处理文本块流式响应的实体类。
    """

    class Data(BaseModel):
        """
        Data 实体类
        该类封装了文本块流式响应中的数据部分。
        """
        text: str  # 要响应的文本数据

    event: StreamEvent = StreamEvent.TEXT_CHUNK  # 事件类型，标识为文本块事件
    data: Data  # 数据实体，包含响应的文本数据


class TextReplaceStreamResponse(StreamResponse):
    """
    TextReplaceStreamResponse 实体类
    用于处理文本替换流式响应的实体类。
    """

    class Data(BaseModel):
        """
        Data 实体类
        该类封装了文本替换流式响应中的数据部分。
        """
        text: str  # 要替换的文本数据

    event: StreamEvent = StreamEvent.TEXT_REPLACE  # 事件类型，标识为文本替换事件
    data: Data  # 数据实体，包含要替换的文本数据


class PingStreamResponse(StreamResponse):
    """
    PingStreamResponse 实体类
    用于处理心跳检测流式响应的实体类。
    """
    event: StreamEvent = StreamEvent.PING  # 事件类型，标识为心跳事件


class AppStreamResponse(BaseModel):
    """
    AppStreamResponse 实体类
    该类封装了应用程序级别的流式响应。
    """
    stream_response: StreamResponse  # 流式响应实体，包含了具体的响应数据和事件类型。


class ChatbotAppStreamResponse(AppStreamResponse):
    """
    ChatbotAppStreamResponse 实体类
    用于表示聊天机器人应用流响应的数据结构。

    属性:
    - conversation_id: 对话ID，字符串类型，标识对话的唯一标识符。
    - message_id: 消息ID，字符串类型，标识消息的唯一标识符。
    - created_at: 创建时间戳，整型，表示响应创建的时间。
    """

    conversation_id: str
    message_id: str
    created_at: int


class CompletionAppStreamResponse(AppStreamResponse):
    """
    CompletionAppStreamResponse 实体类
    用于表示完成应用流响应的数据结构。

    属性:
    - message_id: 消息ID，字符串类型，标识消息的唯一标识符。
    - created_at: 创建时间戳，整型，表示响应创建的时间。
    """

    message_id: str
    created_at: int


class WorkflowAppStreamResponse(AppStreamResponse):
    """
    WorkflowAppStreamResponse 实体类
    用于表示工作流应用流响应的数据结构。

    属性:
    - workflow_run_id: 工作流运行ID，字符串类型，标识工作流运行的唯一标识符。
    """

    workflow_run_id: str


class AppBlockingResponse(BaseModel):
    """
    AppBlockingResponse 实体类
    用于表示应用阻塞响应的数据结构。

    属性:
    - task_id: 任务ID，字符串类型，标识任务的唯一标识符。

    方法:
    - to_dict: 将实例转换为字典格式。
    """

    task_id: str

    def to_dict(self) -> dict:
        """
        将 AppBlockingResponse 实例转换为符合 JSON 格式的字典。

        返回值:
        - 转换后的实例属性字典。
        """
        return jsonable_encoder(self)


class ChatbotAppBlockingResponse(AppBlockingResponse):
    """
    ChatbotAppBlockingResponse实体类，继承自AppBlockingResponse。
    用于表示聊天机器人的一种阻塞响应，包含与会话相关的数据。
    """

    class Data(BaseModel):
        """
        Data实体类，是ChatbotAppBlockingResponse的一部分，用于存储具体的数据信息。
        """
        id: str  # 唯一标识符
        mode: str  # 模式标识，表明响应的类型或模式
        conversation_id: str  # 会话的唯一标识符
        message_id: str  # 消息的唯一标识符
        answer: str  # 响应的答案内容
        metadata: dict = {}  # 附加的元数据信息，以字典形式存储，初始为空字典
        created_at: int  # 创建时间戳

    data: Data  # Data实体的实例，用于存储具体的阻塞响应数据


class CompletionAppBlockingResponse(AppBlockingResponse):
    """
    CompletionAppBlockingResponse 实体类
    用于表示一个完成态的应用阻塞响应

    属性:
    - data: Data 类实例，包含具体的响应数据
    """

    class Data(BaseModel):
        """
        CompletionAppBlockingResponse 的数据实体类
        包含完成态的详细信息

        属性:
        - id: 唯一标识符
        - mode: 模式标识
        - message_id: 消息ID
        - answer: 答案内容
        - metadata: 元数据，字典类型，默认为空
        - created_at: 创建时间戳
        """

        id: str
        mode: str
        message_id: str
        answer: str
        metadata: dict = {}
        created_at: int

    data: Data


class WorkflowAppBlockingResponse(AppBlockingResponse):
    """
    WorkflowAppBlockingResponse 实体类
    用于表示一个工作流应用的阻塞响应

    属性:
    - workflow_run_id: 工作流运行的唯一标识符
    - data: Data 类实例，包含具体的工作流响应数据
    """

    class Data(BaseModel):
        """
        WorkflowAppBlockingResponse 的数据实体类
        包含工作流的详细执行信息

        属性:
        - id: 唯一标识符
        - workflow_id: 工作流ID
        - status: 状态标识
        - outputs: 输出结果，字典类型，可为空
        - error: 错误信息，字符串类型，可为空
        - elapsed_time: 执行耗时，浮点型，单位为秒
        - total_tokens: 总令牌数
        - total_steps: 总步骤数
        - created_at: 创建时间戳
        - finished_at: 完成时间戳
        """

        id: str
        workflow_id: str
        status: str
        outputs: Optional[dict] = None
        error: Optional[str] = None
        elapsed_time: float
        total_tokens: int
        total_steps: int
        created_at: int
        finished_at: int

    workflow_run_id: str
    data: Data


class WorkflowIterationState(BaseModel):
    """
    WorkflowIterationState entity
    """

    class Data(BaseModel):
        """
        Data entity
        """
        parent_iteration_id: Optional[str] = None
        iteration_id: str
        current_index: int
        iteration_steps_boundary: list[int] = None
        node_execution_id: str
        started_at: float
        inputs: dict = None
        total_tokens: int = 0
        node_data: BaseNodeData

    current_iterations: dict[str, Data] = None
