import logging
from collections.abc import Generator
from typing import Any, Union

from core.app.apps.base_app_queue_manager import AppQueueManager
from core.app.entities.app_invoke_entities import (
    InvokeFrom,
    WorkflowAppGenerateEntity,
)
from core.app.entities.queue_entities import (
    QueueErrorEvent,
    QueueMessageReplaceEvent,
    QueueNodeFailedEvent,
    QueueNodeStartedEvent,
    QueueNodeSucceededEvent,
    QueuePingEvent,
    QueueStopEvent,
    QueueTextChunkEvent,
    QueueWorkflowFailedEvent,
    QueueWorkflowStartedEvent,
    QueueWorkflowSucceededEvent,
)
from core.app.entities.task_entities import (
    ErrorStreamResponse,
    StreamResponse,
    TextChunkStreamResponse,
    TextReplaceStreamResponse,
    WorkflowAppBlockingResponse,
    WorkflowAppStreamResponse,
    WorkflowFinishStreamResponse,
    WorkflowTaskState,
)
from core.app.task_pipeline.based_generate_task_pipeline import BasedGenerateTaskPipeline
from core.app.task_pipeline.workflow_cycle_manage import WorkflowCycleManage
from core.workflow.entities.node_entities import SystemVariable
from extensions.ext_database import db
from models.account import Account
from models.model import EndUser
from models.workflow import (
    Workflow,
    WorkflowAppLog,
    WorkflowAppLogCreatedFrom,
    WorkflowRun,
)

logger = logging.getLogger(__name__)


