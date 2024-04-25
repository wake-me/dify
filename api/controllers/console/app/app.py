import json
import uuid

from flask_login import current_user
from flask_restful import Resource, inputs, marshal, marshal_with, reqparse
from werkzeug.exceptions import BadRequest, Forbidden, abort

from controllers.console import api
from controllers.console.app.wraps import get_app_model
from controllers.console.setup import setup_required
from controllers.console.wraps import account_initialization_required, cloud_edition_billing_resource_check
from core.tools.tool_manager import ToolManager
from core.tools.utils.configuration import ToolParameterConfigurationManager
from fields.app_fields import (
    app_detail_fields,
    app_detail_fields_with_site,
    app_pagination_fields,
)
from libs.login import login_required
from models.model import App, AppMode, AppModelConfig
from services.app_service import AppService
from services.tag_service import TagService

ALLOW_CREATE_APP_MODES = ['chat', 'agent-chat', 'advanced-chat', 'workflow', 'completion']

class AppListApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        """Get app list"""
        def uuid_list(value):
            try:
                return [str(uuid.UUID(v)) for v in value.split(',')]
            except ValueError:
                abort(400, message="Invalid UUID format in tag_ids.")
        parser = reqparse.RequestParser()
        parser.add_argument('page', type=inputs.int_range(1, 99999), required=False, default=1, location='args')
        parser.add_argument('limit', type=inputs.int_range(1, 100), required=False, default=20, location='args')
        parser.add_argument('mode', type=str, choices=['chat', 'workflow', 'agent-chat', 'channel', 'all'], default='all', location='args', required=False)
        parser.add_argument('name', type=str, location='args', required=False)
        parser.add_argument('tag_ids', type=uuid_list, location='args', required=False)

        args = parser.parse_args()

        # get app list
        app_service = AppService()
        app_pagination = app_service.get_paginate_apps(current_user.current_tenant_id, args)
        if not app_pagination:
            return {'data': [], 'total': 0, 'page': 1, 'limit': 20, 'has_more': False}

        return marshal(app_pagination, app_pagination_fields)

    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(app_detail_fields)
    @cloud_edition_billing_resource_check('apps')
    def post(self):
        """
        创建一个新的应用程序。

        参数:
        - name: 应用程序的名称，类型为字符串，必需。
        - mode: 应用程序的模式，可选值为'completion', 'chat', 'assistant'，类型为字符串，必需。
        - icon: 应用程序的图标链接，类型为字符串，可选。
        - icon_background: 图标背景颜色，类型为字符串，可选。
        - model_config: 模型配置字典，包括模型的提供者和名称，类型为字典，可选。

        返回值:
        - 创建的应用程序对象和HTTP状态码201。
        
        此接口需要用户登录、账号初始化、并且具有管理员或所有者权限。同时，会根据提供的model_config验证和配置模型，
        如果没有提供model_config，则会使用默认模型配置。
        """

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('name', type=str, required=True, location='json')
        parser.add_argument('description', type=str, location='json')
        parser.add_argument('mode', type=str, choices=ALLOW_CREATE_APP_MODES, location='json')
        parser.add_argument('icon', type=str, location='json')
        parser.add_argument('icon_background', type=str, location='json')
        args = parser.parse_args()

        # 检查当前用户是否有权限创建应用
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        if 'mode' not in args or args['mode'] is None:
            raise BadRequest("mode is required")

        app_service = AppService()
        app = app_service.create_app(current_user.current_tenant_id, args, current_user)

        return app, 201


class AppImportApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(app_detail_fields_with_site)
    @cloud_edition_billing_resource_check('apps')
    def post(self):
        """Import app"""
        # The role of the current user in the ta table must be admin or owner
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        parser = reqparse.RequestParser()
        parser.add_argument('data', type=str, required=True, nullable=False, location='json')
        parser.add_argument('name', type=str, location='json')
        parser.add_argument('description', type=str, location='json')
        parser.add_argument('icon', type=str, location='json')
        parser.add_argument('icon_background', type=str, location='json')
        args = parser.parse_args()

        app_service = AppService()
        app = app_service.import_app(current_user.current_tenant_id, args['data'], args, current_user)

        return app, 201


