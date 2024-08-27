import json
import time
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Optional

from core.app.apps.advanced_chat.app_config_manager import AdvancedChatAppConfigManager
from core.app.apps.workflow.app_config_manager import WorkflowAppConfigManager
from core.app.segments import Variable
from core.model_runtime.utils.encoders import jsonable_encoder
from core.workflow.entities.node_entities import NodeType
from core.workflow.errors import WorkflowNodeRunFailedError
from core.workflow.workflow_engine_manager import WorkflowEngineManager
from events.app_event import app_draft_workflow_was_synced, app_published_workflow_was_updated
from extensions.ext_database import db
from models.account import Account
from models.model import App, AppMode
from models.workflow import (
    CreatedByRole,
    Workflow,
    WorkflowNodeExecution,
    WorkflowNodeExecutionStatus,
    WorkflowNodeExecutionTriggeredFrom,
    WorkflowType,
)
from services.errors.app import WorkflowHashNotEqualError
from services.workflow.workflow_converter import WorkflowConverter


class WorkflowService:
    """
    Workflow Service
    """

    def get_draft_workflow(self, app_model: App) -> Optional[Workflow]:
        """
        获取草稿工作流
        
        参数:
        app_model - App模型对象，用于查询对应的工作流草稿版本。
        
        返回值:
        Workflow的Optional类型，如果找到对应草稿工作流则返回Workflow对象，否则返回None。
        """
        # fetch draft workflow by app_model
        workflow = (
            db.session.query(Workflow)
            .filter(
                Workflow.tenant_id == app_model.tenant_id, Workflow.app_id == app_model.id, Workflow.version == "draft"
            )
            .first()
        )

        # 返回查询到的草稿工作流
        return workflow

    def get_published_workflow(self, app_model: App) -> Optional[Workflow]:
        """
        获取发布的 workflow

        参数:
        app_model: App - 应用模型对象，包含应用的相关信息，例如 workflow_id。

        返回值:
        Optional[Workflow] - 如果找到对应的已发布 workflow，则返回 Workflow 对象；如果未找到或 app_model 中没有 workflow_id，则返回 None。
        """

        if not app_model.workflow_id:
            return None  # 如果 app_model 没有 workflow_id，直接返回 None

        # fetch published workflow by workflow_id
        workflow = (
            db.session.query(Workflow)
            .filter(
                Workflow.tenant_id == app_model.tenant_id,
                Workflow.app_id == app_model.id,
                Workflow.id == app_model.workflow_id,
            )
            .first()
        )

        return workflow  # 返回查询结果，可能是 Workflow 对象或 None

    def sync_draft_workflow(
        self,
        *,
        app_model: App,
        graph: dict,
        features: dict,
        unique_hash: Optional[str],
        account: Account,
        environment_variables: Sequence[Variable],
        conversation_variables: Sequence[Variable],
    ) -> Workflow:
        """
        Sync draft workflow
        :raises WorkflowHashNotEqualError
        """
        
        # 根据 app_model 获取草稿工作流
        workflow = self.get_draft_workflow(app_model=app_model)

        if workflow and workflow.unique_hash != unique_hash:
            raise WorkflowHashNotEqualError()

        # validate features structure
        self.validate_features_structure(app_model=app_model, features=features)

        # 如果未找到草稿工作流，则创建新的草稿工作流
        if not workflow:
            workflow = Workflow(
                tenant_id=app_model.tenant_id,
                app_id=app_model.id,
                type=WorkflowType.from_app_mode(app_model.mode).value,
                version="draft",
                graph=json.dumps(graph),
                features=json.dumps(features),
                created_by=account.id,
                environment_variables=environment_variables,
                conversation_variables=conversation_variables,
            )
            db.session.add(workflow)
        # 如果找到草稿工作流，则更新其信息
        else:
            workflow.graph = json.dumps(graph)
            workflow.features = json.dumps(features)
            workflow.updated_by = account.id
            workflow.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            workflow.environment_variables = environment_variables
            workflow.conversation_variables = conversation_variables

        # 提交数据库会话更改
        db.session.commit()

        # trigger app workflow events
        app_draft_workflow_was_synced.send(app_model, synced_draft_workflow=workflow)

        # return draft workflow
        return workflow

    def publish_workflow(self, app_model: App, account: Account, draft_workflow: Optional[Workflow] = None) -> Workflow:
        """
        从草稿发布工作流

        :param app_model: App实例
        :param account: Account实例
        :param draft_workflow: 工作流实例，可选参数，默认为None
        :return: 发布后的工作流实例

        此函数的目的是将草稿工作流发布为正式工作流。它首先检查提供的草稿工作流，
        如果未提供则通过app_model获取草稿工作流。然后，基于提供的草稿工作流信息，
        创建一个新的工作流实例并将其保存到数据库。最后，更新app_model的工作流ID，
        触发相关应用工作流事件，并返回新发布的工作流实例。
        """
        if not draft_workflow:
            # 如果未提供草稿工作流，则尝试根据app_model获取草稿工作流
            draft_workflow = self.get_draft_workflow(app_model=app_model)

        if not draft_workflow:
            raise ValueError("No valid workflow found.")

        # 创建新的工作流实例
        workflow = Workflow(
            tenant_id=app_model.tenant_id,
            app_id=app_model.id,
            type=draft_workflow.type,
            version=str(datetime.now(timezone.utc).replace(tzinfo=None)),
            graph=draft_workflow.graph,
            features=draft_workflow.features,
            created_by=account.id,
            environment_variables=draft_workflow.environment_variables,
            conversation_variables=draft_workflow.conversation_variables,
        )

        # 将新工作流实例添加到数据库并提交更改
        db.session.add(workflow)
        db.session.flush()
        db.session.commit()

        # 更新app_model的工作流ID并提交更改
        app_model.workflow_id = workflow.id
        db.session.commit()

        # 触发应用工作流更新事件
        app_published_workflow_was_updated.send(app_model, published_workflow=workflow)

        # 返回新发布的工作流实例
        return workflow

    def get_default_block_configs(self) -> list[dict]:
        """
        获取默认的区块配置列表
        
        该方法不接受任何参数，并返回一个包含默认区块配置的列表。
        
        返回值:
            list[dict]: 默认区块配置的列表，每个配置以字典形式存储。
        """
        # 创建WorkflowEngineManager实例以获取默认配置
        workflow_engine_manager = WorkflowEngineManager()
        # 返回默认配置列表
        return workflow_engine_manager.get_default_configs()

    def get_default_block_config(self, node_type: str, filters: Optional[dict] = None) -> Optional[dict]:
        """
        获取节点的默认配置。
        :param node_type: 节点类型
        :param filters: 根据节点配置参数进行过滤的条件
        :return: 返回符合条件的节点默认配置，如果找不到则返回None
        """
        # 将字符串类型的节点类型转换为对应的枚举类型
        node_type = NodeType.value_of(node_type)

        # 通过工作流引擎管理器获取默认配置
        workflow_engine_manager = WorkflowEngineManager()
        return workflow_engine_manager.get_default_config(node_type, filters)

    def run_draft_workflow_node(
        self, app_model: App, node_id: str, user_inputs: dict, account: Account
    ) -> WorkflowNodeExecution:
        """
        Run draft workflow node
        """
        # 根据应用模型获取草稿工作流
        draft_workflow = self.get_draft_workflow(app_model=app_model)
        if not draft_workflow:
            raise ValueError("Workflow not initialized")

        # 初始化工作流引擎管理器并开始执行节点
        workflow_engine_manager = WorkflowEngineManager()
        start_at = time.perf_counter()

        try:
            # 执行单个步骤的工作流节点
            node_instance, node_run_result = workflow_engine_manager.single_step_run_workflow_node(
                workflow=draft_workflow,
                node_id=node_id,
                user_inputs=user_inputs,
                user_id=account.id,
            )
        except WorkflowNodeRunFailedError as e:
            # 如果节点执行失败，记录失败信息
            workflow_node_execution = WorkflowNodeExecution(
                tenant_id=app_model.tenant_id,
                app_id=app_model.id,
                workflow_id=draft_workflow.id,
                triggered_from=WorkflowNodeExecutionTriggeredFrom.SINGLE_STEP.value,
                index=1,
                node_id=e.node_id,
                node_type=e.node_type.value,
                title=e.node_title,
                status=WorkflowNodeExecutionStatus.FAILED.value,
                error=e.error,
                elapsed_time=time.perf_counter() - start_at,
                created_by_role=CreatedByRole.ACCOUNT.value,
                created_by=account.id,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                finished_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            db.session.add(workflow_node_execution)
            db.session.commit()

            return workflow_node_execution

        # 根据节点执行结果，创建并返回工作流节点执行记录
        if node_run_result.status == WorkflowNodeExecutionStatus.SUCCEEDED:
            workflow_node_execution = WorkflowNodeExecution(
                tenant_id=app_model.tenant_id,
                app_id=app_model.id,
                workflow_id=draft_workflow.id,
                triggered_from=WorkflowNodeExecutionTriggeredFrom.SINGLE_STEP.value,
                index=1,
                node_id=node_id,
                node_type=node_instance.node_type.value,
                title=node_instance.node_data.title,
                inputs=json.dumps(node_run_result.inputs) if node_run_result.inputs else None,
                process_data=json.dumps(node_run_result.process_data) if node_run_result.process_data else None,
                outputs=json.dumps(jsonable_encoder(node_run_result.outputs)) if node_run_result.outputs else None,
                execution_metadata=(
                    json.dumps(jsonable_encoder(node_run_result.metadata)) if node_run_result.metadata else None
                ),
                status=WorkflowNodeExecutionStatus.SUCCEEDED.value,
                elapsed_time=time.perf_counter() - start_at,
                created_by_role=CreatedByRole.ACCOUNT.value,
                created_by=account.id,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                finished_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        else:
            # 如果节点执行未成功，记录失败信息
            workflow_node_execution = WorkflowNodeExecution(
                tenant_id=app_model.tenant_id,
                app_id=app_model.id,
                workflow_id=draft_workflow.id,
                triggered_from=WorkflowNodeExecutionTriggeredFrom.SINGLE_STEP.value,
                index=1,
                node_id=node_id,
                node_type=node_instance.node_type.value,
                title=node_instance.node_data.title,
                status=node_run_result.status.value,
                error=node_run_result.error,
                elapsed_time=time.perf_counter() - start_at,
                created_by_role=CreatedByRole.ACCOUNT.value,
                created_by=account.id,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                finished_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )

        db.session.add(workflow_node_execution)
        db.session.commit()

        return workflow_node_execution

    def convert_to_workflow(self, app_model: App, account: Account, args: dict) -> App:
        """
        将聊天机器人应用（专家模式）转换为工作流应用
        完成从App到Workflow App的转换

        :param app_model: App实例
        :param account: Account实例
        :param args: 包含转换所需参数的字典
        :return: 转换后的工作流应用实例
        """
        # 初始化工作流转换器
        workflow_converter = WorkflowConverter()

        # 检查当前应用模式是否支持转换为工作流
        if app_model.mode not in [AppMode.CHAT.value, AppMode.COMPLETION.value]:
            raise ValueError(f"Current App mode: {app_model.mode} is not supported convert to workflow.")

        # 执行转换操作
        new_app = workflow_converter.convert_to_workflow(
            app_model=app_model,
            account=account,
            name=args.get("name"),
            icon_type=args.get("icon_type"),
            icon=args.get("icon"),
            icon_background=args.get("icon_background"),
        )

        return new_app

    def validate_features_structure(self, app_model: App, features: dict) -> dict:
        """
        根据应用模型(app_model)的模式，验证特性(features)的结构是否合法。
        
        参数:
        - app_model: App 类型，代表一个应用模型，用于确定应用的运行模式。
        - features: dict 类型，代表需要验证结构的特性字典。
        
        返回:
        - 验证结果的字典，包含验证的详细信息。
        
        异常:
        - 如果应用模式无效，将抛出 ValueError。
        """
        if app_model.mode == AppMode.ADVANCED_CHAT.value:
            # 在高级聊天模式下，使用 AdvancedChatAppConfigManager 进行配置验证
            return AdvancedChatAppConfigManager.config_validate(
                tenant_id=app_model.tenant_id, config=features, only_structure_validate=True
            )
        elif app_model.mode == AppMode.WORKFLOW.value:
            # 在工作流模式下，使用 WorkflowAppConfigManager 进行配置验证
            return WorkflowAppConfigManager.config_validate(
                tenant_id=app_model.tenant_id, config=features, only_structure_validate=True
            )
        else:
            # 如果应用模式既不是高级聊天也不是工作流，则认为模式无效，抛出异常
            raise ValueError(f"Invalid app mode: {app_model.mode}")

    @classmethod
    def get_elapsed_time(cls, workflow_run_id: str) -> float:
        """
        Get elapsed time
        """
        elapsed_time = 0.0

        # fetch workflow node execution by workflow_run_id
        workflow_nodes = (
            db.session.query(WorkflowNodeExecution)
            .filter(WorkflowNodeExecution.workflow_run_id == workflow_run_id)
            .order_by(WorkflowNodeExecution.created_at.asc())
            .all()
        )
        if not workflow_nodes:
            return elapsed_time

        for node in workflow_nodes:
            elapsed_time += node.elapsed_time

        return elapsed_time
