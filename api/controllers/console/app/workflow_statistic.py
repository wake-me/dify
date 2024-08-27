from datetime import datetime
from decimal import Decimal

import pytz
from flask import jsonify
from flask_login import current_user
from flask_restful import Resource, reqparse

from controllers.console import api
from controllers.console.app.wraps import get_app_model
from controllers.console.setup import setup_required
from controllers.console.wraps import account_initialization_required
from extensions.ext_database import db
from libs.helper import datetime_string
from libs.login import login_required
from models.model import AppMode
from models.workflow import WorkflowRunTriggeredFrom


class WorkflowDailyRunsStatistic(Resource):
    """
    提供每日工作流运行统计信息的资源类。
    
    要求用户登录、账户初始化且应用模型已设置。提供通过日期范围查询指定应用的工作流运行次数的功能。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model
    def get(self, app_model):
        """
        查询并返回指定应用的每日工作流运行统计信息。
        
        :param app_model: 应用模型实例，用于确定要查询的工作流所属的应用。
        :return: 包含每日工作流运行次数的统计信息的JSON响应。
        """
        account = current_user  # 当前登录的用户

        # 解析请求参数：开始和结束日期
        parser = reqparse.RequestParser()
        parser.add_argument("start", type=datetime_string("%Y-%m-%d %H:%M"), location="args")
        parser.add_argument("end", type=datetime_string("%Y-%m-%d %H:%M"), location="args")
        args = parser.parse_args()

        sql_query = """
        SELECT date(DATE_TRUNC('day', created_at AT TIME ZONE 'UTC' AT TIME ZONE :tz )) AS date, count(id) AS runs
            FROM workflow_runs 
            WHERE app_id = :app_id 
                AND triggered_from = :triggered_from
        """
        arg_dict = {
            "tz": account.timezone,
            "app_id": app_model.id,
            "triggered_from": WorkflowRunTriggeredFrom.APP_RUN.value,
        }

        # 处理时区转换
        timezone = pytz.timezone(account.timezone)
        utc_timezone = pytz.utc

        if args["start"]:
            start_datetime = datetime.strptime(args["start"], "%Y-%m-%d %H:%M")
            start_datetime = start_datetime.replace(second=0)

            start_datetime_timezone = timezone.localize(start_datetime)
            start_datetime_utc = start_datetime_timezone.astimezone(utc_timezone)

            sql_query += " and created_at >= :start"
            arg_dict["start"] = start_datetime_utc

        if args["end"]:
            end_datetime = datetime.strptime(args["end"], "%Y-%m-%d %H:%M")
            end_datetime = end_datetime.replace(second=0)

            end_datetime_timezone = timezone.localize(end_datetime)
            end_datetime_utc = end_datetime_timezone.astimezone(utc_timezone)

            sql_query += " and created_at < :end"
            arg_dict["end"] = end_datetime_utc

        sql_query += " GROUP BY date order by date"

        # 执行查询并将结果格式化为响应数据
        response_data = []

        with db.engine.begin() as conn:
            rs = conn.execute(db.text(sql_query), arg_dict)
            for i in rs:
                response_data.append({"date": str(i.date), "runs": i.runs})

        return jsonify({"data": response_data})


class WorkflowDailyTerminalsStatistic(Resource):
    """
    日常工作流终端统计信息资源类。

    该类提供了通过API获取日常工作流终端统计信息的功能。
    需要用户登录、账户初始化、应用模型选定以及设置。
    """

    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model
    def get(self, app_model):
        """
        获取指定应用模型的日常工作流终端统计信息。

        参数:
        - app_model: 应用模型对象，用于确定统计信息的应用范围。

        返回值:
        - 统计信息的JSON响应，包含每日的终端数量。
        """

        # 当前登录的用户账户
        account = current_user

        # 解析请求参数：开始和结束时间
        parser = reqparse.RequestParser()
        parser.add_argument("start", type=datetime_string("%Y-%m-%d %H:%M"), location="args")
        parser.add_argument("end", type=datetime_string("%Y-%m-%d %H:%M"), location="args")
        args = parser.parse_args()

        sql_query = """
                SELECT date(DATE_TRUNC('day', created_at AT TIME ZONE 'UTC' AT TIME ZONE :tz )) AS date, count(distinct workflow_runs.created_by) AS terminal_count
                    FROM workflow_runs 
                    WHERE app_id = :app_id 
                        AND triggered_from = :triggered_from
                """
        arg_dict = {
            "tz": account.timezone,
            "app_id": app_model.id,
            "triggered_from": WorkflowRunTriggeredFrom.APP_RUN.value,
        }

        # 处理时区转换
        timezone = pytz.timezone(account.timezone)
        utc_timezone = pytz.utc

        if args["start"]:
            start_datetime = datetime.strptime(args["start"], "%Y-%m-%d %H:%M")
            start_datetime = start_datetime.replace(second=0)

            start_datetime_timezone = timezone.localize(start_datetime)
            start_datetime_utc = start_datetime_timezone.astimezone(utc_timezone)

            sql_query += " and created_at >= :start"
            arg_dict["start"] = start_datetime_utc

        if args["end"]:
            end_datetime = datetime.strptime(args["end"], "%Y-%m-%d %H:%M")
            end_datetime = end_datetime.replace(second=0)

            end_datetime_timezone = timezone.localize(end_datetime)
            end_datetime_utc = end_datetime_timezone.astimezone(utc_timezone)

            sql_query += " and created_at < :end"
            arg_dict["end"] = end_datetime_utc

        sql_query += " GROUP BY date order by date"

        response_data = []

        with db.engine.begin() as conn:
            rs = conn.execute(db.text(sql_query), arg_dict)
            for i in rs:
                response_data.append({"date": str(i.date), "terminal_count": i.terminal_count})

        return jsonify({"data": response_data})


class WorkflowDailyTokenCostStatistic(Resource):
    """
    日工作流令牌消耗统计资源类，提供获取指定应用的日工作流令牌消耗统计数据。

    方法:
    - get: 获取指定应用的日工作流令牌消耗统计数据。
    """

    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model
    def get(self, app_model):
        """
        获取指定应用的日工作流令牌消耗统计数据。

        参数:
        - app_model: 应用模型实例，代表当前请求的应用。

        返回值:
        - 包含日工作流令牌消耗统计数据的JSON响应。
        """
        account = current_user  # 当前用户账号

        # 解析请求参数：开始和结束时间
        parser = reqparse.RequestParser()
        parser.add_argument("start", type=datetime_string("%Y-%m-%d %H:%M"), location="args")
        parser.add_argument("end", type=datetime_string("%Y-%m-%d %H:%M"), location="args")
        args = parser.parse_args()

        sql_query = """
                SELECT 
                    date(DATE_TRUNC('day', created_at AT TIME ZONE 'UTC' AT TIME ZONE :tz )) AS date, 
                    SUM(workflow_runs.total_tokens) as token_count
                FROM workflow_runs 
                WHERE app_id = :app_id 
                    AND triggered_from = :triggered_from
                """
        arg_dict = {
            "tz": account.timezone,
            "app_id": app_model.id,
            "triggered_from": WorkflowRunTriggeredFrom.APP_RUN.value,
        }

        # 处理时区转换
        timezone = pytz.timezone(account.timezone)
        utc_timezone = pytz.utc

        if args["start"]:
            start_datetime = datetime.strptime(args["start"], "%Y-%m-%d %H:%M")
            start_datetime = start_datetime.replace(second=0)

            start_datetime_timezone = timezone.localize(start_datetime)
            start_datetime_utc = start_datetime_timezone.astimezone(utc_timezone)

            sql_query += " and created_at >= :start"
            arg_dict["start"] = start_datetime_utc

        if args["end"]:
            end_datetime = datetime.strptime(args["end"], "%Y-%m-%d %H:%M")
            end_datetime = end_datetime.replace(second=0)

            end_datetime_timezone = timezone.localize(end_datetime)
            end_datetime_utc = end_datetime_timezone.astimezone(utc_timezone)

            sql_query += " and created_at < :end"
            arg_dict["end"] = end_datetime_utc

        sql_query += " GROUP BY date order by date"

        response_data = []

        with db.engine.begin() as conn:
            rs = conn.execute(db.text(sql_query), arg_dict)
            for i in rs:
                response_data.append(
                    {
                        "date": str(i.date),
                        "token_count": i.token_count,
                    }
                )

        return jsonify({"data": response_data})


class WorkflowAverageAppInteractionStatistic(Resource):
    """
    工作流平均应用交互统计

    资源类，用于提供工作流应用交互的平均统计信息。
    需要用户登录、账户初始化并且应用必须处于工作流模式。
    """

    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.WORKFLOW])
    def get(self, app_model):
        """
        获取指定应用的工作流平均交互统计数据

        参数:
        - app_model: 应用模型对象，用于确定要获取数据的应用。

        返回值:
        - 包含平均交互统计数据的JSON响应。
        """

        # 当前登录的用户
        account = current_user

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument("start", type=datetime_string("%Y-%m-%d %H:%M"), location="args")
        parser.add_argument("end", type=datetime_string("%Y-%m-%d %H:%M"), location="args")
        args = parser.parse_args()

        # 构造SQL查询语句
        sql_query = """
            SELECT 
                AVG(sub.interactions) as interactions,
                sub.date
            FROM
                (SELECT 
                    date(DATE_TRUNC('day', c.created_at AT TIME ZONE 'UTC' AT TIME ZONE :tz )) AS date, 
                    c.created_by,
                    COUNT(c.id) AS interactions
                FROM workflow_runs c
                WHERE c.app_id = :app_id
                    AND c.triggered_from = :triggered_from
                    {{start}}
                    {{end}}
                GROUP BY date, c.created_by) sub
            GROUP BY sub.date
            """
        arg_dict = {
            "tz": account.timezone,
            "app_id": app_model.id,
            "triggered_from": WorkflowRunTriggeredFrom.APP_RUN.value,
        }

        # 处理时区
        timezone = pytz.timezone(account.timezone)
        utc_timezone = pytz.utc

        if args["start"]:
            start_datetime = datetime.strptime(args["start"], "%Y-%m-%d %H:%M")
            start_datetime = start_datetime.replace(second=0)

            start_datetime_timezone = timezone.localize(start_datetime)
            start_datetime_utc = start_datetime_timezone.astimezone(utc_timezone)

            sql_query = sql_query.replace("{{start}}", " AND c.created_at >= :start")
            arg_dict["start"] = start_datetime_utc
        else:
            sql_query = sql_query.replace("{{start}}", "")

        if args["end"]:
            end_datetime = datetime.strptime(args["end"], "%Y-%m-%d %H:%M")
            end_datetime = end_datetime.replace(second=0)

            end_datetime_timezone = timezone.localize(end_datetime)
            end_datetime_utc = end_datetime_timezone.astimezone(utc_timezone)

            sql_query = sql_query.replace("{{end}}", " and c.created_at < :end")
            arg_dict["end"] = end_datetime_utc
        else:
            sql_query = sql_query.replace("{{end}}", "")

        # 执行查询并构造响应数据
        response_data = []

        with db.engine.begin() as conn:
            rs = conn.execute(db.text(sql_query), arg_dict)
            for i in rs:
                response_data.append(
                    {"date": str(i.date), "interactions": float(i.interactions.quantize(Decimal("0.01")))}
                )

        return jsonify({"data": response_data})


api.add_resource(WorkflowDailyRunsStatistic, "/apps/<uuid:app_id>/workflow/statistics/daily-conversations")
api.add_resource(WorkflowDailyTerminalsStatistic, "/apps/<uuid:app_id>/workflow/statistics/daily-terminals")
api.add_resource(WorkflowDailyTokenCostStatistic, "/apps/<uuid:app_id>/workflow/statistics/token-costs")
api.add_resource(
    WorkflowAverageAppInteractionStatistic, "/apps/<uuid:app_id>/workflow/statistics/average-app-interactions"
)