class AppApi(Resource):
    # AppApi类：用于处理应用相关的API请求

    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model
    @marshal_with(app_detail_fields_with_site)
    def get(self, app_model):
        """Get app detail"""
        app_service = AppService()

        app_model = app_service.get_app(app_model)

        return app_model

    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model
    @marshal_with(app_detail_fields_with_site)
    def put(self, app_model):
        """Update app"""
        parser = reqparse.RequestParser()
        parser.add_argument('name', type=str, required=True, nullable=False, location='json')
        parser.add_argument('description', type=str, location='json')
        parser.add_argument('icon', type=str, location='json')
        parser.add_argument('icon_background', type=str, location='json')
        args = parser.parse_args()

        app_service = AppService()
        app_model = app_service.update_app(app_model, args)

        return app_model

    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model
    def delete(self, app_model):
        """Delete app"""
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        app_service = AppService()
        app_service.delete_app(app_model)

        return {'result': 'success'}, 204


class AppCopyApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model
    @marshal_with(app_detail_fields_with_site)
    def post(self, app_model):
        """Copy app"""
        # The role of the current user in the ta table must be admin or owner
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        parser = reqparse.RequestParser()
        parser.add_argument('name', type=str, location='json')
        parser.add_argument('description', type=str, location='json')
        parser.add_argument('icon', type=str, location='json')
        parser.add_argument('icon_background', type=str, location='json')
        args = parser.parse_args()

        app_service = AppService()
        data = app_service.export_app(app_model)
        app = app_service.import_app(current_user.current_tenant_id, data, args, current_user)

        return app, 201


class AppExportApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model
    def get(self, app_model):
        """Export app"""
        app_service = AppService()

        return {
            "data": app_service.export_app(app_model)
        }


class AppNameApi(Resource):
    """
    AppNameApi类，用于处理应用名称的API请求

    继承自Resource，提供post方法用于更新应用名称

    方法:
        post: 更新指定应用的名称
    """

    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model
    @marshal_with(app_detail_fields)
    def post(self, app_model):
        parser = reqparse.RequestParser()
        # 添加'name'参数解析规则，要求必须提供，且位于JSON体中
        parser.add_argument('name', type=str, required=True, location='json')
        # 解析请求体中的参数
        args = parser.parse_args()

        app_service = AppService()
        app_model = app_service.update_app_name(app_model, args.get('name'))

        return app_model

class AppIconApi(Resource):
    """
    应用图标接口类，用于处理应用图标的更改
    
    属性:
        Resource: 父类，提供RESTful API资源的基本方法
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model
    @marshal_with(app_detail_fields)
    def post(self, app_model):
        parser = reqparse.RequestParser()
        parser.add_argument('icon', type=str, location='json')
        parser.add_argument('icon_background', type=str, location='json')
        args = parser.parse_args()  # 解析请求参数

        app_service = AppService()
        app_model = app_service.update_app_icon(app_model, args.get('icon'), args.get('icon_background'))

        return app_model


class AppSiteStatus(Resource):
    """
    应用站点状态管理类，用于处理应用的站点启用状态的更新请求。
    
    方法:
    - post: 更新指定应用的站点启用状态。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model
    @marshal_with(app_detail_fields)
    def post(self, app_model):
        parser = reqparse.RequestParser()
        parser.add_argument('enable_site', type=bool, required=True, location='json')
        args = parser.parse_args()

        app_service = AppService()
        app_model = app_service.update_app_site_status(app_model, args.get('enable_site'))

        return app_model


class AppApiStatus(Resource):
    """
    应用API状态管理类，用于处理应用的API启用状态的更新。
    
    方法:
    - post: 更新指定应用的API启用状态。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model
    @marshal_with(app_detail_fields)
    def post(self, app_model):
        parser = reqparse.RequestParser()
        parser.add_argument('enable_api', type=bool, required=True, location='json')
        args = parser.parse_args()

        app_service = AppService()
        app_model = app_service.update_app_api_status(app_model, args.get('enable_api'))

        return app_model


api.add_resource(AppListApi, '/apps')
api.add_resource(AppImportApi, '/apps/import')
api.add_resource(AppApi, '/apps/<uuid:app_id>')
api.add_resource(AppCopyApi, '/apps/<uuid:app_id>/copy')
api.add_resource(AppExportApi, '/apps/<uuid:app_id>/export')
api.add_resource(AppNameApi, '/apps/<uuid:app_id>/name')
api.add_resource(AppIconApi, '/apps/<uuid:app_id>/icon')
api.add_resource(AppSiteStatus, '/apps/<uuid:app_id>/site-enable')
api.add_resource(AppApiStatus, '/apps/<uuid:app_id>/api-enable')
