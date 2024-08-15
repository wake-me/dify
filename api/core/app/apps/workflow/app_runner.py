import logging
import os
from typing import Optional, cast

from core.app.apps.base_app_queue_manager import AppQueueManager
from core.app.apps.workflow.app_config_manager import WorkflowAppConfig
from core.app.apps.workflow.workflow_event_trigger_callback import WorkflowEventTriggerCallback
from core.app.apps.workflow_logging_callback import WorkflowLoggingCallback
from core.app.entities.app_invoke_entities import (
    InvokeFrom,
    WorkflowAppGenerateEntity,
)
from core.workflow.callbacks.base_workflow_callback import WorkflowCallback
from core.workflow.entities.variable_pool import VariablePool
from core.workflow.enums import SystemVariable
from core.workflow.nodes.base_node import UserFrom
from core.workflow.workflow_engine_manager import WorkflowEngineManager
from extensions.ext_database import db
from models.model import App, EndUser
from models.workflow import Workflow

logger = logging.getLogger(__name__)


class WorkflowAppRunner:
    """
    Workflow Application Runner
    """

    def run(self, application_generate_entity: WorkflowAppGenerateEntity, queue_manager: AppQueueManager) -> None:
        """
        运行应用程序
        :param application_generate_entity: 应用生成实体，包含应用配置和输入等信息
        :param queue_manager: 应用队列管理器，用于管理任务队列
        :return: 无返回值
        """
        # 获取并转换应用配置
        app_config = application_generate_entity.app_config
        app_config = cast(WorkflowAppConfig, app_config)

        user_id = None
        if application_generate_entity.invoke_from in [InvokeFrom.WEB_APP, InvokeFrom.SERVICE_API]:
            end_user = db.session.query(EndUser).filter(EndUser.id == application_generate_entity.user_id).first()
            if end_user:
                user_id = end_user.session_id
        else:
            user_id = application_generate_entity.user_id

        app_record = db.session.query(App).filter(App.id == app_config.app_id).first()
        if not app_record:
            raise ValueError('App not found')

        # 获取工作流实例
        workflow = self.get_workflow(app_model=app_record, workflow_id=app_config.workflow_id)
        if not workflow:
            raise ValueError('Workflow not initialized')

        # 准备工作流输入参数和文件
        inputs = application_generate_entity.inputs
        files = application_generate_entity.files

        # 关闭数据库会话
        db.session.close()

        workflow_callbacks: list[WorkflowCallback] = [
            WorkflowEventTriggerCallback(queue_manager=queue_manager, workflow=workflow)
        ]

        if bool(os.environ.get('DEBUG', 'False').lower() == 'true'):
            workflow_callbacks.append(WorkflowLoggingCallback())

        # Create a variable pool.
        system_inputs = {
            SystemVariable.FILES: files,
            SystemVariable.USER_ID: user_id,
        }
        variable_pool = VariablePool(
            system_variables=system_inputs,
            user_inputs=inputs,
            environment_variables=workflow.environment_variables,
            conversation_variables=[],
        )

        # RUN WORKFLOW
        workflow_engine_manager = WorkflowEngineManager()
        workflow_engine_manager.run_workflow(
            workflow=workflow,
            user_id=application_generate_entity.user_id,
            user_from=UserFrom.ACCOUNT
            if application_generate_entity.invoke_from in [InvokeFrom.EXPLORE, InvokeFrom.DEBUGGER]
            else UserFrom.END_USER,
            invoke_from=application_generate_entity.invoke_from,
            callbacks=workflow_callbacks,
            call_depth=application_generate_entity.call_depth,
            variable_pool=variable_pool,
        )

    def single_iteration_run(
        self, app_id: str, workflow_id: str, queue_manager: AppQueueManager, inputs: dict, node_id: str, user_id: str
    ) -> None:
        """
        Single iteration run
        """
        app_record = db.session.query(App).filter(App.id == app_id).first()
        if not app_record:
            raise ValueError('App not found')

        if not app_record.workflow_id:
            raise ValueError('Workflow not initialized')

        workflow = self.get_workflow(app_model=app_record, workflow_id=workflow_id)
        if not workflow:
            raise ValueError('Workflow not initialized')

        workflow_callbacks = [WorkflowEventTriggerCallback(queue_manager=queue_manager, workflow=workflow)]

        workflow_engine_manager = WorkflowEngineManager()
        workflow_engine_manager.single_step_run_iteration_workflow_node(
            workflow=workflow, node_id=node_id, user_id=user_id, user_inputs=inputs, callbacks=workflow_callbacks
        )

    def get_workflow(self, app_model: App, workflow_id: str) -> Optional[Workflow]:
        """
        获取工作流
        
        参数:
        - app_model: App 类型，代表一个应用程序模型
        - workflow_id: 字符串类型，指定的工作流ID
        
        返回值:
        - Workflow 类型或 None，如果找到指定的工作流则返回Workflow对象，否则返回None
        """
        # fetch workflow by workflow_id
        workflow = (
            db.session.query(Workflow)
            .filter(
                Workflow.tenant_id == app_model.tenant_id, Workflow.app_id == app_model.id, Workflow.id == workflow_id
            )
            .first()
        )

        # return workflow
        return workflow
