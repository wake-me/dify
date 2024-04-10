import base64
import secrets
from datetime import datetime

from flask_restful import Resource, reqparse

from constants.languages import supported_language
from controllers.console import api
from controllers.console.error import AlreadyActivateError
from extensions.ext_database import db
from libs.helper import email, str_len, timezone
from libs.password import hash_password, valid_password
from models.account import AccountStatus
from services.account_service import RegisterService


class ActivateCheckApi(Resource):
    """
    激活检查 API，用于验证注册令牌的有效性。

    方法:
    - GET: 根据提供的 workspace_id, email 和 token 参数验证注册邀请是否有效。

    参数:
    - workspace_id (可选): 工作空间的ID。
    - email (可选): 用户的电子邮件地址。
    - token (必需): 注册邀请的令牌。

    返回值:
    - is_valid: 布尔值，表示提供的 token 是否有效。
    - workspace_name: 字符串，如果 token 有效，则返回工作空间的名称；否则返回 None。
    """

    def get(self):
        # 初始化请求参数解析器
        parser = reqparse.RequestParser()
        parser.add_argument('workspace_id', type=str, required=False, nullable=True, location='args')
        parser.add_argument('email', type=email, required=False, nullable=True, location='args')
        parser.add_argument('token', type=str, required=True, nullable=False, location='args')
        # 解析请求参数
        args = parser.parse_args()

        # 从解析结果中提取参数
        workspaceId = args['workspace_id']
        reg_email = args['email']
        token = args['token']

        # 验证令牌的有效性并获取邀请信息
        invitation = RegisterService.get_invitation_if_token_valid(workspaceId, reg_email, token)

        # 根据邀请信息的存在与否返回验证结果
        return {'is_valid': invitation is not None, 'workspace_name': invitation['tenant'].name if invitation else None}

class ActivateApi(Resource):
    """
    处理API的激活请求

    方法:
    post: 创建或激活账户

    参数:
    - workspace_id: 工作空间ID，字符串类型，非必需，可为空
    - email: 电子邮箱地址，字符串类型，非必需，可为空
    - token: 邀请令牌，字符串类型，必需，不可为空
    - name: 用户名，字符串类型，必需，不可为空，长度不超过30
    - password: 密码，字符串类型，必需，不可为空
    - interface_language: 用户界面语言，字符串类型，必需，不可为空
    - timezone: 时区，字符串类型，必需，不可为空

    返回值:
    - {'result': 'success'}: 激活成功
    """

    def post(self):
        # 初始化请求参数解析器
        parser = reqparse.RequestParser()
        parser.add_argument('workspace_id', type=str, required=False, nullable=True, location='json')
        parser.add_argument('email', type=email, required=False, nullable=True, location='json')
        parser.add_argument('token', type=str, required=True, nullable=False, location='json')
        parser.add_argument('name', type=str_len(30), required=True, nullable=False, location='json')
        parser.add_argument('password', type=valid_password, required=True, nullable=False, location='json')
        parser.add_argument('interface_language', type=supported_language, required=True, nullable=False,
                            location='json')
        parser.add_argument('timezone', type=timezone, required=True, nullable=False, location='json')
        args = parser.parse_args()

        # 验证邀请令牌的有效性
        invitation = RegisterService.get_invitation_if_token_valid(args['workspace_id'], args['email'], args['token'])
        if invitation is None:
            raise AlreadyActivateError()

        # 撤销邀请令牌
        RegisterService.revoke_token(args['workspace_id'], args['email'], args['token'])

        account = invitation['account']
        account.name = args['name']

        # 生成密码盐
        salt = secrets.token_bytes(16)
        base64_salt = base64.b64encode(salt).decode()

        # 使用盐加密密码
        password_hashed = hash_password(args['password'], salt)
        base64_password_hashed = base64.b64encode(password_hashed).decode()
        account.password = base64_password_hashed
        account.password_salt = base64_salt
        account.interface_language = args['interface_language']
        account.timezone = args['timezone']
        account.interface_theme = 'light'
        account.status = AccountStatus.ACTIVE.value
        account.initialized_at = datetime.utcnow()
        db.session.commit()

        return {'result': 'success'}


api.add_resource(ActivateCheckApi, '/activate/check')
api.add_resource(ActivateApi, '/activate')
