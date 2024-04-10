import json
import logging
from datetime import datetime

from flask_login import current_user
from flask_restful import Resource, abort, inputs, marshal_with, reqparse
from werkzeug.exceptions import Forbidden

from constants.languages import demo_model_templates, languages
from constants.model_template import model_templates
from controllers.console import api
from controllers.console.app.error import AppNotFoundError, ProviderNotInitializeError
from controllers.console.setup import setup_required
from controllers.console.wraps import account_initialization_required, cloud_edition_billing_resource_check
from core.errors.error import LLMBadRequestError, ProviderTokenNotInitError
from core.model_manager import ModelManager
from core.model_runtime.entities.model_entities import ModelType
from core.provider_manager import ProviderManager
from events.app_event import app_was_created, app_was_deleted
from extensions.ext_database import db
from fields.app_fields import (
    app_detail_fields,
    app_detail_fields_with_site,
    app_pagination_fields,
    template_list_fields,
)
from libs.login import login_required
from models.model import App, AppModelConfig, Site
from services.app_model_config_service import AppModelConfigService
from core.tools.utils.configuration import ToolParameterConfigurationManager
from core.tools.tool_manager import ToolManager
from core.entities.application_entities import AgentToolEntity

def _get_app(app_id, tenant_id):
    """
    从数据库中获取指定的应用。
    
    参数:
    app_id: int - 应用的ID。
    tenant_id: int - 租户的ID。
    
    返回值:
    App - 查询到的应用对象。
    
    抛出:
    AppNotFoundError: 如果指定的应用不存在，则抛出此异常。
    """
    # 从数据库中查询符合条件的第一个应用
    app = db.session.query(App).filter(App.id == app_id, App.tenant_id == tenant_id).first()
    if not app:
        # 如果找不到应用，抛出异常
        raise AppNotFoundError
    return app

class AppListApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(app_pagination_fields)
    def get(self):
        """
        获取应用列表的接口
        参数:
            page: 请求的页数，默认为1
            limit: 每页显示的数量，默认为20
            mode: 查询模式，可选'chat'、'completion'或'all'，默认为'all'
                   'chat'只返回聊天模式的应用
                   'completion'只返回完成模式的应用
                   'all'返回所有模式的应用
            name: 应用名称，可选，支持模糊搜索
        返回值:
            根据分页参数和过滤条件返回应用列表的JSON响应
        """

        # 初始化请求参数解析器
        parser = reqparse.RequestParser()
        parser.add_argument('page', type=inputs.int_range(1, 99999), required=False, default=1, location='args')
        parser.add_argument('limit', type=inputs.int_range(1, 100), required=False, default=20, location='args')
        parser.add_argument('mode', type=str, choices=['chat', 'completion', 'all'], default='all', location='args', required=False)
        parser.add_argument('name', type=str, location='args', required=False)
        args = parser.parse_args()

        # 默认过滤条件
        filters = [
            App.tenant_id == current_user.current_tenant_id,
            App.is_universal == False
        ]

        # 根据模式参数添加额外的过滤条件
        if args['mode'] == 'completion':
            filters.append(App.mode == 'completion')
        elif args['mode'] == 'chat':
            filters.append(App.mode == 'chat')
        else:
            pass  # 不做额外过滤

        # 如果指定了应用名称，则添加名称模糊匹配的过滤条件
        if 'name' in args and args['name']:
            filters.append(App.name.ilike(f'%{args["name"]}%'))

        # 使用数据库分页查询符合条件的应用
        app_models = db.paginate(
            db.select(App).where(*filters).order_by(App.created_at.desc()),
            page=args['page'],
            per_page=args['limit'],
            error_out=False
        )

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
        parser.add_argument('mode', type=str, choices=['completion', 'chat', 'assistant'], location='json')
        parser.add_argument('icon', type=str, location='json')
        parser.add_argument('icon_background', type=str, location='json')
        parser.add_argument('model_config', type=dict, location='json')
        args = parser.parse_args()

        # 检查当前用户是否有权限创建应用
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        try:
            provider_manager = ProviderManager()
            default_model_entity = provider_manager.get_default_model(
                tenant_id=current_user.current_tenant_id,
                model_type=ModelType.LLM
            )
        except (ProviderTokenNotInitError, LLMBadRequestError):
            default_model_entity = None
        except Exception as e:
            logging.exception(e)
            default_model_entity = None

        # 验证和处理模型配置
        if args['model_config'] is not None:
            # 验证配置的合法性
            model_config_dict = args['model_config']

            # 获取提供者配置
            provider_manager = ProviderManager()
            provider_configurations = provider_manager.get_configurations(current_user.current_tenant_id)

            # 获取可用模型列表
            available_models = provider_configurations.get_models(
                model_type=ModelType.LLM,
                only_active=True
            )

            # 检查所选模型是否可用，不可用则使用默认模型
            available_models_names = [f'{model.provider.provider}.{model.model}' for model in available_models]
            provider_model = f"{model_config_dict['model']['provider']}.{model_config_dict['model']['name']}"
            if provider_model not in available_models_names:
                if not default_model_entity:
                    raise ProviderNotInitializeError(
                        "No Default System Reasoning Model available. Please configure "
                        "in the Settings -> Model Provider.")
                else:
                    model_config_dict["model"]["provider"] = default_model_entity.provider.provider
                    model_config_dict["model"]["name"] = default_model_entity.model

            model_configuration = AppModelConfigService.validate_configuration(
                tenant_id=current_user.current_tenant_id,
                account=current_user,
                config=model_config_dict,
                app_mode=args['mode']
            )

            # 创建App对象并配置模型
            app = App(
                enable_site=True,
                enable_api=True,
                is_demo=False,
                api_rpm=0,
                api_rph=0,
                status='normal'
            )

            app_model_config = AppModelConfig()
            app_model_config = app_model_config.from_model_config_dict(model_configuration)
        else:
            # 使用默认模式配置
            if 'mode' not in args or args['mode'] is None:
                abort(400, message="mode is required")

            model_config_template = model_templates[args['mode'] + '_default']

            app = App(**model_config_template['app'])
            app_model_config = AppModelConfig(**model_config_template['model_config'])

            # 尝试获取默认模型实例
            model_manager = ModelManager()
            try:
                model_instance = model_manager.get_default_model_instance(
                    tenant_id=current_user.current_tenant_id,
                    model_type=ModelType.LLM
                )
            except ProviderTokenNotInitError:
                model_instance = None

            if model_instance:
                model_dict = app_model_config.model_dict
                model_dict['provider'] = model_instance.provider
                model_dict['name'] = model_instance.model
                app_model_config.model = json.dumps(model_dict)

        # 设置应用属性并保存到数据库
        app.name = args['name']
        app.mode = args['mode']
        app.icon = args['icon']
        app.icon_background = args['icon_background']
        app.tenant_id = current_user.current_tenant_id

        db.session.add(app)
        db.session.flush()

        app_model_config.app_id = app.id
        db.session.add(app_model_config)
        db.session.flush()

        app.app_model_config_id = app_model_config.id

        # 创建站点并保存
        account = current_user

        site = Site(
            app_id=app.id,
            title=app.name,
            default_language=account.interface_language,
            customize_token_strategy='not_allow',
            code=Site.generate_code(16)
        )

        db.session.add(site)
        db.session.commit()

        # 发送应用创建事件
        app_was_created.send(app)

        return app, 201
    

