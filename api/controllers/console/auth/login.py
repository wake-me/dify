import flask_login
from flask import current_app, request
from flask_restful import Resource, reqparse

import services
from controllers.console import api
from controllers.console.setup import setup_required
from libs.helper import email
from libs.password import valid_password
from services.account_service import AccountService, TenantService


class LoginApi(Resource):
    """用户登录的资源类。"""

    @setup_required
    def post(self):
        """
        验证用户身份并登录。
        
        请求参数:
        - email: 用户邮箱，必填，位于JSON体中。
        - password: 用户密码，必填，位于JSON体中。
        - remember_me: 是否记住登录状态，非必填，默认为False，位于JSON体中。
        
        返回值:
        - 当登录成功时，返回包含token的成功信息；
        - 当登录失败时，返回包含错误信息的401状态码。
        """
        parser = reqparse.RequestParser()
        parser.add_argument('email', type=email, required=True, location='json')
        parser.add_argument('password', type=valid_password, required=True, location='json')
        parser.add_argument('remember_me', type=bool, required=False, default=False, location='json')
        args = parser.parse_args()

        # 验证recaptcha的代码待实现

        try:
            account = AccountService.authenticate(args['email'], args['password'])
        except services.errors.account.AccountLoginError as e:
            return {'code': 'unauthorized', 'message': str(e)}, 401

        # SELF_HOSTED only have one workspace
        tenants = TenantService.get_join_tenants(account)
        if len(tenants) == 0:
            return {'result': 'fail', 'data': 'workspace not found, please contact system admin to invite you to join in a workspace'}

        # 更新用户上次登录信息
        AccountService.update_last_login(account, request)

        # 生成并返回用户JWT令牌
        token = AccountService.get_account_jwt_token(account)

        return {'result': 'success', 'data': token}


class LogoutApi(Resource):
    """
    定义了一个用于用户登出的API类。
    """

    @setup_required
    def get(self):
        """
        处理用户登出的GET请求。

        无需参数。

        返回值:
            返回一个包含登出结果的字典，如{'result': 'success'}。
        """
        flask_login.logout_user()  # 执行用户登出操作
        return {'result': 'success'}  # 返回登出成功的提示


class ResetPasswordApi(Resource):
    @setup_required
    def get(self):
        """
        处理重置密码的GET请求。
        
        要求提供电子邮件地址，然后向该地址发送一封包含新密码的邮件。
        
        参数:
        - 无（通过GET请求的JSON体中获取email参数）
        
        返回值:
        - {'result': 'success'}: 表示发送重置密码邮件操作成功
        """
        parser = reqparse.RequestParser()
        parser.add_argument('email', type=email, required=True, location='json')
        args = parser.parse_args()

        # import mailchimp_transactional as MailchimpTransactional
        # from mailchimp_transactional.api_client import ApiClientError
        
        # 准备发送密码重置邮件所需的账户信息
        account = {'email': args['email']}
        # account = AccountService.get_by_email(args['email'])
        # if account is None:
        #     raise ValueError('Email not found')
        # new_password = AccountService.generate_password()
        # AccountService.update_password(account, new_password)

        # TODO: 发送邮件通知用户新密码
        MAILCHIMP_API_KEY = current_app.config['MAILCHIMP_TRANSACTIONAL_API_KEY']
        # mailchimp = MailchimpTransactional(MAILCHIMP_API_KEY)

        message = {
            'from_email': 'noreply@example.com',
            'to': [{'email': account.email}],
            'subject': 'Reset your Dify password',
            'html': """
                <p>Dear User,</p>
                <p>The Dify team has generated a new password for you, details as follows:</p> 
                <p><strong>{new_password}</strong></p>
                <p>Please change your password to log in as soon as possible.</p>
                <p>Regards,</p>
                <p>The Dify Team</p> 
            """
        }

        # response = mailchimp.messages.send({
        #     'message': message,
        #     # required for transactional email
        #     ' settings': {
        #         'sandbox_mode': current_app.config['MAILCHIMP_SANDBOX_MODE'],
        #     },
        # })

        # Check if MSG was sent
        # if response.status_code != 200:
        #     # handle error
        #     pass

        return {'result': 'success'}


api.add_resource(LoginApi, '/login')
api.add_resource(LogoutApi, '/logout')
