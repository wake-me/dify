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
from core.workflow.entities.node_entities import SystemVariable
from core.workflow.nodes.base_node import UserFrom
from core.workflow.workflow_engine_manager import WorkflowEngineManager
from extensions.ext_database import db
from models.model import App
from models.workflow import Workflow

logger = logging.getLogger(__name__)


class WorkflowAppRunner:
    """
    Workflow Application Runner
    """

    def run(self, application_generate_entity: WorkflowAppGenerateEntity,
            queue_manager: AppQueueManager) -> None:
        """
        运行应用程序
        :param application_generate_entity: 应用生成实体，包含应用配置和输入等信息
        :param queue_manager: 应用队列管理器，用于管理任务队列
        :return: 无返回值
        """
        # 获取并转换应用配置
        app_config = application_generate_entity.app_config
        app_config = cast(WorkflowAppConfig, app_config)

        # 从数据库查询应用记录
        app_record = db.session.query(App).filter(App.id == app_config.app_id).first()
        if not app_record:
            raise ValueError("App not found")  # 如果应用记录不存在，则抛出异常

        # 获取工作流实例
        workflow = self.get_workflow(app_model=app_record, workflow_id=app_config.workflow_id)
        if not workflow:
            raise ValueError("Workflow not initialized")  # 如果工作流未初始化，则抛出异常

        # 准备工作流输入参数和文件
        inputs = application_generate_entity.inputs
        files = application_generate_entity.files

        # 关闭数据库会话
        db.session.close()

        # 设置工作流回调，用于处理工作流事件
        workflow_callbacks = [WorkflowEventTriggerCallback(
            queue_manager=queue_manager,
            workflow=workflow
        )]
        
        # 如果处于调试模式，添加日志回调
        if bool(os.environ.get("DEBUG", 'False').lower() == 'true'):
            workflow_callbacks.append(WorkflowLoggingCallback())

        # 执行工作流
        workflow_engine_manager = WorkflowEngineManager()
        workflow_engine_manager.run_workflow(
            workflow=workflow,
            user_id=application_generate_entity.user_id,
            user_from=UserFrom.ACCOUNT
            if application_generate_entity.invoke_from in [InvokeFrom.EXPLORE, InvokeFrom.DEBUGGER]
            else UserFrom.END_USER,
            user_inputs=inputs,
            system_inputs={
                SystemVariable.FILES: files
            },
            callbacks=workflow_callbacks
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
        
        # 根据 workflow_id 从数据库中查询工作流
        workflow = db.session.query(Workflow).filter(
            Workflow.tenant_id == app_model.tenant_id,  # 租户ID匹配
            Workflow.app_id == app_model.id,  # 应用ID匹配
            Workflow.id == workflow_id  # 工作流ID匹配
        ).first()
        
        # 返回查询到的工作流
        return workflow
