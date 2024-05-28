import json
import time
from datetime import datetime, timezone
from typing import Optional, Union, cast

from core.app.entities.app_invoke_entities import InvokeFrom
from core.app.entities.queue_entities import (
    QueueNodeFailedEvent,
    QueueNodeStartedEvent,
    QueueNodeSucceededEvent,
    QueueStopEvent,
    QueueWorkflowFailedEvent,
    QueueWorkflowSucceededEvent,
)
from core.app.entities.task_entities import (
    NodeExecutionInfo,
    NodeFinishStreamResponse,
    NodeStartStreamResponse,
    WorkflowFinishStreamResponse,
    WorkflowStartStreamResponse,
)
from core.app.task_pipeline.workflow_iteration_cycle_manage import WorkflowIterationCycleManage
from core.file.file_obj import FileVar
from core.model_runtime.utils.encoders import jsonable_encoder
from core.tools.tool_manager import ToolManager
from core.workflow.entities.node_entities import NodeRunMetadataKey, NodeType
from core.workflow.nodes.tool.entities import ToolNodeData
from core.workflow.workflow_engine_manager import WorkflowEngineManager
from extensions.ext_database import db
from models.account import Account
from models.model import EndUser
from models.workflow import (
    CreatedByRole,
    Workflow,
    WorkflowNodeExecution,
    WorkflowNodeExecutionStatus,
    WorkflowNodeExecutionTriggeredFrom,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowRunTriggeredFrom,
)


