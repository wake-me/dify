import uuid

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
        query = db.select(WorkflowAppLog).where(
            WorkflowAppLog.tenant_id == app_model.tenant_id, WorkflowAppLog.app_id == app_model.id
        )

        status = WorkflowRunStatus.value_of(args.get("status")) if args.get("status") else None
        keyword = args["keyword"]
        if keyword or status:
            query = query.join(WorkflowRun, WorkflowRun.id == WorkflowAppLog.workflow_run_id)

        if keyword:
            keyword_like_val = f"%{args['keyword'][:30]}%"
            keyword_conditions = [
                WorkflowRun.inputs.ilike(keyword_like_val),
                WorkflowRun.outputs.ilike(keyword_like_val),
                # filter keyword by end user session id if created by end user role
                and_(WorkflowRun.created_by_role == "end_user", EndUser.session_id.ilike(keyword_like_val)),
            ]

            # filter keyword by workflow run id
            keyword_uuid = self._safe_parse_uuid(keyword)
            if keyword_uuid:
                keyword_conditions.append(WorkflowRun.id == keyword_uuid)

            query = query.outerjoin(
                EndUser,
                and_(WorkflowRun.created_by == EndUser.id, WorkflowRun.created_by_role == CreatedByRole.END_USER.value),
            ).filter(or_(*keyword_conditions))

        # 如果有状态条件，根据工作流运行的状态进行筛选
        if status:
            # join with workflow_run and filter by status
            query = query.filter(WorkflowRun.status == status.value)

        # 按日志创建时间倒序排列
        query = query.order_by(WorkflowAppLog.created_at.desc())

        pagination = db.paginate(query, page=args["page"], per_page=args["limit"], error_out=False)

        return pagination

    @staticmethod
    def _safe_parse_uuid(value: str):
        # fast check
        if len(value) < 32:
            return None

        try:
            return uuid.UUID(value)
        except ValueError:
            return None
