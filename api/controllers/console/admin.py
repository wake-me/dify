import os
from functools import wraps

from flask import request
from flask_restful import Resource, reqparse
from werkzeug.exceptions import NotFound, Unauthorized

from constants.languages import supported_language
from controllers.console import api
from controllers.console.wraps import only_edition_cloud
from extensions.ext_database import db
from models.model import App, InstalledApp, RecommendedApp


def admin_required(view):
    """
    装饰器函数，用于确保只有拥有有效管理员API密钥的请求才能访问被装饰的视图函数。
    
    参数:
    - view: 被装饰的视图函数。
    
    返回值:
    - 返回一个封装了原视图函数的装饰器函数，该函数在原视图函数执行前增加了API密钥验证的逻辑。
    """
    @wraps(view)
    def decorated(*args, **kwargs):
        # 检查环境变量中是否存在有效的管理员API密钥
        if not os.getenv('ADMIN_API_KEY'):
            raise Unauthorized('API key is invalid.')

        # 检查请求头中是否包含Authorization字段
        auth_header = request.headers.get('Authorization')
        if auth_header is None:
            raise Unauthorized('Authorization header is missing.')

        # 检查Authorization头部的格式是否正确
        if ' ' not in auth_header:
            raise Unauthorized('Invalid Authorization header format. Expected \'Bearer <api-key>\' format.')

        # 分解Authorization头部，获取认证方案和令牌
        auth_scheme, auth_token = auth_header.split(None, 1)
        auth_scheme = auth_scheme.lower()

        # 检查认证方案是否为预期的"Bearer"
        if auth_scheme != 'bearer':
            raise Unauthorized('Invalid Authorization header format. Expected \'Bearer <api-key>\' format.')

        # 检查传入的API密钥是否与环境变量中的管理员API密钥匹配
        if os.getenv('ADMIN_API_KEY') != auth_token:
            raise Unauthorized('API key is invalid.')

        # 如果API密钥验证通过，则执行原视图函数
        return view(*args, **kwargs)

    return decorated


class InsertExploreAppListApi(Resource):
    """
    插入探索应用列表的API接口类
    该类用于处理后台管理员添加或更新推荐应用列表的请求
    """
    @only_edition_cloud
    @admin_required
    def post(self):
        """
        处理POST请求，用于添加或更新探索页面的推荐应用信息
        参数:
        - 通过JSON体接收app_id, desc, copyright, privacy_policy, language, category, position等参数
        其中app_id, language, category, position为必需参数
        返回值:
        - 成功添加或更新应用信息时，返回200或201状态码和包含'result'字段的JSON，值为'success'
        - 若应用不存在，则返回404状态码和错误信息
        """
        parser = reqparse.RequestParser()
        # 解析请求中所需的参数
        parser.add_argument('app_id', type=str, required=True, nullable=False, location='json')
        parser.add_argument('desc', type=str, location='json')
        parser.add_argument('copyright', type=str, location='json')
        parser.add_argument('privacy_policy', type=str, location='json')
        parser.add_argument('language', type=supported_language, required=True, nullable=False, location='json')
        parser.add_argument('category', type=str, required=True, nullable=False, location='json')
        parser.add_argument('position', type=int, required=True, nullable=False, location='json')
        args = parser.parse_args()

        # 根据app_id查询应用信息
        app = App.query.filter(App.id == args['app_id']).first()
        if not app:
            raise NotFound(f'App \'{args["app_id"]}\' is not found')

        site = app.site
        # 根据应用是否有站点，来确定推荐应用的描述、版权和隐私政策信息
        if not site:
            desc = args['desc'] if args['desc'] else ''
            copy_right = args['copyright'] if args['copyright'] else ''
            privacy_policy = args['privacy_policy'] if args['privacy_policy'] else ''
        else:
            desc = site.description if site.description else \
                args['desc'] if args['desc'] else ''
            copy_right = site.copyright if site.copyright else \
                args['copyright'] if args['copyright'] else ''
            privacy_policy = site.privacy_policy if site.privacy_policy else \
                args['privacy_policy'] if args['privacy_policy']  else ''

        # 查询推荐应用信息，如果不存在则创建新的推荐应用记录
        recommended_app = RecommendedApp.query.filter(RecommendedApp.app_id == args['app_id']).first()
        if not recommended_app:
            # 新建推荐应用记录并提交到数据库
            recommended_app = RecommendedApp(
                app_id=app.id,
                description=desc,
                copyright=copy_right,
                privacy_policy=privacy_policy,
                language=args['language'],
                category=args['category'],
                position=args['position']
            )

            db.session.add(recommended_app)

            app.is_public = True
            db.session.commit()

            return {'result': 'success'}, 201
        else:
            # 如果推荐应用已存在，则更新相关信息并提交到数据库
            recommended_app.description = desc
            recommended_app.copyright = copy_right
            recommended_app.privacy_policy = privacy_policy
            recommended_app.language = args['language']
            recommended_app.category = args['category']
            recommended_app.position = args['position']

            app.is_public = True

            db.session.commit()

            return {'result': 'success'}, 200


class InsertExploreAppApi(Resource):
    """
    插入探索应用API的类，提供删除指定应用的功能。
    
    方法:
    - delete: 删除指定的应用。
    
    参数:
    - app_id: 要删除的应用的ID。
    
    返回值:
    - 一个包含结果信息的字典和HTTP状态码。成功删除时，返回{'result': 'success'}和状态码204。
    """
    
    @only_edition_cloud
    @admin_required
    def delete(self, app_id):
        # 尝试根据app_id查询推荐应用
        recommended_app = RecommendedApp.query.filter(RecommendedApp.app_id == str(app_id)).first()
        if not recommended_app:
            # 如果推荐应用不存在，直接返回成功
            return {'result': 'success'}, 204

        # 查询关联的App信息
        app = App.query.filter(App.id == recommended_app.app_id).first()
        if app:
            # 如果App存在，将其公开状态设置为False
            app.is_public = False

        # 查询所有非应用所有者租户安装的该应用实例
        installed_apps = InstalledApp.query.filter(
            InstalledApp.app_id == recommended_app.app_id,
            InstalledApp.tenant_id != InstalledApp.app_owner_tenant_id
        ).all()

        # 删除所有非应用所有者租户安装的该应用实例
        for installed_app in installed_apps:
            db.session.delete(installed_app)

        # 删除推荐的应用
        db.session.delete(recommended_app)
        # 提交数据库事务
        db.session.commit()

        # 返回成功信息和状态码204
        return {'result': 'success'}, 204


api.add_resource(InsertExploreAppListApi, '/admin/insert-explore-apps')
api.add_resource(InsertExploreAppApi, '/admin/insert-explore-apps/<uuid:app_id>')
