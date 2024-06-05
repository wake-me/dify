from collections.abc import Callable
from datetime import datetime, timezone
from enum import Enum
from functools import wraps
from typing import Optional

from flask import current_app, request
from flask_login import user_logged_in
from flask_restful import Resource
from pydantic import BaseModel
from werkzeug.exceptions import Forbidden, Unauthorized

from extensions.ext_database import db
from libs.login import _get_user
from models.account import Account, Tenant, TenantAccountJoin, TenantStatus
from models.model import ApiToken, App, EndUser
from services.feature_service import FeatureService


class WhereisUserArg(Enum):
    """
    whereis_user_arg 枚举类的定义。

    用于指定用户信息查询的参数形式。
    """

    QUERY = 'query'    # 使用查询字符串形式
    JSON = 'json'      # 使用JSON格式
    FORM = 'form'      # 使用表单形式


class FetchUserArg(BaseModel):
    """
    用于定义获取用户参数的模型类。
    
    参数:
    - fetch_from: 指定从哪里获取用户信息，是 WhereisUserArg 类型的一个枚举。
    - required: 指定该参数是否为必需的，默认为 False。 
    
    返回值:
    无
    """
    fetch_from: WhereisUserArg
    required: bool = False
    # 这里定义了获取用户信息的相关配置，包括获取来源和是否必需。

def validate_app_token(view: Optional[Callable] = None, *, fetch_user_arg: Optional[FetchUserArg] = None):
    """
    用于验证应用程序令牌的装饰器函数。
    
    参数:
    - view: 可选，被装饰的视图函数。如果传递，则直接装饰该视图函数，否则返回一个装饰器。
    - fetch_user_arg: 可选，指定如何从请求中获取最终用户信息的参数。
    
    返回:
    - 如果view参数未提供，则返回一个装饰器函数；如果提供了，则直接装饰并返回该视图函数。
    """
    def decorator(view_func):
        @wraps(view_func)
        def decorated_view(*args, **kwargs):
            # 验证并获取应用程序API令牌
            api_token = validate_and_get_api_token('app')

            # 从数据库中查询对应的App模型
            app_model = db.session.query(App).filter(App.id == api_token.app_id).first()
            if not app_model:
                raise Forbidden("The app no longer exists.")

            # 检查应用程序状态是否正常
            if app_model.status != 'normal':
                raise Forbidden("The app's status is abnormal.")

            # 检查应用程序是否启用了API访问
            if not app_model.enable_api:
                raise Forbidden("The app's API service has been disabled.")

            tenant = db.session.query(Tenant).filter(Tenant.id == app_model.tenant_id).first()
            if tenant.status == TenantStatus.ARCHIVE:
                raise Forbidden("The workspace's status is archived.")

            kwargs['app_model'] = app_model

            # 如果需要，则尝试从请求中获取最终用户ID
            if fetch_user_arg:
                # 根据参数指定的位置（查询字符串、JSON或表单）来获取用户ID
                if fetch_user_arg.fetch_from == WhereisUserArg.QUERY:
                    user_id = request.args.get('user')
                elif fetch_user_arg.fetch_from == WhereisUserArg.JSON:
                    user_id = request.get_json().get('user')
                elif fetch_user_arg.fetch_from == WhereisUserArg.FORM:
                    user_id = request.form.get('user')
                else:
                    # 如果未指定位置，则默认为None
                    user_id = None

                # 如果用户ID是必需的但未提供，则抛出错误
                if not user_id and fetch_user_arg.required:
                    raise ValueError("Arg user must be provided.")

                # 将用户ID转换为字符串，准备进行用户信息的创建或更新
                if user_id:
                    user_id = str(user_id)

                # 根据用户ID创建或更新最终用户信息
                kwargs['end_user'] = create_or_update_end_user_for_user_id(app_model, user_id)

            # 调用原始视图函数，并传递可能已更新的参数
            return view_func(*args, **kwargs)
        return decorated_view

    # 根据是否提供了view参数来决定返回装饰器还是装饰后的视图函数
    if view is None:
        return decorator
    else:
        return decorator(view)


