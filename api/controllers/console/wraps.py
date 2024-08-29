import json
from functools import wraps

from flask import abort, request
from flask_login import current_user

from configs import dify_config
from controllers.console.workspace.error import AccountNotInitializedError
from services.feature_service import FeatureService
from services.operation_service import OperationService


def account_initialization_required(view):
    """
    装饰器函数，用于检查用户账号是否已经初始化。
    
    参数:
    - view: 待装饰的视图函数。
    
    返回值:
    - 返回一个封装了原视图函数的装饰器函数。
    """
    @wraps(view)
    def decorated(*args, **kwargs):
        # 检查账号初始化状态
        account = current_user

        if account.status == "uninitialized":
            raise AccountNotInitializedError()

        return view(*args, **kwargs)  # 如果账号已初始化，执行原视图函数

    return decorated


def only_edition_cloud(view):
    """
    一个装饰器函数，用于确保被装饰的视图函数只在‘CLOUD’版本中可用。
    如果当前应用的版本不是‘CLOUD’，则返回404错误。

    :param view: 需要被装饰的视图函数
    :return: 被装饰后的视图函数
    """
    @wraps(view)
    def decorated(*args, **kwargs):
        if dify_config.EDITION != "CLOUD":
            abort(404)

        # 执行并返回原始视图函数
        return view(*args, **kwargs)

    return decorated


def only_edition_self_hosted(view):
    """
    一个装饰器函数，用于确保只有在配置中的'EDITION'为'SELF_HOSTED'时，才允许访问被装饰的视图函数。
    
    参数:
    - view: 将要被装饰的视图函数。
    
    返回值:
    - 返回一个封装了原视图函数的装饰器函数。
    """
    @wraps(view)
    def decorated(*args, **kwargs):
        if dify_config.EDITION != "SELF_HOSTED":
            abort(404)

        # 调用原始视图函数并返回其结果
        return view(*args, **kwargs)

    return decorated


def cloud_edition_billing_resource_check(resource: str):
    def interceptor(view):
        @wraps(view)
        def decorated(*args, **kwargs):
            # 获取当前用户的资源限制信息
            features = FeatureService.get_features(current_user.current_tenant_id)
            # 如果启用了计费功能，则进行资源限制检查
            if features.billing.enabled:
                # 各资源的限制和当前使用量
                members = features.members
                apps = features.apps
                vector_space = features.vector_space
                documents_upload_quota = features.documents_upload_quota
                annotation_quota_limit = features.annotation_quota_limit
                if resource == "members" and 0 < members.limit <= members.size:
                    abort(403, "The number of members has reached the limit of your subscription.")
                elif resource == "apps" and 0 < apps.limit <= apps.size:
                    abort(403, "The number of apps has reached the limit of your subscription.")
                elif resource == "vector_space" and 0 < vector_space.limit <= vector_space.size:
                    abort(403, "The capacity of the vector space has reached the limit of your subscription.")
                elif resource == "documents" and 0 < documents_upload_quota.limit <= documents_upload_quota.size:
                    # The api of file upload is used in the multiple places, so we need to check the source of the request from datasets
                    source = request.args.get("source")
                    if source == "datasets":
                        abort(403, "The number of documents has reached the limit of your subscription.")
                    else:
                        return view(*args, **kwargs)
                elif resource == "workspace_custom" and not features.can_replace_logo:
                    abort(403, "The workspace custom feature has reached the limit of your subscription.")
                elif resource == "annotation" and 0 < annotation_quota_limit.limit < annotation_quota_limit.size:
                    abort(403, "The annotation quota has reached the limit of your subscription.")
                else:
                    return view(*args, **kwargs)

            return view(*args, **kwargs)

        return decorated

    return interceptor


def cloud_edition_billing_knowledge_limit_check(resource: str):
    def interceptor(view):
        @wraps(view)
        def decorated(*args, **kwargs):
            # 获取当前用户的租户的特性服务
            features = FeatureService.get_features(current_user.current_tenant_id)
            # 检查计费功能是否启用
            if features.billing.enabled:
                if resource == "add_segment":
                    if features.billing.subscription.plan == "sandbox":
                        abort(
                            403,
                            "To unlock this feature and elevate your Dify experience, please upgrade to a paid plan.",
                        )
                else:
                    # 如果资源未超出限制，正常执行视图函数
                    return view(*args, **kwargs)

            # 如果计费功能未启用，正常执行视图函数
            return view(*args, **kwargs)

        return decorated

    return interceptor


def cloud_utm_record(view):
    """
    一个用于装饰视图函数的装饰器，主要功能是在视图执行前记录UTM（来源追踪）信息。
    
    :param view: 被装饰的视图函数
    :return: 包装后的视图函数，该函数在执行原视图功能前会尝试记录UTM信息。
    """
    @wraps(view)
    def decorated(*args, **kwargs):
        try:
            # 获取当前用户所属租户的特性服务
            features = FeatureService.get_features(current_user.current_tenant_id)

            # 检查是否启用了账单功能
            if features.billing.enabled:
                utm_info = request.cookies.get("utm_info")

                # 如果存在UTM信息，则进行记录
                if utm_info:
                    utm_info = json.loads(utm_info)  # 将UTM信息从JSON格式转换为Python对象
                    # 记录UTM信息
                    OperationService.record_utm(current_user.current_tenant_id, utm_info)
        except Exception as e:
            # 如果过程中发生异常，则静默处理，不执行任何操作
            pass
        # 执行原视图函数，并返回其返回值
        return view(*args, **kwargs)

    return decorated
