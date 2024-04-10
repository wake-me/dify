from datetime import datetime

from flask_login import current_user
from flask_restful import Resource, inputs, marshal_with, reqparse
from sqlalchemy import and_
from werkzeug.exceptions import BadRequest, Forbidden, NotFound

from controllers.console import api
from controllers.console.explore.wraps import InstalledAppResource
from controllers.console.wraps import account_initialization_required, cloud_edition_billing_resource_check
from extensions.ext_database import db
from fields.installed_app_fields import installed_app_list_fields
from libs.login import login_required
from models.model import App, InstalledApp, RecommendedApp
from services.account_service import TenantService


class InstalledAppsListApi(Resource):
    @login_required  # 需要用户登录
    @account_initialization_required  # 账户初始化所需
    @marshal_with(installed_app_list_fields)  # 使用预定义的字段列表对返回结果进行格式化
    def get(self):
        """
        获取当前租户已安装的应用列表。

        需要用户登录且账户已初始化。返回的安装应用列表会根据用户角色和应用状态进行标记和排序。

        返回:
            - installed_apps: 一个列表，包含已安装应用的信息，如应用ID、应用名、是否被固定、最后使用时间等。
        """
        current_tenant_id = current_user.current_tenant_id  # 获取当前用户所属的租户ID
        # 从数据库查询当前租户安装的所有应用
        installed_apps = db.session.query(InstalledApp).filter(
            InstalledApp.tenant_id == current_tenant_id
        ).all()

        # 设置当前用户角色，基于其在当前租户下的角色
        current_user.role = TenantService.get_user_role(current_user, current_user.current_tenant)
        # 构建并调整应用信息列表，以适配前端需求和用户权限
        installed_apps = [
            {
                'id': installed_app.id,
                'app': installed_app.app,
                'app_owner_tenant_id': installed_app.app_owner_tenant_id,
                'is_pinned': installed_app.is_pinned,
                'last_used_at': installed_app.last_used_at,
                'editable': current_user.role in ["owner", "admin"],  # 标记应用是否可编辑
                'uninstallable': current_tenant_id == installed_app.app_owner_tenant_id,  # 标记应用是否可卸载
                'is_agent': installed_app.is_agent
            }
            for installed_app in installed_apps
        ]
        # 根据应用是否被固定、最后使用时间对应用列表进行排序
        installed_apps.sort(key=lambda app: (-app['is_pinned'],
                                             app['last_used_at'] is None,
                                             -app['last_used_at'].timestamp() if app['last_used_at'] is not None else 0))

        return {'installed_apps': installed_apps}  # 返回排序和处理后的应用列表

    @login_required  # 需要用户登录
    @account_initialization_required  # 账户初始化所需
    @cloud_edition_billing_resource_check('apps')  # 云版本账单资源检查
    def post(self):
        """
        处理应用安装请求
        参数:
        - app_id: 字符串类型，必需，指定要安装的应用ID
        返回值:
        - 一个包含成功安装消息的字典
        """

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('app_id', type=str, required=True, help='Invalid app_id')
        args = parser.parse_args()

        # 查询推荐应用信息
        recommended_app = RecommendedApp.query.filter(RecommendedApp.app_id == args['app_id']).first()
        if recommended_app is None:
            raise NotFound('App not found')  # 应用未找到异常

        # 获取当前用户所属的租户ID
        current_tenant_id = current_user.current_tenant_id
        # 查询指定ID的应用信息
        app = db.session.query(App).filter(
            App.id == args['app_id']
        ).first()

        if app is None:
            raise NotFound('App not found')  # 应用未找到异常

        # 检查应用是否为公开应用
        if not app.is_public:
            raise Forbidden('You can\'t install a non-public app')  # 无法安装非公开应用异常

        # 检查租户是否已安装该应用
        installed_app = InstalledApp.query.filter(and_(
            InstalledApp.app_id == args['app_id'],
            InstalledApp.tenant_id == current_tenant_id
        )).first()

        if installed_app is None:
            # 如果应用未被安装，则进行安装处理
            recommended_app.install_count += 1  # 更新推荐应用的安装计数

            # 创建新的已安装应用记录
            new_installed_app = InstalledApp(
                app_id=args['app_id'],
                tenant_id=current_tenant_id,
                app_owner_tenant_id=app.tenant_id,
                is_pinned=False,
                last_used_at=datetime.utcnow()
            )
            db.session.add(new_installed_app)
            db.session.commit()  # 提交数据库事务

        return {'message': 'App installed successfully'}  # 返回安装成功的消息


class InstalledAppApi(InstalledAppResource):
    """
    更新和删除已安装的应用
    使用InstalledAppResource来应用默认装饰器并获取已安装的应用
    """
    def delete(self, installed_app):
        """
        删除已安装的应用
        参数:
            - installed_app: 已安装的应用对象
        返回值:
            - 字典，包含结果信息和成功卸载的消息
        """
        # 检查应用所有者是否为当前租户，如果是，则抛出错误
        if installed_app.app_owner_tenant_id == current_user.current_tenant_id:
            raise BadRequest('You can\'t uninstall an app owned by the current tenant')

        # 从数据库会话中删除应用对象并提交更改
        db.session.delete(installed_app)
        db.session.commit()

        return {'result': 'success', 'message': 'App uninstalled successfully'}

    def patch(self, installed_app):
        """
        更新已安装应用的信息
        参数:
            - installed_app: 已安装的应用对象
        返回值:
            - 字典，包含结果信息和成功更新的消息
        """
        # 解析请求参数，获取is_pinned参数
        parser = reqparse.RequestParser()
        parser.add_argument('is_pinned', type=inputs.boolean)
        args = parser.parse_args()

        # 初始化是否提交数据库更改的标志
        commit_args = False
        # 如果请求中包含is_pinned参数，则更新应用的is_pinned属性并设置提交标志
        if 'is_pinned' in args:
            installed_app.is_pinned = args['is_pinned']
            commit_args = True

        # 如果有需要提交的参数，则提交数据库更改
        if commit_args:
            db.session.commit()

        return {'result': 'success', 'message': 'App info updated successfully'}


api.add_resource(InstalledAppsListApi, '/installed-apps')
api.add_resource(InstalledAppApi, '/installed-apps/<uuid:installed_app_id>')