class WorkflowAppGenerateTaskPipeline(BasedGenerateTaskPipeline, WorkflowCycleManage):
    """
    WorkflowAppGenerateTaskPipeline 是一个为应用程序生成流输出和状态管理的类。
    """
    _workflow: Workflow  # 工作流实例
    _user: Union[Account, EndUser]  # 用户账户
    _task_state: WorkflowTaskState  # 工作流任务状态
    _application_generate_entity: WorkflowAppGenerateEntity  # 应用生成实体
    _workflow_system_variables: dict[SystemVariable, Any]  # 工作流系统变量

    def __init__(self, application_generate_entity: WorkflowAppGenerateEntity,
                 workflow: Workflow,
                 queue_manager: AppQueueManager,
                 user: Union[Account, EndUser],
                 stream: bool) -> None:
        """
        初始化 GenerateTaskPipeline。
        :param application_generate_entity: 应用生成实体
        :param workflow: 工作流
        :param queue_manager: 队列管理器
        :param user: 用户
        :param stream: 是否为流式
        """
        super().__init__(application_generate_entity, queue_manager, user, stream)

        self._workflow = workflow
        self._workflow_system_variables = {
            SystemVariable.FILES: application_generate_entity.files,
        }

        self._task_state = WorkflowTaskState()

    def process(self) -> Union[WorkflowAppBlockingResponse, Generator[WorkflowAppStreamResponse, None, None]]:
        """
        处理生成任务管道。
        :return: 根据是否为流式返回不同的响应类型
        """
        db.session.refresh(self._workflow)  # 刷新工作流实例
        db.session.refresh(self._user)  # 刷新用户实例
        db.session.close()  # 关闭数据库会话

        generator = self._process_stream_response()  # 处理流响应
        if self._stream:
            return self._to_stream_response(generator)  # 转换为流式响应
        else:
            return self._to_blocking_response(generator)  # 转换为阻塞式响应

    def _to_blocking_response(self, generator: Generator[StreamResponse, None, None]) \
            -> WorkflowAppBlockingResponse:
        """
        转换为阻塞式响应。
        :return: 阻塞式响应实例
        """
        for stream_response in generator:
            if isinstance(stream_response, ErrorStreamResponse):
                raise stream_response.err  # 抛出错误
            elif isinstance(stream_response, WorkflowFinishStreamResponse):
                workflow_run = db.session.query(WorkflowRun).filter(
                    WorkflowRun.id == self._task_state.workflow_run_id).first()

                response = WorkflowAppBlockingResponse(
                    task_id=self._application_generate_entity.task_id,
                    workflow_run_id=workflow_run.id,
                    data=WorkflowAppBlockingResponse.Data(
                        id=workflow_run.id,
                        workflow_id=workflow_run.workflow_id,
                        status=workflow_run.status,
                        outputs=workflow_run.outputs_dict,
                        error=workflow_run.error,
                        elapsed_time=workflow_run.elapsed_time,
                        total_tokens=workflow_run.total_tokens,
                        total_steps=workflow_run.total_steps,
                        created_at=int(workflow_run.created_at.timestamp()),
                        finished_at=int(workflow_run.finished_at.timestamp())
                    )
                )

                return response
            else:
                continue

        raise Exception('Queue listening stopped unexpectedly.')  # 异常处理

    def _to_stream_response(self, generator: Generator[StreamResponse, None, None]) \
            -> Generator[WorkflowAppStreamResponse, None, None]:
        """
        转换为流式响应。
        :return: 流式响应生成器
        """
        for stream_response in generator:
            yield WorkflowAppStreamResponse(
                workflow_run_id=self._task_state.workflow_run_id,
                stream_response=stream_response
            )

    def _process_stream_response(self) -> Generator[StreamResponse, None, None]:
        """
        处理流式响应。
        :return: 流式响应生成器
        """
        for message in self._queue_manager.listen():  # 监听队列消息
            event = message.event

            if isinstance(event, QueueErrorEvent):
                err = self._handle_error(event)
                yield self._error_to_stream_response(err)
                break
            # 处理工作流开始事件
            elif isinstance(event, QueueWorkflowStartedEvent):
                workflow_run = self._handle_workflow_start()
                yield self._workflow_start_to_stream_response(
                    task_id=self._application_generate_entity.task_id,
                    workflow_run=workflow_run
                )
            # 处理节点开始事件
            elif isinstance(event, QueueNodeStartedEvent):
                workflow_node_execution = self._handle_node_start(event)
                yield self._workflow_node_start_to_stream_response(
                    event=event,
                    task_id=self._application_generate_entity.task_id,
                    workflow_node_execution=workflow_node_execution
                )
            # 处理节点完成事件
            elif isinstance(event, QueueNodeSucceededEvent | QueueNodeFailedEvent):
                workflow_node_execution = self._handle_node_finished(event)
                yield self._workflow_node_finish_to_stream_response(
                    task_id=self._application_generate_entity.task_id,
                    workflow_node_execution=workflow_node_execution
                )
            # 处理工作流完成事件
            elif isinstance(event, QueueStopEvent | QueueWorkflowSucceededEvent | QueueWorkflowFailedEvent):
                workflow_run = self._handle_workflow_finished(event)

                # 保存工作流应用日志
                self._save_workflow_app_log(workflow_run)

                yield self._workflow_finish_to_stream_response(
                    task_id=self._application_generate_entity.task_id,
                    workflow_run=workflow_run
                )
            # 处理文本块事件
            elif isinstance(event, QueueTextChunkEvent):
                delta_text = event.text
                if delta_text is None:
                    continue

                self._task_state.answer += delta_text
                yield self._text_chunk_to_stream_response(delta_text)
            # 处理文本替换事件
            elif isinstance(event, QueueMessageReplaceEvent):
                yield self._text_replace_to_stream_response(event.text)
            # 处理心跳事件
            elif isinstance(event, QueuePingEvent):
                yield self._ping_stream_response()
            else:
                continue

    def _save_workflow_app_log(self, workflow_run: WorkflowRun) -> None:
        """
        保存工作流应用日志。
        :param workflow_run: 工作流运行实例
        """
        invoke_from = self._application_generate_entity.invoke_from
        if invoke_from == InvokeFrom.SERVICE_API:
            created_from = WorkflowAppLogCreatedFrom.SERVICE_API
        elif invoke_from == InvokeFrom.EXPLORE:
            created_from = WorkflowAppLogCreatedFrom.INSTALLED_APP
        elif invoke_from == InvokeFrom.WEB_APP:
            created_from = WorkflowAppLogCreatedFrom.WEB_APP
        else:
            # 为调试目的不保存日志
            return

        workflow_app_log = WorkflowAppLog(
            tenant_id=workflow_run.tenant_id,
            app_id=workflow_run.app_id,
            workflow_id=workflow_run.workflow_id,
            workflow_run_id=workflow_run.id,
            created_from=created_from.value,
            created_by_role=('account' if isinstance(self._user, Account) else 'end_user'),
            created_by=self._user.id,
        )
        db.session.add(workflow_app_log)
        db.session.commit()
        db.session.close()

    def _text_chunk_to_stream_response(self, text: str) -> TextChunkStreamResponse:
        """
        处理文本块事件。
        :param text: 文本块
        :return: 文本块流式响应实例
        """
        response = TextChunkStreamResponse(
            task_id=self._application_generate_entity.task_id,
            data=TextChunkStreamResponse.Data(text=text)
        )

        return response

    def _text_replace_to_stream_response(self, text: str) -> TextReplaceStreamResponse:
        """
        文本替换到流式响应。
        :param text: 替换后的文本
        :return: 文本替换流式响应实例
        """
        return TextReplaceStreamResponse(
            task_id=self._application_generate_entity.task_id,
            text=TextReplaceStreamResponse.Data(text=text)
        )