class AppTemplateApi(Resource):
    """
    App模板API接口类，用于提供应用演示模板的获取功能。

    属性:
        Resource: 父类，提供RESTful API接口的基本方法。
    """

    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(template_list_fields)
    def get(self):
        """
        获取应用演示模板的接口。

        路径参数:
            无

        返回值:
            dict: 包含模板数据的字典。
        """
        # 获取当前登录的用户账户信息
        account = current_user
        # 获取用户设置的界面语言
        interface_language = account.interface_language

        # 尝试根据用户界面语言获取对应的演示模板，若无则使用默认语言的模板
        templates = demo_model_templates.get(interface_language)
        if not templates:
            templates = demo_model_templates.get(languages[0])  # 使用默认语言模板

        return {'data': templates}  # 返回模板数据

class AppApi(Resource):
    # AppApi类：用于处理应用相关的API请求

    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(app_detail_fields_with_site)
    def get(self, app_id):
        """
        获取应用详情
        :param app_id: 应用ID，用于标识要获取详情的应用
        :return: 返回应用的详细信息，包括经过解密和掩码处理的工具参数配置
        """
        app_id = str(app_id)  # 将传入的app_id转换为字符串类型
        app: App = _get_app(app_id, current_user.current_tenant_id)  # 根据app_id和当前用户所属的租户ID获取App实例

        # 获取原始应用模型配置
        model_config: AppModelConfig = app.app_model_config
        agent_mode = model_config.agent_mode_dict

        # 遍历并解密代理工具参数（如果为密文）
        for tool in agent_mode.get('tools') or []:
            if not isinstance(tool, dict) or len(tool.keys()) <= 3:
                continue
            agent_tool_entity = AgentToolEntity(**tool)
            # 获取工具运行时配置
            try:
                tool_runtime = ToolManager.get_agent_tool_runtime(
                    tenant_id=current_user.current_tenant_id,
                    agent_tool=agent_tool_entity,
                    agent_callback=None
                )
                manager = ToolParameterConfigurationManager(
                    tenant_id=current_user.current_tenant_id,
                    tool_runtime=tool_runtime,
                    provider_name=agent_tool_entity.provider_id,
                    provider_type=agent_tool_entity.provider_type,
                )

                # 获取解密后的参数并进行掩码处理
                if agent_tool_entity.tool_parameters:
                    parameters = manager.decrypt_tool_parameters(agent_tool_entity.tool_parameters or {})
                    masked_parameter = manager.mask_tool_parameters(parameters or {})
                else:
                    masked_parameter = {}

                # 使用掩码后的参数覆盖工具参数配置
                tool['tool_parameters'] = masked_parameter
            except Exception as e:
                pass  # 忽略处理过程中的任何异常

        # 将代理模式配置覆盖为json格式字符串
        model_config.agent_mode = json.dumps(agent_mode)

        return app  # 返回处理后的应用实例

    @setup_required
    @login_required
    @account_initialization_required
    def delete(self, app_id):
        """
        删除应用
        :param app_id: 应用的ID，可以是整数或字符串
        :return: 一个包含删除结果的字典和HTTP状态码。成功删除时返回{'result': 'success'}, 204状态码。
        """
        app_id = str(app_id)  # 确保app_id为字符串类型

        # 检查当前用户是否有权限删除应用，如果不是管理员或应用所有者，则抛出Forbidden异常
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        # 根据app_id和当前用户所在的租户ID获取应用对象
        app = _get_app(app_id, current_user.current_tenant_id)

        # 在数据库会话中删除应用对象，并提交事务
        db.session.delete(app)
        db.session.commit()

        # 待完成：考虑删除相关的数据，如配置信息、站点信息、API令牌、对话、消息等

        # 发送app被删除的信号，让其他监听者知道这一事件
        app_was_deleted.send(app)

        return {'result': 'success'}, 204


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
    @marshal_with(app_detail_fields)
    def post(self, app_id):
        """
        更新应用的名称

        参数:
            app_id: 应用的唯一标识符

        返回值:
            更新后的应用对象
        """

        # 将app_id转换为字符串格式
        app_id = str(app_id)
        # 根据app_id和当前用户的租户ID获取应用对象
        app = _get_app(app_id, current_user.current_tenant_id)

        # 创建请求解析器，用于解析JSON请求体中的参数
        parser = reqparse.RequestParser()
        # 添加'name'参数解析规则，要求必须提供，且位于JSON体中
        parser.add_argument('name', type=str, required=True, location='json')
        # 解析请求体中的参数
        args = parser.parse_args()

        # 更新应用的名称和更新时间
        app.name = args.get('name')
        app.updated_at = datetime.utcnow()
        # 提交数据库事务，保存更改
        db.session.commit()
        return app

