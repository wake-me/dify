import os

from flask import session
from flask_restful import Resource, reqparse

from configs import dify_config
from libs.helper import str_len
from models.model import DifySetup
from services.account_service import TenantService

from . import api
from .error import AlreadySetupError, InitValidateFailedError
from .wraps import only_edition_self_hosted


class InitValidateAPI(Resource):
    def get(self):
        """
        处理获取初始化验证状态的请求。
        
        返回:
            - 如果初始化已完成，则返回 {'status': 'finished'}；
            - 如果初始化未开始，则返回 {'status': 'not_started'}。
        """
        init_status = get_init_validate_status()  # 获取初始化验证的状态
        if init_status:
            return {"status": "finished"}
        return {"status": "not_started"}

    @only_edition_self_hosted
    def post(self):
        """
        处理提交初始化验证的请求。
        
        提交的JSON数据应包含一个'password'字段，用于验证初始化密码。
        
        返回:
            - 如果验证成功，则返回 {'result': 'success'}，并设置初始化验证通过的会话状态；
            - 如果验证失败（包括已初始化或密码错误），则抛出相应的错误。
        """
        # 检查租户是否已经创建
        tenant_count = TenantService.get_tenant_count()
        if tenant_count > 0:
            raise AlreadySetupError()  # 如果租户已存在，抛出已设置错误

        parser = reqparse.RequestParser()
        parser.add_argument("password", type=str_len(30), required=True, location="json")
        input_password = parser.parse_args()["password"]

        if input_password != os.environ.get("INIT_PASSWORD"):
            session["is_init_validated"] = False
            raise InitValidateFailedError()

        session["is_init_validated"] = True
        return {"result": "success"}, 201


def get_init_validate_status():
    if dify_config.EDITION == "SELF_HOSTED":
        if os.environ.get("INIT_PASSWORD"):
            return session.get("is_init_validated") or DifySetup.query.first()

    return True


api.add_resource(InitValidateAPI, "/init")