def cloud_edition_billing_resource_check(resource: str,
                                         api_token_type: str,
                                         error_msg: str = "You have reached the limit of your subscription."):
    """
    用于检查云版本计费资源是否超过限制的装饰器工厂函数。
    
    参数:
    - resource: 要检查的资源类型（如成员、应用、向量空间等）。
    - api_token_type: API令牌的类型，用于验证和获取API令牌。
    - error_msg: 当资源超过限制时抛出的错误消息，默认为"You have reached the limit of your subscription."。
    
    返回值:
    - interceptor: 一个装饰器，用于拦截和检查请求是否超过指定资源的限制。
    """
    def interceptor(view):
        """
        拦截器函数，用于装饰视图函数，以在视图执行前检查资源限制。
        
        参数:
        - view: 被装饰的视图函数。
        
        返回值:
        - decorated: 经过装饰的视图函数，会在执行前添加资源限制检查。
        """
        def decorated(*args, **kwargs):
            """
            装饰器函数，用于实际执行资源限制检查和调用视图函数。
            
            参数:
            - *args: 位置参数。
            - **kwargs: 关键字参数。
            
            返回值:
            - 视图函数的返回值，如果资源检查失败则会抛出Forbidden异常。
            """
            api_token = validate_and_get_api_token(api_token_type)  # 验证并获取API令牌
            features = FeatureService.get_features(api_token.tenant_id)  # 根据租户ID获取功能服务

            # 检查是否启用了计费功能
            if features.billing.enabled:
                members = features.members
                apps = features.apps
                vector_space = features.vector_space
                documents_upload_quota = features.documents_upload_quota

                # 根据资源类型检查是否超过限制
                if resource == 'members' and 0 < members.limit <= members.size:
                    raise Forbidden(error_msg)
                elif resource == 'apps' and 0 < apps.limit <= apps.size:
                    raise Forbidden(error_msg)
                elif resource == 'vector_space' and 0 < vector_space.limit <= vector_space.size:
                    raise Forbidden(error_msg)
                elif resource == 'documents' and 0 < documents_upload_quota.limit <= documents_upload_quota.size:
                    raise Forbidden(error_msg)
                else:
                    return view(*args, **kwargs)  # 资源检查通过，执行视图函数

            return view(*args, **kwargs)  # 若未启用计费功能，直接执行视图函数
        return decorated
    return interceptor


def cloud_edition_billing_knowledge_limit_check(resource: str,
                                                api_token_type: str,
                                                error_msg: str = "To unlock this feature and elevate your Dify experience, please upgrade to a paid plan."):
    """
    用于检查特定资源的计费限制是否超出阈值的装饰器工厂函数。
    
    参数:
    - resource: 要检查的资源名称，例如 'add_segment'。
    - api_token_type: API令牌的类型，用于验证用户身份和访问权限。
    - error_msg: 当用户未升级到付费计划而尝试访问受限功能时抛出的错误信息。
    
    返回值:
    - interceptor: 一个装饰器，用于拦截并验证用户是否有权限访问特定资源。
    """
    def interceptor(view):
        @wraps(view)
        def decorated(*args, **kwargs):
            # 验证并获取API令牌，根据令牌类型确定用户身份。
            api_token = validate_and_get_api_token(api_token_type)
            # 获取用户当前的使用功能列表。
            features = FeatureService.get_features(api_token.tenant_id)
            # 检查计费功能是否已启用。
            if features.billing.enabled:
                # 如果资源是'add_segment'且用户计划为'sandbox'，则禁止访问。
                if resource == 'add_segment':
                    if features.billing.subscription.plan == 'sandbox':
                        raise Forbidden(error_msg)
                # 如果资源不是'add_segment'且计费功能已启用，允许访问原函数。
                else:
                    return view(*args, **kwargs)

            # 如果计费功能未启用，也允许访问原函数。
            return view(*args, **kwargs)

        return decorated

    return interceptor