class AppIconApi(Resource):
    """
    应用图标接口类，用于处理应用图标的更改
    
    属性:
        Resource: 父类，提供RESTful API资源的基本方法
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(app_detail_fields)
    def post(self, app_id):
        """
        更新应用的图标和图标背景色
        
        方法通过POST请求更新指定应用的图标和图标背景色。
        
        参数:
            app_id (int): 应用的ID，需要转换为字符串格式
            
        返回:
            应用对象，包含更新后的图标和图标背景色信息
        """
        app_id = str(app_id)  # 将app_id转换为字符串格式
        app = _get_app(app_id, current_user.current_tenant_id)  # 获取指定的应用对象

        parser = reqparse.RequestParser()  # 创建请求解析器
        # 添加请求体中的图标和图标背景色参数
        parser.add_argument('icon', type=str, location='json')
        parser.add_argument('icon_background', type=str, location='json')
        args = parser.parse_args()  # 解析请求参数

        # 更新应用的图标和图标背景色，并记录更新时间
        app.icon = args.get('icon')
        app.icon_background = args.get('icon_background')
        app.updated_at = datetime.utcnow()
        db.session.commit()  # 提交数据库事务，保存更改

        return app  # 返回更新后的应用对象


class AppSiteStatus(Resource):
    """
    应用站点状态管理类，用于处理应用的站点启用状态的更新请求。
    
    方法:
    - post: 更新指定应用的站点启用状态。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(app_detail_fields)
    def post(self, app_id):
        """
        更新应用的站点启用状态。
        
        参数:
        - app_id: 应用的唯一标识符。
        
        返回值:
        - 更新后的应用对象。
        
        异常:
        - AppNotFoundError: 当指定的应用不存在时抛出。
        """
        # 解析请求中的参数
        parser = reqparse.RequestParser()
        parser.add_argument('enable_site', type=bool, required=True, location='json')
        args = parser.parse_args()
        
        # 根据app_id和当前用户所属的租户ID查询应用
        app_id = str(app_id)
        app = db.session.query(App).filter(App.id == app_id, App.tenant_id == current_user.current_tenant_id).first()
        if not app:
            raise AppNotFoundError  # 如果应用不存在，则抛出异常
        
        # 如果请求中的启用状态与应用当前状态相同，则直接返回应用对象
        if args.get('enable_site') == app.enable_site:
            return app
        
        # 更新应用的启用状态和更新时间，然后提交到数据库
        app.enable_site = args.get('enable_site')
        app.updated_at = datetime.utcnow()
        db.session.commit()
        return app


