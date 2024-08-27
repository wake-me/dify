from flask_restful import Resource, reqparse

from controllers.console.setup import setup_required
from controllers.inner_api import api
from controllers.inner_api.wraps import inner_api_only
from events.tenant_event import tenant_was_created
from models.account import Account
from services.account_service import TenantService


class EnterpriseWorkspace(Resource):
    @setup_required
    @inner_api_only
    def post(self):
        """
        创建一个新的企业工作空间。
        
        请求需要包含企业工作空间的名称和所有者的电子邮件地址。
        
        返回值:
            - 当企业工作空间创建成功时，返回一个包含消息的字典，消息内容是'enterprise workspace created.'；
            - 当所有者账户不存在时，返回一个包含消息的字典，消息内容是'owner account not found.'，并返回HTTP状态码404。
        """
        # 解析请求中的参数
        parser = reqparse.RequestParser()
        parser.add_argument("name", type=str, required=True, location="json")
        parser.add_argument("owner_email", type=str, required=True, location="json")
        args = parser.parse_args()

        account = Account.query.filter_by(email=args["owner_email"]).first()
        if account is None:
            return {"message": "owner account not found."}, 404

        tenant = TenantService.create_tenant(args["name"])
        TenantService.create_tenant_member(tenant, account, role="owner")

        # 发送租户创建成功的信号
        tenant_was_created.send(tenant)

        return {"message": "enterprise workspace created."}


api.add_resource(EnterpriseWorkspace, "/enterprise/workspace")