def validate_dataset_token(view=None):
    """
    验证数据集令牌的装饰器。
    
    参数:
    - view: 被装饰的视图函数，该参数可选。
    
    返回:
    - 如果 view 参数提供，则返回装饰后的视图函数。
    - 如果 view 参数未提供，则返回一个装饰器函数。
    """

    def decorator(view):
        @wraps(view)
        def decorated(*args, **kwargs):
            # 验证并获取数据集API令牌
            api_token = validate_and_get_api_token('dataset')
            # 查询租户和其拥有者账户的关联信息
            tenant_account_join = db.session.query(Tenant, TenantAccountJoin) \
                .filter(Tenant.id == api_token.tenant_id) \
                .filter(TenantAccountJoin.tenant_id == Tenant.id) \
                .filter(TenantAccountJoin.role.in_(['owner'])) \
                .filter(Tenant.status == TenantStatus.NORMAL) \
                .one_or_none() # TODO: only owner information is required, so only one is returned.
            if tenant_account_join:
                tenant, ta = tenant_account_join
                # 查询并登录拥有者账户
                account = Account.query.filter_by(id=ta.account_id).first()
                if account:
                    account.current_tenant = tenant
                    # 更新请求上下文并登录用户
                    current_app.login_manager._update_request_context_with_user(account)
                    user_logged_in.send(current_app._get_current_object(), user=_get_user())
                else:
                    # 如果拥有者账户不存在，则抛出未授权异常
                    raise Unauthorized("Tenant owner account does not exist.")
            else:
                # 如果租户不存在，则抛出未授权异常
                raise Unauthorized("Tenant does not exist.")
            return view(api_token.tenant_id, *args, **kwargs)
        return decorated

    if view:
        # 如果直接传入视图函数，则返回装饰后的视图函数
        return decorator(view)

    # 如果 view 为 None，意味着装饰器没有使用括号，返回装饰器本身
    # 用于作为方法装饰器使用
    return decorator


def validate_and_get_api_token(scope=None):
    """
    验证并获取API令牌。
    
    参数:
    - scope: 字符串，指定令牌的权限范围，可选参数，默认为None。
    
    返回值:
    - ApiToken实例，如果验证成功，则返回对应的API令牌实例。
    
    抛出:
    - Unauthorized: 如果验证失败，会抛出未授权异常。
    """

    # 从请求头中获取认证信息
    auth_header = request.headers.get('Authorization')
    if auth_header is None or ' ' not in auth_header:
        raise Unauthorized("Authorization header must be provided and start with 'Bearer'")

    # 解析认证信息
    auth_scheme, auth_token = auth_header.split(None, 1)
    auth_scheme = auth_scheme.lower()

    # 验证认证方案是否为Bearer
    if auth_scheme != 'bearer':
        raise Unauthorized("Authorization scheme must be 'Bearer'")

    # 从数据库中查询对应的API令牌
    api_token = db.session.query(ApiToken).filter(
        ApiToken.token == auth_token,
        ApiToken.type == scope,
    ).first()

    # 验证令牌的有效性
    if not api_token:
        raise Unauthorized("Access token is invalid")

    api_token.last_used_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.session.commit()

    return api_token


def create_or_update_end_user_for_user_id(app_model: App, user_id: Optional[str] = None) -> EndUser:
    """
    根据用户ID创建或更新会话终端。
    
    参数:
    - app_model: App 类型，代表一个应用模型，用于确定操作的租户和应用ID。
    - user_id: 可选的字符串类型，用户的ID。如果未提供，则默认为'DEFAULT-USER'。

    返回值:
    - EndUser 类型，表示创建或更新后的会话终端对象。
    """
    # 如果未提供user_id，则默认设置为'DEFAULT-USER'
    if not user_id:
        user_id = 'DEFAULT-USER'

    # 尝试从数据库中查询已存在的会话终端
    end_user = db.session.query(EndUser) \
        .filter(
        EndUser.tenant_id == app_model.tenant_id,
        EndUser.app_id == app_model.id,
        EndUser.session_id == user_id,
        EndUser.type == 'service_api'
    ).first()

    # 如果未找到对应的会话终端，则创建新的会话终端并添加到数据库
    if end_user is None:
        end_user = EndUser(
            tenant_id=app_model.tenant_id,
            app_id=app_model.id,
            type='service_api',
            is_anonymous=True if user_id == 'DEFAULT-USER' else False,
            session_id=user_id
        )
        db.session.add(end_user)
        db.session.commit()

    return end_user


class DatasetApiResource(Resource):
    method_decorators = [validate_dataset_token]
