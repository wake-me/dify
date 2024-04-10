from datetime import datetime

import pytz
from flask import current_app, request
from flask_login import current_user
from flask_restful import Resource, fields, marshal_with, reqparse

from constants.languages import supported_language
from controllers.console import api
from controllers.console.setup import setup_required
from controllers.console.workspace.error import (
    AccountAlreadyInitedError,
    CurrentPasswordIncorrectError,
    InvalidInvitationCodeError,
    RepeatPasswordNotMatchError,
)
from controllers.console.wraps import account_initialization_required
from extensions.ext_database import db
from fields.member_fields import account_fields
from libs.helper import TimestampField, timezone
from libs.login import login_required
from models.account import AccountIntegrate, InvitationCode
from services.account_service import AccountService
from services.errors.account import CurrentPasswordIncorrectError as ServiceCurrentPasswordIncorrectError


class AccountInitApi(Resource):
    """
    账户初始化API接口类
    """

    @setup_required
    @login_required
    def post(self):
        """
        初始化账户接口
        需要用户登录，并且检查账户是否已经激活。如果账户已经激活，则抛出错误。
        用户必须提供接口语言、时区信息，如果是云版本，还需要提供邀请码。
        
        参数:
        - 无
        
        返回值:
        - {'result': 'success'}: 初始化成功
        - 抛出各种错误（如账户已激活、无效的邀请码等）
        """
        account = current_user

        # 检查账户是否已经是激活状态
        if account.status == 'active':
            raise AccountAlreadyInitedError()

        parser = reqparse.RequestParser()

        # 如果是云版本，添加邀请码参数解析
        if current_app.config['EDITION'] == 'CLOUD':
            parser.add_argument('invitation_code', type=str, location='json')

        # 解析请求中的接口语言和时区参数
        parser.add_argument(
            'interface_language', type=supported_language, required=True, location='json')
        parser.add_argument('timezone', type=timezone,
                            required=True, location='json')
        args = parser.parse_args()

        # 验证邀请码（如果适用）
        if current_app.config['EDITION'] == 'CLOUD':
            if not args['invitation_code']:
                raise ValueError('invitation_code is required')

            # 检查邀请码是否有效
            invitation_code = db.session.query(InvitationCode).filter(
                InvitationCode.code == args['invitation_code'],
                InvitationCode.status == 'unused',
            ).first()

            if not invitation_code:
                raise InvalidInvitationCodeError()

            # 更新邀请码状态为已使用
            invitation_code.status = 'used'
            invitation_code.used_at = datetime.utcnow()
            invitation_code.used_by_tenant_id = account.current_tenant_id
            invitation_code.used_by_account_id = account.id

        # 更新账户信息
        account.interface_language = args['interface_language']
        account.timezone = args['timezone']
        account.interface_theme = 'light'
        account.status = 'active'
        account.initialized_at = datetime.utcnow()
        db.session.commit()

        return {'result': 'success'}


class AccountProfileApi(Resource):
    """
    账户简介API类，提供获取当前登录用户账户信息的功能。
    
    属性:
        Resource: 父类，提供API资源的基础方法。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(account_fields)
    def get(self):
        """
        获取当前登录用户的账户信息。
        
        方法装饰器:
            - setup_required: 确保系统设置已完成。
            - login_required: 确保用户已登录。
            - account_initialization_required: 确保账户已初始化。
            - marshal_with(account_fields): 使用指定字段列表格式化返回数据。
            
        返回:
            当前登录的用户对象，经过指定字段格式化后的数据。
        """
        return current_user  # 返回当前已登录的用户对象

class AccountNameApi(Resource):
    """
    账户名称API接口类，用于处理账户名称的更改请求。
    
    该类继承自Resource，提供了post方法用于接收并处理用户提交的账户名称更改请求。
    需要用户登录且账号未初始化，请求的数据格式需符合指定的字段要求。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(account_fields)
    def post(self):
        """
        处理用户提交的账户名称更改请求。
        
        需要用户已登录且账号已初始化，接收的请求数据应包含一个名为'name'的字符串参数。
        参数验证通过后，更新用户的账户名称，并返回更新后的账户信息。
        
        返回值:
            更新后的账户信息。
        """
        parser = reqparse.RequestParser()
        parser.add_argument('name', type=str, required=True, location='json')
        args = parser.parse_args()

        # 验证账户名称长度是否符合要求
        if len(args['name']) < 3 or len(args['name']) > 30:
            raise ValueError(
                "Account name must be between 3 and 30 characters.")

        # 更新账户名称，并返回更新后的账户信息
        updated_account = AccountService.update_account(current_user, name=args['name'])

        return updated_account


class AccountAvatarApi(Resource):
    """
    账户头像接口类，用于处理账户头像的更新请求。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(account_fields)
    def post(self):
        """
        更新当前用户的头像。
        
        参数:
        - 无
        
        返回值:
        - 更新后的账户信息
        """
        
        # 解析请求中的头像参数
        parser = reqparse.RequestParser()
        parser.add_argument('avatar', type=str, required=True, location='json')
        args = parser.parse_args()

        # 更新账户头像，并返回更新后的账户信息
        updated_account = AccountService.update_account(current_user, avatar=args['avatar'])

        return updated_account


class AccountInterfaceLanguageApi(Resource):
    """
    账户接口语言API类，用于更改用户账户的接口语言设置。
    
    方法:
    - post: 更新账户的接口语言设置。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(account_fields)
    def post(self):
        """
        更新当前登录用户的接口语言设置。
        
        参数:
        - interface_language: 通过JSON请求体传入，表示要设置的接口语言，必须是支持的语言之一。
        
        返回值:
        - 更新后的账户信息。
        """
        
        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument(
            'interface_language', type=supported_language, required=True, location='json')
        args = parser.parse_args()

        # 更新账户的接口语言设置并返回更新后的账户信息
        updated_account = AccountService.update_account(current_user, interface_language=args['interface_language'])

        return updated_account