class WorkflowCycleManage(WorkflowIterationCycleManage):
    def _init_workflow_run(self, workflow: Workflow,
                           triggered_from: WorkflowRunTriggeredFrom,
                           user: Union[Account, EndUser],
                           user_inputs: dict,
                           system_inputs: Optional[dict] = None) -> WorkflowRun:
        """
        初始化工作流运行实例。
        :param workflow: Workflow 实例，表示要运行的工作流。
        :param triggered_from: 工作流运行触发来源。
        :param user: 账户或终端用户，表示触发工作流的用户。
        :param user_inputs: 用户变量输入，即用户在工作流运行中提供的输入数据。
        :param system_inputs: 系统输入，例如查询、文件等系统级别数据（可选）。
        :return: 初始化后的 WorkflowRun 实例。
        """
        # 计算新的序列号，确保每个工作流运行实例的序列号唯一。
        max_sequence = db.session.query(db.func.max(WorkflowRun.sequence_number)) \
                           .filter(WorkflowRun.tenant_id == workflow.tenant_id) \
                           .filter(WorkflowRun.app_id == workflow.app_id) \
                           .scalar() or 0
        new_sequence_number = max_sequence + 1

        # 合并用户输入和系统输入，并处理特殊值。
        inputs = {**user_inputs}
        for key, value in (system_inputs or {}).items():
            if key.value == 'conversation':
                continue

            inputs[f'sys.{key.value}'] = value
        inputs = WorkflowEngineManager.handle_special_values(inputs)

        # 初始化 WorkflowRun 实例并准备持久化到数据库。
        workflow_run = WorkflowRun(
            tenant_id=workflow.tenant_id,
            app_id=workflow.app_id,
            sequence_number=new_sequence_number,
            workflow_id=workflow.id,
            type=workflow.type,
            triggered_from=triggered_from.value,
            version=workflow.version,
            graph=workflow.graph,
            inputs=json.dumps(inputs),
            status=WorkflowRunStatus.RUNNING.value,
            created_by_role=(CreatedByRole.ACCOUNT.value
                             if isinstance(user, Account) else CreatedByRole.END_USER.value),
            created_by=user.id
        )

        # 将工作流运行实例添加到数据库会话并提交，确保其持久化。
        db.session.add(workflow_run)
        db.session.commit()
        db.session.refresh(workflow_run)
        db.session.close()

        return workflow_run

    def _workflow_run_success(self, workflow_run: WorkflowRun,
                              start_at: float,
                              total_tokens: int,
                              total_steps: int,
                              outputs: Optional[str] = None) -> WorkflowRun:
        """
        标记工作流运行成功，并更新相关状态和统计信息。
        :param workflow_run: WorkflowRun 实例，表示正在运行的工作流实例。
        :param start_at: 开始时间，表示工作流运行的起始时间戳。
        :param total_tokens: 总令牌数，表示工作流运行过程中处理的令牌总数。
        :param total_steps: 总步骤数，表示工作流运行过程中执行的总步骤数。
        :param outputs: 输出数据，表示工作流运行的结果（可选）。
        :return: 更新后的 WorkflowRun 实例。
        """
        # 更新工作流运行状态及相关统计信息，并持久化到数据库。
        workflow_run.status = WorkflowRunStatus.SUCCEEDED.value
        workflow_run.outputs = outputs
        workflow_run.elapsed_time = time.perf_counter() - start_at
        workflow_run.total_tokens = total_tokens
        workflow_run.total_steps = total_steps
        workflow_run.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)

        db.session.commit()
        db.session.refresh(workflow_run)
        db.session.close()

        return workflow_run

    def _workflow_run_failed(self, workflow_run: WorkflowRun,
                             start_at: float,
                             total_tokens: int,
                             total_steps: int,
                             status: WorkflowRunStatus,
                             error: str) -> WorkflowRun:
        """
        处理工作流运行失败的逻辑。
        
        :param workflow_run: 表示一个工作流运行实例的对象。
        :param start_at: 工作流开始运行的时间戳（秒）。
        :param total_tokens: 运行过程中消耗的总令牌数。
        :param total_steps: 运行过程中执行的总步骤数。
        :param status: 工作流运行的状态。
        :param error: 运行失败时的错误信息。
        :return: 更新后的工作流运行实例对象。
        """
        # 更新工作流运行状态及相关属性
        workflow_run.status = status.value
        workflow_run.error = error
        workflow_run.elapsed_time = time.perf_counter() - start_at  # 计算运行耗时
        workflow_run.total_tokens = total_tokens
        workflow_run.total_steps = total_steps
        workflow_run.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)

        # 提交数据库事务，更新数据库中的工作流运行状态
        db.session.commit()
        db.session.refresh(workflow_run)  # 刷新工作流运行对象，以获取最新的数据库状态
        db.session.close()  # 关闭数据库会话

        return workflow_run  # 返回更新后的工作流运行实例对象

    def _init_node_execution_from_workflow_run(self, workflow_run: WorkflowRun,
                                                node_id: str,
                                                node_type: NodeType,
                                                node_title: str,
                                                node_run_index: int = 1,
                                                predecessor_node_id: Optional[str] = None) -> WorkflowNodeExecution:
            """
            从工作流运行初始化工作流节点执行
            :param workflow_run: 工作流运行实例
            :param node_id: 节点ID
            :param node_type: 节点类型
            :param node_title: 节点标题
            :param node_run_index: 执行索引，默认为1
            :param predecessor_node_id: 前驱节点ID，如果存在
            :return: 初始化后的工作流节点执行实例
            """
            # 初始化工作流节点执行信息
            workflow_node_execution = WorkflowNodeExecution(
                tenant_id=workflow_run.tenant_id,
                app_id=workflow_run.app_id,
                workflow_id=workflow_run.workflow_id,
                triggered_from=WorkflowNodeExecutionTriggeredFrom.WORKFLOW_RUN.value,
                workflow_run_id=workflow_run.id,
                predecessor_node_id=predecessor_node_id,
                index=node_run_index,
                node_id=node_id,
                node_type=node_type.value,
                title=node_title,
                status=WorkflowNodeExecutionStatus.RUNNING.value,
                created_by_role=workflow_run.created_by_role,
                created_by=workflow_run.created_by
            )

            # 将节点执行实例添加到数据库会话并提交
            db.session.add(workflow_node_execution)
            db.session.commit()
            db.session.refresh(workflow_node_execution)  # 刷新实体以获取刚插入的ID等信息
            db.session.close()  # 关闭数据库会话

            return workflow_node_execution  # 返回初始化的工作流节点执行实例

    def _workflow_node_execution_success(self, workflow_node_execution: WorkflowNodeExecution,
                                            start_at: float,
                                            inputs: Optional[dict] = None,
                                            process_data: Optional[dict] = None,
                                            outputs: Optional[dict] = None,
                                            execution_metadata: Optional[dict] = None) -> WorkflowNodeExecution:
            """
            处理工作流节点执行成功的情况。
            
            :param workflow_node_execution: 工作流节点执行实例
            :param start_at: 执行开始时间（秒）
            :param inputs: 输入参数
            :param process_data: 处理数据
            :param outputs: 输出结果
            :param execution_metadata: 执行元数据
            :return: 更新后的工作流节点执行实例
            """
            # 处理输入和输出中的特殊值
            inputs = WorkflowEngineManager.handle_special_values(inputs)
            outputs = WorkflowEngineManager.handle_special_values(outputs)

            workflow_node_execution.status = WorkflowNodeExecutionStatus.SUCCEEDED.value
            workflow_node_execution.elapsed_time = time.perf_counter() - start_at
            workflow_node_execution.inputs = json.dumps(inputs) if inputs else None
            workflow_node_execution.process_data = json.dumps(process_data) if process_data else None
            workflow_node_execution.outputs = json.dumps(outputs) if outputs else None
            workflow_node_execution.execution_metadata = json.dumps(jsonable_encoder(execution_metadata)) \
                if execution_metadata else None 
            workflow_node_execution.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)

            # 提交数据库事务并关闭数据库会话
            db.session.commit()
            db.session.refresh(workflow_node_execution)
            db.session.close()

            return workflow_node_execution

    def _workflow_node_execution_failed(self, workflow_node_execution: WorkflowNodeExecution,
                                        start_at: float,
                                        error: str,
                                        inputs: Optional[dict] = None,
                                        process_data: Optional[dict] = None,
                                        outputs: Optional[dict] = None,
                                        execution_metadata: Optional[dict] = None
                                        ) -> WorkflowNodeExecution:
        """
        Workflow node execution failed
        :param workflow_node_execution: workflow node execution
        :param start_at: start time
        :param error: error message
        :return:
        """
        inputs = WorkflowEngineManager.handle_special_values(inputs)
        outputs = WorkflowEngineManager.handle_special_values(outputs)

        workflow_node_execution.status = WorkflowNodeExecutionStatus.FAILED.value
        workflow_node_execution.error = error
        workflow_node_execution.elapsed_time = time.perf_counter() - start_at
        workflow_node_execution.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
        workflow_node_execution.inputs = json.dumps(inputs) if inputs else None
        workflow_node_execution.process_data = json.dumps(process_data) if process_data else None
        workflow_node_execution.outputs = json.dumps(outputs) if outputs else None
        workflow_node_execution.execution_metadata = json.dumps(jsonable_encoder(execution_metadata)) \
            if execution_metadata else None

        # 提交数据库事务，更新工作流节点执行信息
        db.session.commit()
        db.session.refresh(workflow_node_execution)
        db.session.close()

        return workflow_node_execution

    def _workflow_start_to_stream_response(self, task_id: str,
                                        workflow_run: WorkflowRun) -> WorkflowStartStreamResponse:
        """
        将工作流启动信息转换为流响应。
        :param task_id: 任务ID
        :param workflow_run: 工作流运行实例
        :return: 返回工作流启动的流响应实例
        """
        # 构建并返回工作流启动的流响应实例
        return WorkflowStartStreamResponse(
            task_id=task_id,
            workflow_run_id=workflow_run.id,
            data=WorkflowStartStreamResponse.Data(
                id=workflow_run.id,
                workflow_id=workflow_run.workflow_id,
                sequence_number=workflow_run.sequence_number,
                inputs=workflow_run.inputs_dict,
                created_at=int(workflow_run.created_at.timestamp())
            )
        )

    def _workflow_finish_to_stream_response(self, task_id: str,
                                                workflow_run: WorkflowRun) -> WorkflowFinishStreamResponse:
            """
            将工作流完成信息转换为流响应。
            :param task_id: 任务ID
            :param workflow_run: 工作流运行实例
            :return: 返回工作流完成的流响应实例
            """
            created_by = None
            # 根据创建者角色，设置创建者信息
            if workflow_run.created_by_role == CreatedByRole.ACCOUNT.value:
                # 如果是由账户创建的工作流，提取账户创建者信息
                created_by_account = workflow_run.created_by_account
                if created_by_account:
                    created_by = {
                        "id": created_by_account.id,
                        "name": created_by_account.name,
                        "email": created_by_account.email,
                    }
            else:
                # 如果是由终端用户创建的工作流，提取终端用户创建者信息
                created_by_end_user = workflow_run.created_by_end_user
                if created_by_end_user:
                    created_by = {
                        "id": created_by_end_user.id,
                        "user": created_by_end_user.session_id,
                    }

            # 构建并返回工作流完成的流响应实例
            return WorkflowFinishStreamResponse(
                task_id=task_id,
                workflow_run_id=workflow_run.id,
                data=WorkflowFinishStreamResponse.Data(
                    id=workflow_run.id,
                    workflow_id=workflow_run.workflow_id,
                    sequence_number=workflow_run.sequence_number,
                    status=workflow_run.status,
                    outputs=workflow_run.outputs_dict,
                    error=workflow_run.error,
                    elapsed_time=workflow_run.elapsed_time,
                    total_tokens=workflow_run.total_tokens,
                    total_steps=workflow_run.total_steps,
                    created_by=created_by,
                    created_at=int(workflow_run.created_at.timestamp()),
                    finished_at=int(workflow_run.finished_at.timestamp()),
                    files=self._fetch_files_from_node_outputs(workflow_run.outputs_dict)
                )
            )

    def _workflow_node_start_to_stream_response(self, event: QueueNodeStartedEvent,
                                                task_id: str,
                                                workflow_node_execution: WorkflowNodeExecution) \
            -> NodeStartStreamResponse:
        """
        将工作流节点启动事件转换为流响应。
        :param event: 队列节点启动事件，包含节点开始执行时的信息。
        :param task_id: 任务ID，标识特定的任务。
        :param workflow_node_execution: 工作流节点执行实例，包含节点执行的详细信息。
        :return: 返回一个节点启动流响应对象，包含任务ID、工作流运行ID和节点执行的详细数据。
        """
        # 构建节点启动流响应对象
        response = NodeStartStreamResponse(
            task_id=task_id,
            workflow_run_id=workflow_node_execution.workflow_run_id,
            data=NodeStartStreamResponse.Data(
                id=workflow_node_execution.id,
                node_id=workflow_node_execution.node_id,
                node_type=workflow_node_execution.node_type,
                title=workflow_node_execution.title,
                index=workflow_node_execution.index,
                predecessor_node_id=workflow_node_execution.predecessor_node_id,
                inputs=workflow_node_execution.inputs_dict,
                created_at=int(workflow_node_execution.created_at.timestamp())
            )
        )

        # 额外信息逻辑处理，仅当节点类型为TOOL时执行
        if event.node_type == NodeType.TOOL:
            node_data = cast(ToolNodeData, event.node_data)
            # 为工具节点添加图标信息到响应对象的extras字段
            response.data.extras['icon'] = ToolManager.get_tool_icon(
                tenant_id=self._application_generate_entity.app_config.tenant_id,
                provider_type=node_data.provider_type,
                provider_id=node_data.provider_id
            )

        return response

    def _workflow_node_finish_to_stream_response(self, task_id: str, workflow_node_execution: WorkflowNodeExecution) \
            -> NodeFinishStreamResponse:
        """
        将工作流节点执行的结束信息转换为流式响应。
        :param task_id: 任务ID
        :param workflow_node_execution: 工作流节点执行实例
        :return: 返回一个节点完成的流式响应对象
        """
        # 构建并返回一个NodeFinishStreamResponse实例
        return NodeFinishStreamResponse(
            task_id=task_id,
            workflow_run_id=workflow_node_execution.workflow_run_id,
            data=NodeFinishStreamResponse.Data(
                id=workflow_node_execution.id,
                node_id=workflow_node_execution.node_id,
                node_type=workflow_node_execution.node_type,
                index=workflow_node_execution.index,
                title=workflow_node_execution.title,
                predecessor_node_id=workflow_node_execution.predecessor_node_id,
                inputs=workflow_node_execution.inputs_dict,
                process_data=workflow_node_execution.process_data_dict,
                outputs=workflow_node_execution.outputs_dict,
                status=workflow_node_execution.status,
                error=workflow_node_execution.error,
                elapsed_time=workflow_node_execution.elapsed_time,
                execution_metadata=workflow_node_execution.execution_metadata_dict,
                created_at=int(workflow_node_execution.created_at.timestamp()),
                finished_at=int(workflow_node_execution.finished_at.timestamp()),
                files=self._fetch_files_from_node_outputs(workflow_node_execution.outputs_dict)
            )
        )

    def _handle_workflow_start(self) -> WorkflowRun:
        """
        处理工作流开始的逻辑。
        
        该方法初始化一个工作流运行实例，并更新任务状态来反映工作流的开始。
        
        返回值:
            WorkflowRun: 返回初始化的工作流运行实例。
        """
        # 记录工作流开始时间
        self._task_state.start_at = time.perf_counter()

        # 初始化工作流运行实例，设置触发来源和用户信息
        workflow_run = self._init_workflow_run(
            workflow=self._workflow,
            triggered_from=WorkflowRunTriggeredFrom.DEBUGGING
            if self._application_generate_entity.invoke_from == InvokeFrom.DEBUGGER
            else WorkflowRunTriggeredFrom.APP_RUN,
            user=self._user,
            user_inputs=self._application_generate_entity.inputs,
            system_inputs=self._workflow_system_variables
        )

        # 设置任务状态的工作流运行ID
        self._task_state.workflow_run_id = workflow_run.id

        # 关闭数据库会话
        db.session.close()

        return workflow_run

    def _handle_node_start(self, event: QueueNodeStartedEvent) -> WorkflowNodeExecution:
        """
        处理节点开始执行的事件。
        
        参数:
        - event: QueueNodeStartedEvent, 表示节点开始执行的事件对象，包含节点的详细信息。
        
        返回值:
        - WorkflowNodeExecution, 节点执行的实例。
        """
        # 从数据库查询对应的 workflow run 信息
        workflow_run = db.session.query(WorkflowRun).filter(WorkflowRun.id == self._task_state.workflow_run_id).first()
        # 根据 workflow run 信息初始化节点执行实例
        workflow_node_execution = self._init_node_execution_from_workflow_run(
            workflow_run=workflow_run,
            node_id=event.node_id,
            node_type=event.node_type,
            node_title=event.node_data.title,
            node_run_index=event.node_run_index,
            predecessor_node_id=event.predecessor_node_id
        )

        # 创建节点执行的最新信息，并记录开始时间
        latest_node_execution_info = NodeExecutionInfo(
            workflow_node_execution_id=workflow_node_execution.id,
            node_type=event.node_type,
            start_at=time.perf_counter()
        )

        # 更新任务状态，包括节点执行信息和最新节点执行信息
        self._task_state.ran_node_execution_infos[event.node_id] = latest_node_execution_info
        self._task_state.latest_node_execution_info = latest_node_execution_info

        # 更新任务总步骤数
        self._task_state.total_steps += 1

        # 关闭数据库会话
        db.session.close()

        return workflow_node_execution

    def _handle_node_finished(self, event: QueueNodeSucceededEvent | QueueNodeFailedEvent) -> WorkflowNodeExecution:
        """
        处理节点完成的事件，无论是成功还是失败。
        
        :param event: 队列节点成功或失败的事件对象，继承自QueueNodeSucceededEvent或QueueNodeFailedEvent。
        :return: 更新后的WorkflowNodeExecution对象。
        """
        # 根据节点ID获取当前节点执行信息
        current_node_execution = self._task_state.ran_node_execution_infos[event.node_id]
        # 从数据库中查询对应的workflow节点执行信息
        workflow_node_execution = db.session.query(WorkflowNodeExecution).filter(
            WorkflowNodeExecution.id == current_node_execution.workflow_node_execution_id).first()
        
        execution_metadata = event.execution_metadata if isinstance(event, QueueNodeSucceededEvent) else None
        
        if self._iteration_state and self._iteration_state.current_iterations:
            if not execution_metadata:
                execution_metadata = {}
            current_iteration_data = None
            for iteration_node_id in self._iteration_state.current_iterations:
                data = self._iteration_state.current_iterations[iteration_node_id]
                if data.parent_iteration_id == None:
                    current_iteration_data = data
                    break

            if current_iteration_data:
                execution_metadata[NodeRunMetadataKey.ITERATION_ID] = current_iteration_data.iteration_id
                execution_metadata[NodeRunMetadataKey.ITERATION_INDEX] = current_iteration_data.current_index

        if isinstance(event, QueueNodeSucceededEvent):
            # 节点成功完成时的处理逻辑
            workflow_node_execution = self._workflow_node_execution_success(
                workflow_node_execution=workflow_node_execution,
                start_at=current_node_execution.start_at,
                inputs=event.inputs,
                process_data=event.process_data,
                outputs=event.outputs,
                execution_metadata=execution_metadata
            )

            if execution_metadata and execution_metadata.get(NodeRunMetadataKey.TOTAL_TOKENS):
                self._task_state.total_tokens += (
                    int(execution_metadata.get(NodeRunMetadataKey.TOTAL_TOKENS)))
                
                if self._iteration_state:
                    for iteration_node_id in self._iteration_state.current_iterations:
                        data = self._iteration_state.current_iterations[iteration_node_id]
                        if execution_metadata.get(NodeRunMetadataKey.TOTAL_TOKENS):
                            data.total_tokens += int(execution_metadata.get(NodeRunMetadataKey.TOTAL_TOKENS))

            if workflow_node_execution.node_type == NodeType.LLM.value:
                outputs = workflow_node_execution.outputs_dict
                usage_dict = outputs.get('usage', {})
                self._task_state.metadata['usage'] = usage_dict
        else:
            # 节点失败完成时的处理逻辑
            workflow_node_execution = self._workflow_node_execution_failed(
                workflow_node_execution=workflow_node_execution,
                start_at=current_node_execution.start_at,
                error=event.error,
                inputs=event.inputs,
                process_data=event.process_data,
                outputs=event.outputs,
                execution_metadata=execution_metadata
            )

        # 关闭数据库会话
        db.session.close()

        return workflow_node_execution

    def _handle_workflow_finished(self, event: QueueStopEvent | QueueWorkflowSucceededEvent | QueueWorkflowFailedEvent) \
            -> Optional[WorkflowRun]:
        """
        处理工作流完成的事件，根据事件类型更新工作流运行状态。

        参数:
        - event: 队列停止事件、工作流成功事件或工作流失败事件，触发对工作流运行状态的更新。

        返回值:
        - 如果找到对应的工作流运行实例，则返回更新后的实例；否则，返回None。
        """
        # 从数据库查询对应的工作流运行实例
        workflow_run = db.session.query(WorkflowRun).filter(
            WorkflowRun.id == self._task_state.workflow_run_id).first()
        if not workflow_run:
            return None

        # 处理工作流停止事件
        if isinstance(event, QueueStopEvent):
            workflow_run = self._workflow_run_failed(
                workflow_run=workflow_run,
                start_at=self._task_state.start_at,
                total_tokens=self._task_state.total_tokens,
                total_steps=self._task_state.total_steps,
                status=WorkflowRunStatus.STOPPED,
                error='Workflow stopped.'
            )

            # 如果存在最新节点执行信息，则处理该节点的失败
            latest_node_execution_info = self._task_state.latest_node_execution_info
            if latest_node_execution_info:
                workflow_node_execution = db.session.query(WorkflowNodeExecution).filter(
                    WorkflowNodeExecution.id == latest_node_execution_info.workflow_node_execution_id).first()
                if (workflow_node_execution
                        and workflow_node_execution.status == WorkflowNodeExecutionStatus.RUNNING.value):
                    self._workflow_node_execution_failed(
                        workflow_node_execution=workflow_node_execution,
                        start_at=latest_node_execution_info.start_at,
                        error='Workflow stopped.'
                    )
        # 处理工作流失败事件
        elif isinstance(event, QueueWorkflowFailedEvent):
            workflow_run = self._workflow_run_failed(
                workflow_run=workflow_run,
                start_at=self._task_state.start_at,
                total_tokens=self._task_state.total_tokens,
                total_steps=self._task_state.total_steps,
                status=WorkflowRunStatus.FAILED,
                error=event.error
            )
        else:
            # 处理工作流成功事件
            if self._task_state.latest_node_execution_info:
                workflow_node_execution = db.session.query(WorkflowNodeExecution).filter(
                    WorkflowNodeExecution.id == self._task_state.latest_node_execution_info.workflow_node_execution_id).first()
                outputs = workflow_node_execution.outputs
            else:
                outputs = None

            workflow_run = self._workflow_run_success(
                workflow_run=workflow_run,
                start_at=self._task_state.start_at,
                total_tokens=self._task_state.total_tokens,
                total_steps=self._task_state.total_steps,
                outputs=outputs
            )

        # 更新任务状态的工作流运行ID，并关闭数据库会话
        self._task_state.workflow_run_id = workflow_run.id

        db.session.close()

        return workflow_run

    def _fetch_files_from_node_outputs(self, outputs_dict: dict) -> list[dict]:
        """
        从节点输出中获取文件
        :param outputs_dict: 节点输出字典
        :return: 文件信息列表
        """
        # 如果输出字典为空，则直接返回空列表
        if not outputs_dict:
            return []

        files = []
        # 遍历输出字典中的每一个输出变量及其值
        for output_var, output_value in outputs_dict.items():
            # 从变量值中获取文件信息
            file_vars = self._fetch_files_from_variable_value(output_value)
            # 如果获取到文件信息，则将其添加到文件列表中
            if file_vars:
                files.extend(file_vars)

        return files

    def _fetch_files_from_variable_value(self, value: Union[dict, list]) -> list[dict]:
        """
        从变量值中获取文件信息
        :param value: 变量值，可以是字典或列表
        :return: 文件信息列表
        """
        # 如果变量值为空，则直接返回空列表
        if not value:
            return []

        files = []
        # 如果变量值是列表，则遍历列表中的每个项
        if isinstance(value, list):
            for item in value:
                # 尝试从列表项中获取文件信息
                file_var = self._get_file_var_from_value(item)
                # 如果获取成功，则将其添加到文件列表中
                if file_var:
                    files.append(file_var)
        # 如果变量值是字典
        elif isinstance(value, dict):
            # 尝试直接从字典中获取文件信息
            file_var = self._get_file_var_from_value(value)
            # 如果获取成功，则将其添加到文件列表中
            if file_var:
                files.append(file_var)

        return files

    def _get_file_var_from_value(self, value: Union[dict, list]) -> Optional[dict]:
        """
        从值中获取文件变量信息
        :param value: 变量值，可以是字典或列表
        :return: 文件变量信息的字典，如果不存在则返回None
        """
        # 如果值为空，则直接返回None
        if not value:
            return None

        # 如果值是字典
        if isinstance(value, dict):
            # 检查字典是否表示一个文件变量
            if '__variant' in value and value['__variant'] == FileVar.__name__:
                return value
        # 如果值本身就是FileVar类型的实例
        elif isinstance(value, FileVar):
            # 转换为字典形式并返回
            return value.to_dict()

        # 如果不符合上述任何条件，则返回None
        return None
