from flask_restful import Resource, marshal_with, reqparse
from flask_restful.inputs import int_range

from controllers.console import api
from controllers.console.app.wraps import get_app_model
from controllers.console.setup import setup_required
from controllers.console.wraps import account_initialization_required
from fields.workflow_run_fields import (
    advanced_chat_workflow_run_pagination_fields,
    workflow_run_detail_fields,
    workflow_run_node_execution_list_fields,
    workflow_run_pagination_fields,
)
from libs.helper import uuid_value
from libs.login import login_required
from models.model import App, AppMode
from services.workflow_run_service import WorkflowRunService


class AdvancedChatAppWorkflowRunListApi(Resource):
    # 该类用于处理高级聊天应用工作流运行列表的API请求
    
    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.ADVANCED_CHAT])
    @marshal_with(advanced_chat_workflow_run_pagination_fields)
    def get(self, app_model: App):
        """
        获取高级聊天应用的工作流运行列表
        
        :param app_model: App模型实例，代表当前被操作的应用
        :return: 返回工作流运行的分页结果
        """
        # 初始化请求解析器，用于解析GET请求中的参数
        parser = reqparse.RequestParser()
        parser.add_argument("last_id", type=uuid_value, location="args")
        parser.add_argument("limit", type=int_range(1, 100), required=False, default=20, location="args")
        args = parser.parse_args()

        # 使用工作流运行服务来获取分页后的高级聊天工作流运行列表
        workflow_run_service = WorkflowRunService()
        result = workflow_run_service.get_paginate_advanced_chat_workflow_runs(app_model=app_model, args=args)

        return result  # 返回获取到的结果


class WorkflowRunListApi(Resource):
    # 此类用于处理工作流运行列表的API请求
    
    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.ADVANCED_CHAT, AppMode.WORKFLOW])
    @marshal_with(workflow_run_pagination_fields)
    def get(self, app_model: App):
        """
        获取工作流运行列表
        
        参数:
        - app_model: App模型，指定应用的实例
        
        返回值:
        - 返回工作流运行的分页结果
        """
        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument("last_id", type=uuid_value, location="args")
        parser.add_argument("limit", type=int_range(1, 100), required=False, default=20, location="args")
        args = parser.parse_args()

        # 使用工作流运行服务获取分页后的运行列表
        workflow_run_service = WorkflowRunService()
        result = workflow_run_service.get_paginate_workflow_runs(app_model=app_model, args=args)

        return result  # 返回获取到的工作流运行列表分页结果


class WorkflowRunDetailApi(Resource):
    # 此类用于处理工作流运行详情的API请求
    
    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.ADVANCED_CHAT, AppMode.WORKFLOW])
    @marshal_with(workflow_run_detail_fields)
    def get(self, app_model: App, run_id):
        """
        获取工作流运行的详细信息
        
        :param app_model: 应用模型，指定了应用的模式（高级聊天或工作流）
        :type app_model: App
        :param run_id: 工作流运行的唯一标识符
        :type run_id: str
        :return: 返回工作流运行的详细信息
        :rtype: WorkflowRun
        """
        run_id = str(run_id)  # 确保run_id为字符串格式

        # 初始化工作流运行服务
        workflow_run_service = WorkflowRunService()
        # 根据应用模型和运行ID获取工作流运行详情
        workflow_run = workflow_run_service.get_workflow_run(app_model=app_model, run_id=run_id)

        return workflow_run  # 返回工作流运行详情


class WorkflowRunNodeExecutionListApi(Resource):
    # 该类用于处理工作流运行节点执行列表的API请求
    
    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.ADVANCED_CHAT, AppMode.WORKFLOW])
    @marshal_with(workflow_run_node_execution_list_fields)
    def get(self, app_model: App, run_id):
        """
        获取工作流运行节点执行列表
        
        :param app_model: 应用模型，指定应用的模式（高级聊天或工作流）
        :type app_model: App
        :param run_id: 工作流运行的ID
        :type run_id: int
        :return: 返回工作流运行节点执行的列表数据
        :rtype: dict
        """
        run_id = str(run_id)  # 将run_id转换为字符串
        
        # 使用工作流运行服务获取工作流运行节点执行的信息
        workflow_run_service = WorkflowRunService()
        node_executions = workflow_run_service.get_workflow_run_node_executions(app_model=app_model, run_id=run_id)

        return {"data": node_executions}


api.add_resource(AdvancedChatAppWorkflowRunListApi, "/apps/<uuid:app_id>/advanced-chat/workflow-runs")
api.add_resource(WorkflowRunListApi, "/apps/<uuid:app_id>/workflow-runs")
api.add_resource(WorkflowRunDetailApi, "/apps/<uuid:app_id>/workflow-runs/<uuid:run_id>")
api.add_resource(WorkflowRunNodeExecutionListApi, "/apps/<uuid:app_id>/workflow-runs/<uuid:run_id>/node-executions")