class AppApiStatus(Resource):
    """
    应用API状态管理类，用于处理应用的API启用状态的更新。
    
    方法:
    - post: 更新指定应用的API启用状态。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(app_detail_fields)
    def post(self, app_id):
        """
        更新应用的API启用状态。
        
        参数:
        - app_id: 应用的唯一标识符。
        
        返回值:
        - 更新后的应用对象。
        """
        
        # 解析请求中的参数
        parser = reqparse.RequestParser()
        parser.add_argument('enable_api', type=bool, required=True, location='json')
        args = parser.parse_args()

        app_id = str(app_id)  # 将app_id转换为字符串，以统一处理
        # 根据app_id和当前用户所属的租户ID获取应用对象
        app = _get_app(app_id, current_user.current_tenant_id)

        # 如果请求中的API启用状态与当前状态相同，则直接返回当前应用对象
        if args.get('enable_api') == app.enable_api:
            return app

        # 更新应用的API启用状态和更新时间
        app.enable_api = args.get('enable_api')
        app.updated_at = datetime.utcnow()
        db.session.commit()  # 提交数据库事务，保存更改
        return app  # 返回更新后的应用对象


class AppCopy(Resource):
    """
    AppCopy类用于处理应用的复制功能。
    """

    @staticmethod
    def create_app_copy(app):
        """
        创建一个新的应用副本。

        参数:
        app: App对象，被复制的原始应用。

        返回值:
        返回一个新的应用对象，它是原始应用的一个副本。
        """
        # 创建应用副本并设置属性
        copy_app = App(
            name=app.name + ' copy',
            icon=app.icon,
            icon_background=app.icon_background,
            tenant_id=app.tenant_id,
            mode=app.mode,
            app_model_config_id=app.app_model_config_id,
            enable_site=app.enable_site,
            enable_api=app.enable_api,
            api_rpm=app.api_rpm,
            api_rph=app.api_rph
        )
        return copy_app

    @staticmethod
    def create_app_model_config_copy(app_config, copy_app_id):
        """
        创建一个新的应用模型配置副本。

        参数:
        app_config: AppModelConfig对象，被复制的原始应用模型配置。
        copy_app_id: int，新应用的ID。

        返回值:
        返回一个新的应用模型配置对象，它是原始配置的一个副本。
        """
        # 复制应用模型配置并设置新应用ID
        copy_app_model_config = app_config.copy()
        copy_app_model_config.app_id = copy_app_id

        return copy_app_model_config

    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(app_detail_fields)
    def post(self, app_id):
        """
        复制一个应用及其模型配置。

        参数:
        app_id: str，要被复制的应用的ID。

        返回值:
        返回复制后的新应用对象和HTTP状态码201。
        """
        # 转换应用ID为字符串格式
        app_id = str(app_id)
        # 获取要复制的应用
        app = _get_app(app_id, current_user.current_tenant_id)

        # 创建应用副本
        copy_app = self.create_app_copy(app)
        db.session.add(copy_app)

        # 查询原始应用的模型配置
        app_config = db.session.query(AppModelConfig). \
            filter(AppModelConfig.app_id == app_id). \
            one_or_none()

        if app_config:
            # 如果存在模型配置，则创建并添加模型配置副本到数据库
            copy_app_model_config = self.create_app_model_config_copy(app_config, copy_app.id)
            db.session.add(copy_app_model_config)
            db.session.commit()
            # 更新应用副本的模型配置ID
            copy_app.app_model_config_id = copy_app_model_config.id
        db.session.commit()

        # 返回应用副本和状态码201
        return copy_app, 201


api.add_resource(AppListApi, '/apps')
api.add_resource(AppTemplateApi, '/app-templates')
api.add_resource(AppApi, '/apps/<uuid:app_id>')
api.add_resource(AppCopy, '/apps/<uuid:app_id>/copy')
api.add_resource(AppNameApi, '/apps/<uuid:app_id>/name')
api.add_resource(AppIconApi, '/apps/<uuid:app_id>/icon')
api.add_resource(AppSiteStatus, '/apps/<uuid:app_id>/site-enable')
api.add_resource(AppApiStatus, '/apps/<uuid:app_id>/api-enable')
