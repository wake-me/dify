import logging
from datetime import datetime, timezone
from typing import Optional

import requests
from flask import current_app, redirect, request
from flask_restful import Resource

from constants.languages import languages
from extensions.ext_database import db
from libs.oauth import GitHubOAuth, GoogleOAuth, OAuthUserInfo
from models.account import Account, AccountStatus
from services.account_service import AccountService, RegisterService, TenantService

from .. import api


def get_oauth_providers():
    """
    获取支持的OAuth提供者字典。
    
    该函数不接受参数。
    
    返回值:
        dict: 包含所有支持的OAuth提供者的字典，键是提供者名称（如github、google），值是对应的OAuth实例。
    """
    with current_app.app_context():
        # 初始化GitHub OAuth客户端
        github_oauth = GitHubOAuth(client_id=current_app.config.get('GITHUB_CLIENT_ID'),
                                   client_secret=current_app.config.get(
                                       'GITHUB_CLIENT_SECRET'),
                                   redirect_uri=current_app.config.get(
                                       'CONSOLE_API_URL') + '/console/api/oauth/authorize/github')

        # 初始化Google OAuth客户端
        google_oauth = GoogleOAuth(client_id=current_app.config.get('GOOGLE_CLIENT_ID'),
                                   client_secret=current_app.config.get(
                                       'GOOGLE_CLIENT_SECRET'),
                                   redirect_uri=current_app.config.get(
                                       'CONSOLE_API_URL') + '/console/api/oauth/authorize/google')

        # 将初始化的OAuth客户端添加到提供者字典中
        OAUTH_PROVIDERS = {
            'github': github_oauth,
            'google': google_oauth
        }
        return OAUTH_PROVIDERS

class OAuthLogin(Resource):
    """
    处理OAuth登录请求的类。
    
    参数:
    - provider: 字符串，指定OAuth提供者的名称。
    
    返回值:
    - 如果提供者有效，重定向到相应的授权页面；如果无效，返回一个包含错误信息的JSON响应。
    """

    def get(self, provider: str):
        # 获取所有配置的OAuth提供者
        OAUTH_PROVIDERS = get_oauth_providers()
        
        # 设置当前应用的上下文
        with current_app.app_context():
            # 根据provider参数获取对应的OAuth提供者配置
            oauth_provider = OAUTH_PROVIDERS.get(provider)
            print(vars(oauth_provider))  # 打印OAuth提供者配置的变量信息，通常用于调试
            
        # 检查是否找到了对应的OAuth提供者配置
        if not oauth_provider:
            # 如果找不到，返回一个包含错误信息的响应
            return {'error': 'Invalid provider'}, 400

        # 获取授权URL，并重定向到该URL
        auth_url = oauth_provider.get_authorization_url()
        return redirect(auth_url)


class OAuthCallback(Resource):
    """
    处理OAuth认证回调的类。
    
    参数:
    - provider: 字符串，指定OAuth提供者的名称。
    
    返回值:
    - 根据不同的情况返回不同的JSON响应：错误时返回包含错误信息的JSON和400状态码；成功时重定向到控制台页面，并附带访问令牌。
    """

    def get(self, provider: str):
        # 获取所有配置的OAuth提供者
        OAUTH_PROVIDERS = get_oauth_providers()
        with current_app.app_context():
            # 根据提供者名称获取具体的OAuth提供者实例
            oauth_provider = OAUTH_PROVIDERS.get(provider)
        if not oauth_provider:
            # 如果不存在指定的提供者，则返回错误信息
            return {'error': 'Invalid provider'}, 400

        # 从请求参数中获取认证代码
        code = request.args.get('code')
        try:
            # 使用认证代码获取访问令牌和用户信息
            token = oauth_provider.get_access_token(code)
            user_info = oauth_provider.get_user_info(token)
        except requests.exceptions.HTTPError as e:
            # 记录OAuth过程中出现的HTTP错误
            logging.exception(
                f"An error occurred during the OAuth process with {provider}: {e.response.text}")
            return {'error': 'OAuth process failed'}, 400

        # 根据OAuth提供的用户信息生成或更新账户
        account = _generate_account(provider, user_info)
        
        # 检查账户状态
        if account.status == AccountStatus.BANNED.value or account.status == AccountStatus.CLOSED.value:
            # 如果账户被禁用或已关闭，则返回错误信息
            return {'error': 'Account is banned or closed.'}, 403

        # 如果账户状态是待处理，则将其状态更新为激活，并记录首次初始化时间
        if account.status == AccountStatus.PENDING.value:
            account.status = AccountStatus.ACTIVE.value
            account.initialized_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.session.commit()

        # 如果账户是首个所有者，则创建租户
        TenantService.create_owner_tenant_if_not_exist(account)

        # 更新账户的最后登录时间
        AccountService.update_last_login(account, request)

        # 生成并获取账户的JWT令牌
        token = AccountService.get_account_jwt_token(account)

        # 重定向到控制台页面，并附带访问令牌
        return redirect(f'{current_app.config.get("CONSOLE_WEB_URL")}?console_token={token}')

def _get_account_by_openid_or_email(provider: str, user_info: OAuthUserInfo) -> Optional[Account]:
    """
    根据开放ID或电子邮件地址获取账户信息。
    
    参数:
    - provider: 字符串，表示身份验证提供者（如GitHub、Google等）。
    - user_info: OAuthUserInfo对象，包含用户的开放ID和电子邮件地址等信息。
    
    返回值:
    - Optional[Account]，如果找到相应的账户，则返回Account对象；否则返回None。
    """
    # 尝试根据提供的开放ID获取账户
    account = Account.get_by_openid(provider, user_info.id)

    # 如果根据开放ID未找到账户，尝试根据电子邮件地址查询账户
    if not account:
        account = Account.query.filter_by(email=user_info.email).first()

    return account

def _generate_account(provider: str, user_info: OAuthUserInfo):
    """
    根据提供的OAuth用户信息生成或获取账户，并将其与提供商链接。
    
    参数:
    - provider: 字符串，指定用户信息来源的提供商（如Google、Facebook等）。
    - user_info: OAuthUserInfo对象，包含用户的详细信息，如名字、邮箱、ID等。
    
    返回值:
    - account: 账户对象，已存在则返回该账户，否则创建并返回新账户。
    """
    # 尝试通过openid或邮箱获取已有账户
    account = _get_account_by_openid_or_email(provider, user_info)

    if not account:
        # 如果账户不存在，则创建新账户
        account_name = user_info.name if user_info.name else 'Dify'
        account = RegisterService.register(
            email=user_info.email,
            name=account_name,
            password=None,
            open_id=user_info.id,
            provider=provider
        )

        # 设置用户界面语言
        preferred_lang = request.accept_languages.best_match(languages)
        if preferred_lang and preferred_lang in languages:
            interface_language = preferred_lang
        else:
            interface_language = languages[0]
        account.interface_language = interface_language
        db.session.commit()  # 提交对账户的更改

    # 将账户与提供商进行链接
    AccountService.link_account_integrate(provider, user_info.id, account)

    return account


api.add_resource(OAuthLogin, '/oauth/login/<provider>')
api.add_resource(OAuthCallback, '/oauth/authorize/<provider>')
