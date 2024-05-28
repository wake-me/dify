from functools import wraps

from flask import request
from flask_restful import Resource
from werkzeug.exceptions import BadRequest, NotFound, Unauthorized

from controllers.web.error import WebSSOAuthRequiredError
from extensions.ext_database import db
from libs.passport import PassportService
from models.model import App, EndUser, Site
from services.feature_service import FeatureService


def validate_jwt_token(view=None):
    """
    验证JWT令牌的装饰器。
    
    如果提供了view参数，则直接返回一个装饰后的视图函数；
    如果没有提供view参数，则返回一个装饰器函数。
    
    参数:
    - view: 可选，视图函数，如果提供，则直接对其进行装饰。
    
    返回:
    - 如果提供了view，则返回装饰后的视图函数；
      否则返回一个需要传入视图函数的装饰器。
    """
    def decorator(view):
        @wraps(view)
        def decorated(*args, **kwargs):
            # 解码JWT令牌，获取应用模型和终端用户信息
            app_model, end_user = decode_jwt_token()

            # 调用原始视图函数，并传入解码后的信息
            return view(app_model, end_user, *args, **kwargs)
        return decorated
    if view:
        return decorator(view)
    return decorator


def decode_jwt_token():
    system_features = FeatureService.get_system_features()

    try:
        auth_header = request.headers.get('Authorization')
        if auth_header is None:
            raise Unauthorized('Authorization header is missing.')

        if ' ' not in auth_header:
            raise Unauthorized('Invalid Authorization header format. Expected \'Bearer <api-key>\' format.')

        auth_scheme, tk = auth_header.split(None, 1)
        auth_scheme = auth_scheme.lower()

        if auth_scheme != 'bearer':
            raise Unauthorized('Invalid Authorization header format. Expected \'Bearer <api-key>\' format.')
        decoded = PassportService().verify(tk)
        app_code = decoded.get('app_code')
        app_model = db.session.query(App).filter(App.id == decoded['app_id']).first()
        site = db.session.query(Site).filter(Site.code == app_code).first()
        if not app_model:
            raise NotFound()
        if not app_code or not site:
            raise BadRequest('Site URL is no longer valid.')
        if app_model.enable_site is False:
            raise BadRequest('Site is disabled.')
        end_user = db.session.query(EndUser).filter(EndUser.id == decoded['end_user_id']).first()
        if not end_user:
            raise NotFound()

        _validate_web_sso_token(decoded, system_features)

        return app_model, end_user
    except Unauthorized as e:
        if system_features.sso_enforced_for_web:
            raise WebSSOAuthRequiredError()

        raise Unauthorized(e.description)


def _validate_web_sso_token(decoded, system_features):
    # Check if SSO is enforced for web, and if the token source is not SSO, raise an error and redirect to SSO login
    if system_features.sso_enforced_for_web:
        source = decoded.get('token_source')
        if not source or source != 'sso':
            raise WebSSOAuthRequiredError()

    # Check if SSO is not enforced for web, and if the token source is SSO, raise an error and redirect to normal passport login
    if not system_features.sso_enforced_for_web:
        source = decoded.get('token_source')
        if source and source == 'sso':
            raise Unauthorized('sso token expired.')


class WebApiResource(Resource):
    """
    继承自Resource，为Web API提供资源访问控制。
    
    属性:
    - method_decorators: 列表，包含用于方法装饰器的列表，例如JWT令牌验证。
    """
    method_decorators = [validate_jwt_token]