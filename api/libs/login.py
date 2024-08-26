import os
from functools import wraps

from flask import current_app, g, has_request_context, request
from flask_login import user_logged_in
from flask_login.config import EXEMPT_METHODS
from werkzeug.exceptions import Unauthorized
from werkzeug.local import LocalProxy

from extensions.ext_database import db
from models.account import Account, Tenant, TenantAccountJoin

#: A proxy for the current user. If no user is logged in, this will be an
#: anonymous user
current_user = LocalProxy(lambda: _get_user())


def login_required(func):
    """
    一个装饰器，用于确保当前用户已登录并经过身份验证才可访问视图。
    如果用户未登录，将调用 :attr:`LoginManager.unauthorized` 回调。
    
    使用示例：
    
    @app.route('/post')
    @login_required
    def post():
        pass

    如果仅在特定情况下需要用户登录，可以这样判断：

    if not current_user.is_authenticated:
        return current_app.login_manager.unauthorized()

    该装饰器还支持通过设置环境变量 `LOGIN_DISABLED` 为 `True` 来全局禁用身份验证，
    以便在单元测试时使用。

    注意：
    
    根据 W3 对 CORS 预检请求的指南，HTTP "OPTIONS" 请求免于登录检查。

    :param func: 需要装饰的视图函数。
    :type func: function
    :return: 被装饰的视图函数。
    """

    @wraps(func)
    def decorated_view(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        admin_api_key_enable = os.getenv("ADMIN_API_KEY_ENABLE", default="False")
        if admin_api_key_enable.lower() == "true":
            if auth_header:
                if " " not in auth_header:
                    raise Unauthorized("Invalid Authorization header format. Expected 'Bearer <api-key>' format.")
                auth_scheme, auth_token = auth_header.split(None, 1)
                auth_scheme = auth_scheme.lower()
                if auth_scheme != "bearer":
                    raise Unauthorized("Invalid Authorization header format. Expected 'Bearer <api-key>' format.")
                admin_api_key = os.getenv("ADMIN_API_KEY")

                # 验证API密钥
                if admin_api_key:
                    if os.getenv("ADMIN_API_KEY") == auth_token:
                        workspace_id = request.headers.get("X-WORKSPACE-ID")
                        if workspace_id:
                            tenant_account_join = (
                                db.session.query(Tenant, TenantAccountJoin)
                                .filter(Tenant.id == workspace_id)
                                .filter(TenantAccountJoin.tenant_id == Tenant.id)
                                .filter(TenantAccountJoin.role == "owner")
                                .one_or_none()
                            )
                            if tenant_account_join:
                                tenant, ta = tenant_account_join
                                account = Account.query.filter_by(id=ta.account_id).first()
                                # 登录管理员
                                if account:
                                    account.current_tenant = tenant
                                    current_app.login_manager._update_request_context_with_user(account)
                                    user_logged_in.send(current_app._get_current_object(), user=_get_user())
        
        # 免登录检查的HTTP方法或当登录被禁用时
        if request.method in EXEMPT_METHODS or current_app.config.get("LOGIN_DISABLED"):
            pass
        elif not current_user.is_authenticated:
            return current_app.login_manager.unauthorized()

        # 兼容Flask 1.x
        # current_app.ensure_sync 只在Flask >= 2.0中可用
        if callable(getattr(current_app, "ensure_sync", None)):
            return current_app.ensure_sync(func)(*args, **kwargs)
        return func(*args, **kwargs)

    return decorated_view


def _get_user():
    """
    获取当前请求的登录用户。
    
    该函数首先检查当前请求上下文中是否存在登录用户。如果存在，但用户信息尚未加载，则调用登录管理器加载用户信息。
    
    返回值:
        - 如果有登录用户，则返回该用户对象。
        - 如果没有登录用户或不在请求上下文中，则返回None。
    """
    if has_request_context():  # 检查当前是否有请求上下文
        if "_login_user" not in g:  # 在全局变量g中检查登录用户是否存在
            current_app.login_manager._load_user()  # 如果未加载用户，则加载

        return g._login_user  # 返回登录用户对象

    return None  # 如果没有请求上下文，返回None
