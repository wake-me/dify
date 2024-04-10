from flask_sqlalchemy.pagination import Pagination
from sqlalchemy import and_, or_

from extensions.ext_database import db
from models import CreatedByRole
from models.model import App, EndUser
from models.workflow import WorkflowAppLog, WorkflowRun, WorkflowRunStatus


class WorkflowAppService:
    
    def get_paginate_workflow_app_logs(self, app_model: App, args: dict) -> Pagination:
        """
        获取分页工作流应用日志
        :param app_model: 应用模型，用于指定查询的日志所属应用
        :param args: 请求参数，包含日志状态、关键字、页码和每页数量等信息
        :return: 分页对象，包含当前页日志信息和分页导航参数
        """
        # 构建基础查询语句，筛选出指定应用和租户的日志
        query = (
            db.select(WorkflowAppLog)
            .where(
                WorkflowAppLog.tenant_id == app_model.tenant_id,
                WorkflowAppLog.app_id == app_model.id
            )
        )

        # 根据请求参数中的状态值构建查询条件
        status = WorkflowRunStatus.value_of(args.get('status')) if args.get('status') else None
        # 如果有关键字或状态条件，则需关联查询工作流运行信息
        if args['keyword'] or status:
            query = query.join(
                WorkflowRun, WorkflowRun.id == WorkflowAppLog.workflow_run_id
            )

        # 如果有关键字条件，构建关键字查询条件，并进行模糊匹配
        if args['keyword']:
            keyword_val = f"%{args['keyword'][:30]}%"
            keyword_conditions = [
                WorkflowRun.inputs.ilike(keyword_val),
                WorkflowRun.outputs.ilike(keyword_val),
                # 如果日志是由终端用户创建的，通过终端用户会话ID筛选
                and_(WorkflowRun.created_by_role == 'end_user', EndUser.session_id.ilike(keyword_val))
            ]

            # 关联终端用户信息，以便根据终端用户会话ID进行筛选
            query = query.outerjoin(
                EndUser,
                and_(WorkflowRun.created_by == EndUser.id, WorkflowRun.created_by_role == CreatedByRole.END_USER.value)
            ).filter(or_(*keyword_conditions))

        # 如果有状态条件，根据工作流运行的状态进行筛选
        if status:
            query = query.filter(
                WorkflowRun.status == status.value
            )

        # 按日志创建时间倒序排列
        query = query.order_by(WorkflowAppLog.created_at.desc())

        # 执行分页查询
        pagination = db.paginate(
            query,
            page=args['page'],
            per_page=args['limit'],
            error_out=False
        )

        return pagination