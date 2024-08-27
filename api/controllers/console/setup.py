from functools import wraps

from flask import request
from flask_restful import Resource, reqparse

from configs import dify_config
from libs.helper import email, get_remote_ip, str_len
from libs.password import valid_password
from models.model import DifySetup
from services.account_service import RegisterService, TenantService

from . import api
from .error import AlreadySetupError, NotInitValidateError, NotSetupError
from .init_validate import get_init_validate_status
from .wraps import only_edition_self_hosted


class SetupApi(Resource):
    def get(self):
        if dify_config.EDITION == "SELF_HOSTED":
            setup_status = get_setup_status()
            if setup_status:
                return {"step": "finished", "setup_at": setup_status.setup_at.isoformat()}
            return {"step": "not_started"}
        return {"step": "finished"}

    @only_edition_self_hosted
    def post(self):
        """
        执行设置流程。
        
        首先检查是否已经完成了设置，如果完成则抛出异常；然后检查租户是否已创建，如果已创建也抛出异常。
        接着，解析请求中的设置信息（邮箱、名称、密码），注册新账户，并完成设置流程。
        
        参数:
            - email: 用户邮箱，必填。
            - name: 用户名，必填。
            - password: 用户密码，必填。
        
        返回值:
            - 设置成功返回结果和状态码201。
            
        抛出:
            - AlreadySetupError: 如果已经完成设置。
            - NotInitValidateError: 如果初始化验证未通过。
            - NotSetupError: 如果设置尚未开始。
        """
        # 检查是否已经设置
        if get_setup_status():
            raise AlreadySetupError()

        # 检查是否已有租户创建
        tenant_count = TenantService.get_tenant_count()
        if tenant_count > 0:
            raise AlreadySetupError()

        if not get_init_validate_status():
            raise NotInitValidateError()

        parser = reqparse.RequestParser()
        parser.add_argument("email", type=email, required=True, location="json")
        parser.add_argument("name", type=str_len(30), required=True, location="json")
        parser.add_argument("password", type=valid_password, required=True, location="json")
        args = parser.parse_args()

        # setup
        RegisterService.setup(
            email=args["email"], name=args["name"], password=args["password"], ip_address=get_remote_ip(request)
        )

        return {"result": "success"}, 201


def setup_required(view):
    """
    装饰器，用于确保视图在设置完成后才能访问。
    
    参数:
        - view: 待装饰的视图函数。
        
    返回:
        - 经过装饰，添加了设置检查逻辑的视图函数。
        
    抛出:
        - NotInitValidateError: 如果初始化验证未通过。
        - NotSetupError: 如果设置尚未完成。
    """
    @wraps(view)
    def decorated(*args, **kwargs):
        # 检查初始化验证和设置状态
        if not get_init_validate_status():
            raise NotInitValidateError()

        elif not get_setup_status():
            raise NotSetupError()

        return view(*args, **kwargs)

    return decorated


def get_setup_status():
    if dify_config.EDITION == "SELF_HOSTED":
        return DifySetup.query.first()
    else:
        return True


api.add_resource(SetupApi, "/setup")
