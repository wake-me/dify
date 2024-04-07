from functools import wraps

from flask import request
from flask_restful import Resource
from werkzeug.exceptions import NotFound, Unauthorized

from extensions.ext_database import db
from libs.passport import PassportService
from models.model import App, EndUser, Site


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
    """
    解码JWT令牌，验证其有效性，并返回应用模型和终端用户信息。
    
    返回:
    - app_model: 应用模型对象。
    - end_user: 终端用户对象。
    
    抛出:
    - Unauthorized: 如果认证信息缺失、格式错误或无效。
    - NotFound: 如果相关的应用模型或终端用户不存在。
    """
    # 从请求头中获取认证信息
    auth_header = request.headers.get('Authorization')
    if auth_header is None:
        raise Unauthorized('Authorization header is missing.')

    if ' ' not in auth_header:
        raise Unauthorized('Invalid Authorization header format. Expected \'Bearer <api-key>\' format.')
    
    # 分解认证信息，验证认证方案
    auth_scheme, tk = auth_header.split(None, 1)
    auth_scheme = auth_scheme.lower()

    if auth_scheme != 'bearer':
        raise Unauthorized('Invalid Authorization header format. Expected \'Bearer <api-key>\' format.')
    # 使用PassportService验证令牌
    decoded = PassportService().verify(tk)
    app_code = decoded.get('app_code')
    app_model = db.session.query(App).filter(App.id == decoded['app_id']).first()
    site = db.session.query(Site).filter(Site.code == app_code).first()
    if not app_model:
        raise NotFound()
    if not app_code or not site:
        raise Unauthorized('Site URL is no longer valid.')
    if app_model.enable_site is False:
        raise Unauthorized('Site is disabled.')
    end_user = db.session.query(EndUser).filter(EndUser.id == decoded['end_user_id']).first()
    if not end_user:
        raise NotFound()

    return app_model, end_user

class WebApiResource(Resource):
    """
    继承自Resource，为Web API提供资源访问控制。
    
    属性:
    - method_decorators: 列表，包含用于方法装饰器的列表，例如JWT令牌验证。
    """
    method_decorators = [validate_jwt_token]