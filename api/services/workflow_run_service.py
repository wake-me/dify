from extensions.ext_database import db
from libs.infinite_scroll_pagination import InfiniteScrollPagination
from models.model import App
from models.workflow import (
    WorkflowNodeExecution,
    WorkflowNodeExecutionTriggeredFrom,
    WorkflowRun,
    WorkflowRunTriggeredFrom,
)


class WorkflowRunService:
    def get_paginate_advanced_chat_workflow_runs(self, app_model: App, args: dict) -> InfiniteScrollPagination:
        """
        获取高级聊天应用的工作流运行列表
        仅返回 triggered_from 字段等于 advanced_chat 的工作流运行记录

        :param app_model: 应用模型，用于指定获取哪个应用的工作流运行记录
        :param args: 请求参数，可用于过滤和分页等操作
        :return: 返回一个 InfiniteScrollPagination 对象，包含分页后的工作流运行记录列表
        """
        # 定义一个内部类，用于封装工作流运行记录和相关消息信息
        class WorkflowWithMessage:
            message_id: str  # 消息ID
            conversation_id: str  # 聊天会话ID

            def __init__(self, workflow_run: WorkflowRun):
                self._workflow_run = workflow_run  # 工作流运行记录

            def __getattr__(self, item):
                # 通过工作流运行记录对象获取属性值
                return getattr(self._workflow_run, item)

        # 调用通用的工作流运行记录分页获取方法
        pagination = self.get_paginate_workflow_runs(app_model, args)

        # 初始化一个列表，用于存储带有消息信息的工作流运行记录
        with_message_workflow_runs = []
        for workflow_run in pagination.data:
            message = workflow_run.message  # 尝试获取与工作流运行记录相关联的消息
            with_message_workflow_run = WorkflowWithMessage(
                workflow_run=workflow_run
            )
            if message:
                # 如果存在相关消息，则设置工作流运行记录的消息ID和会话ID
                with_message_workflow_run.message_id = message.id
                with_message_workflow_run.conversation_id = message.conversation_id

            with_message_workflow_runs.append(with_message_workflow_run)  # 将带有消息信息的工作流运行记录添加到列表

        # 更新分页对象的数据为带有消息信息的工作流运行记录列表
        pagination.data = with_message_workflow_runs
        return pagination  # 返回更新后的分页对象

    def get_paginate_workflow_runs(self, app_model: App, args: dict) -> InfiniteScrollPagination:
        """
        获取调试工作流运行列表
        仅返回 triggered_from 字段为 debugging 的工作流运行记录

        :param app_model: 应用模型，用于指定查询的应用
        :param args: 请求参数，包含分页和筛选条件
        :return: 返回一个包含工作流运行数据的 InfiniteScrollPagination 对象
        """
        # 解析请求中的限制条数，默认为20
        limit = int(args.get('limit', 20))

        # 构建基础查询，筛选出特定应用和租户ID，以及触发方式为调试的工作流运行记录
        base_query = db.session.query(WorkflowRun).filter(
            WorkflowRun.tenant_id == app_model.tenant_id,
            WorkflowRun.app_id == app_model.id,
            WorkflowRun.triggered_from == WorkflowRunTriggeredFrom.DEBUGGING.value
        )

        # 如果请求中包含 last_id 参数，则进一步筛选出之后的工作流运行记录
        if args.get('last_id'):
            last_workflow_run = base_query.filter(
                WorkflowRun.id == args.get('last_id'),
            ).first()

            # 如果找不到指定的 last_workflow_run，则抛出异常
            if not last_workflow_run:
                raise ValueError('Last workflow run not exists')

            # 筛选创建时间早于 last_workflow_run 且 ID 不同的工作流运行记录，按创建时间降序排列，并限制条数
            workflow_runs = base_query.filter(
                WorkflowRun.created_at < last_workflow_run.created_at,
                WorkflowRun.id != last_workflow_run.id
            ).order_by(WorkflowRun.created_at.desc()).limit(limit).all()
        else:
            # 若无 last_id 参数，则直接按创建时间降序排列并限制条数
            workflow_runs = base_query.order_by(WorkflowRun.created_at.desc()).limit(limit).all()

        # 判断是否还有更多记录
        has_more = False
        if len(workflow_runs) == limit:
            current_page_first_workflow_run = workflow_runs[-1]
            # 计算创建时间早于当前页第一条记录且 ID 不同的工作流运行记录总数
            rest_count = base_query.filter(
                WorkflowRun.created_at < current_page_first_workflow_run.created_at,
                WorkflowRun.id != current_page_first_workflow_run.id
            ).count()

            # 如果还有更多记录，则 has_more 设为 True
            if rest_count > 0:
                has_more = True

        # 返回分页结果
        return InfiniteScrollPagination(
            data=workflow_runs,
            limit=limit,
            has_more=has_more
        )

    def get_workflow_run(self, app_model: App, run_id: str) -> WorkflowRun:
        """
        获取工作流运行的详细信息
        
        :param app_model: 应用模型，包含应用的相关信息
        :param run_id: 工作流运行的唯一标识符
        :return: 返回指定工作流运行的详细信息对象
        """
        # 根据提供的应用模型、运行ID查询工作流运行信息
        workflow_run = db.session.query(WorkflowRun).filter(
            WorkflowRun.tenant_id == app_model.tenant_id,
            WorkflowRun.app_id == app_model.id,
            WorkflowRun.id == run_id,
        ).first()

        return workflow_run

    def get_workflow_run_node_executions(self, app_model: App, run_id: str) -> list[WorkflowNodeExecution]:
        """
        获取工作流运行的节点执行列表
        
        :param app_model: 应用模型，包含应用的相关信息
        :param run_id: 工作流运行的唯一标识符
        :return: 返回一个列表，包含指定工作流运行下的所有节点执行信息
        """
        # 首先获取对应的工作流运行信息
        workflow_run = self.get_workflow_run(app_model, run_id)

        # 如果找不到对应的工作流运行，则直接返回空列表
        if not workflow_run:
            return []

        # 查询并返回该工作流运行下的所有节点执行信息，按节点索引降序排列
        node_executions = db.session.query(WorkflowNodeExecution).filter(
            WorkflowNodeExecution.tenant_id == app_model.tenant_id,
            WorkflowNodeExecution.app_id == app_model.id,
            WorkflowNodeExecution.workflow_id == workflow_run.workflow_id,
            WorkflowNodeExecution.triggered_from == WorkflowNodeExecutionTriggeredFrom.WORKFLOW_RUN.value,
            WorkflowNodeExecution.workflow_run_id == run_id,
        ).order_by(WorkflowNodeExecution.index.desc()).all()

        return node_executions
