from flask_login import current_user
from flask_restful import Resource, reqparse

from controllers.console import api
from controllers.console.setup import setup_required
from controllers.console.wraps import account_initialization_required, only_edition_cloud
from libs.login import login_required
from services.billing_service import BillingService


class Subscription(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @only_edition_cloud
    def get(self):
        parser = reqparse.RequestParser()
        parser.add_argument("plan", type=str, required=True, location="args", choices=["professional", "team"])
        parser.add_argument("interval", type=str, required=True, location="args", choices=["month", "year"])
        args = parser.parse_args()

        # 检查用户是否有权限查看订阅信息
        BillingService.is_tenant_owner_or_admin(current_user)

        return BillingService.get_subscription(
            args["plan"], args["interval"], current_user.email, current_user.current_tenant_id
        )

class Invoices(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @only_edition_cloud
    def get(self):
        """
        获取当前用户的发票信息。

        装饰器:
            - setup_required: 确保系统设置已完成。
            - login_required: 确保用户已登录。
            - account_initialization_required: 确保用户账号已初始化。
            - only_edition_cloud: 限制该功能仅在云版本中可用。

        返回:
            用户邮箱和当前租户ID对应的发票信息。
        """
        # 检查用户是否为租户所有者或管理员
        BillingService.is_tenant_owner_or_admin(current_user)
        # 获取当前用户的发票信息
        return BillingService.get_invoices(current_user.email, current_user.current_tenant_id)


api.add_resource(Subscription, "/billing/subscription")
api.add_resource(Invoices, "/billing/invoices")