class AccountInterfaceThemeApi(Resource):
    """
    账户界面主题接口API类，用于更改用户账户的界面主题。
    
    方法:
    - post: 更新当前登录用户的界面主题。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(account_fields)
    def post(self):
        """
        提供更改当前登录用户界面主题的功能。
        
        参数:
        - interface_theme: 字符串类型，必选，取值为'light'或'dark'，通过JSON传递。
        
        返回值:
        - 更新后的用户账户信息。
        """
        
        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('interface_theme', type=str, choices=[
            'light', 'dark'], required=True, location='json')
        args = parser.parse_args()

        # 更新账户的界面主题
        updated_account = AccountService.update_account(current_user, interface_theme=args['interface_theme'])

        return updated_account


class AccountTimezoneApi(Resource):
    """
    账户时区接口API类，用于处理账户时区的更改。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(account_fields)
    def post(self):
        """
        处理POST请求，用于更新当前登录用户的时区信息。
        
        参数:
        - 无
        
        返回值:
        - 更新后的账户信息
        """
        
        # 解析请求体中的时区参数
        parser = reqparse.RequestParser()
        parser.add_argument('timezone', type=str,
                            required=True, location='json')
        args = parser.parse_args()

        # 验证时区字符串的有效性
        if args['timezone'] not in pytz.all_timezones:
            raise ValueError("Invalid timezone string.")

        # 更新账户的时区信息
        updated_account = AccountService.update_account(current_user, timezone=args['timezone'])

        return updated_account


class AccountPasswordApi(Resource):
    """
    账户密码接口类，用于处理账户密码的更改请求。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(account_fields)
    def post(self):
        """
        处理客户端提交的密码更改请求。
        
        参数:
        - 无
        
        返回值:
        - {"result": "success"}: 更改密码成功
        """
        # 解析客户端请求中的密码参数
        parser = reqparse.RequestParser()
        parser.add_argument('password', type=str,
                            required=False, location='json')
        parser.add_argument('new_password', type=str,
                            required=True, location='json')
        parser.add_argument('repeat_new_password', type=str,
                            required=True, location='json')
        args = parser.parse_args()

        # 验证新密码和重复新密码是否一致
        if args['new_password'] != args['repeat_new_password']:
            raise RepeatPasswordNotMatchError()

        try:
            # 尝试更新账户密码，如果当前密码不正确会抛出异常
            AccountService.update_account_password(
                current_user, args['password'], args['new_password'])
        except ServiceCurrentPasswordIncorrectError:
            raise CurrentPasswordIncorrectError()

        return {"result": "success"}


class AccountIntegrateApi(Resource):
    """
    账户集成API接口类，用于处理账户与第三方服务的集成信息。
    """
    
    # 定义返回集成信息时的字段
    integrate_fields = {
        'provider': fields.String,
        'created_at': TimestampField,
        'is_bound': fields.Boolean,
        'link': fields.String
    }

    # 定义返回集成列表时的字段结构
    integrate_list_fields = {
        'data': fields.List(fields.Nested(integrate_fields)),
    }

    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(integrate_list_fields)
    def get(self):
        """
        获取当前用户的账户集成信息列表。
        
        需要用户已设置、已登录、账户已初始化。
        返回值: 包含集成信息的列表，每个集成信息包括提供者、创建时间、是否绑定以及链接。
        """
        account = current_user  # 获取当前登录的用户

        # 从数据库查询当前账户的所有集成信息
        account_integrates = db.session.query(AccountIntegrate).filter(
            AccountIntegrate.account_id == account.id).all()

        # 基础URL和OAuth登录路径
        base_url = request.url_root.rstrip('/')
        oauth_base_path = "/console/api/oauth/login"
        providers = ["github", "google"]  # 支持的集成提供者列表

        # 遍历提供者列表，生成集成信息数据
        integrate_data = []
        for provider in providers:
            # 查找当前提供者是否已绑定
            existing_integrate = next((ai for ai in account_integrates if ai.provider == provider), None)
            if existing_integrate:
                # 如果已绑定，添加相关信息
                integrate_data.append({
                    'id': existing_integrate.id,
                    'provider': provider,
                    'created_at': existing_integrate.created_at,
                    'is_bound': True,
                    'link': None
                })
            else:
                # 如果未绑定，添加未绑定的信息及登录链接
                integrate_data.append({
                    'id': None,
                    'provider': provider,
                    'created_at': None,
                    'is_bound': False,
                    'link': f'{base_url}{oauth_base_path}/{provider}'
                })

        return {'data': integrate_data}  # 返回集成信息列表


# Register API resources
api.add_resource(AccountInitApi, '/account/init')
api.add_resource(AccountProfileApi, '/account/profile')
api.add_resource(AccountNameApi, '/account/name')
api.add_resource(AccountAvatarApi, '/account/avatar')
api.add_resource(AccountInterfaceLanguageApi, '/account/interface-language')
api.add_resource(AccountInterfaceThemeApi, '/account/interface-theme')
api.add_resource(AccountTimezoneApi, '/account/timezone')
api.add_resource(AccountPasswordApi, '/account/password')
api.add_resource(AccountIntegrateApi, '/account/integrates')
# api.add_resource(AccountEmailApi, '/account/email')
# api.add_resource(AccountEmailVerifyApi, '/account/email-verify')
