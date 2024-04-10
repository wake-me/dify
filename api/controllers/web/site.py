
from flask import current_app
from flask_restful import fields, marshal_with
from werkzeug.exceptions import Forbidden

from controllers.web import api
from controllers.web.wraps import WebApiResource
from extensions.ext_database import db
from models.model import Site
from services.feature_service import FeatureService


class AppSiteApi(WebApiResource):
    """应用站点资源类，用于管理应用站点的API接口。"""

    # 定义模型配置的字段
    model_config_fields = {
        'opening_statement': fields.String,  # 开场白，使用字符串类型
        'suggested_questions': fields.Raw(attribute='suggested_questions_list'),  # 建议的问题，以原始数据类型存储，列表形式
        'suggested_questions_after_answer': fields.Raw(attribute='suggested_questions_after_answer_dict'),  # 回答后的建议问题，以原始数据类型存储，字典形式
        'more_like_this': fields.Raw(attribute='more_like_this_dict'),  # 类似的推荐，以原始数据类型存储，字典形式
        'model': fields.Raw(attribute='model_dict'),  # 模型配置，以原始数据类型存储，字典形式
        'user_input_form': fields.Raw(attribute='user_input_form_list'),  # 用户输入表单，以原始数据类型存储，列表形式
        'pre_prompt': fields.String,  # 提示信息，使用字符串类型
    }

    # 定义站点信息字段
    # 该字典定义了站点信息的各种字段及其类型，用于构建站点的元数据。
    site_fields = {
        'title': fields.String,  # 站点标题，字符串类型
        'icon': fields.String,  # 站点图标链接，字符串类型
        'icon_background': fields.String,  # 图标背景颜色，字符串类型
        'description': fields.String,  # 站点描述，字符串类型
        'copyright': fields.String,  # 知识产权声明，字符串类型
        'privacy_policy': fields.String,  # 隐私政策链接，字符串类型
        'default_language': fields.String,  # 默认语言，字符串类型
        'prompt_public': fields.Boolean  # 是否公开提示，布尔类型
    }

    # 定义应用信息字段，包含嵌套的站点和模型配置信息
    app_fields = {
        'app_id': fields.String,
        'end_user_id': fields.String,
        'enable_site': fields.Boolean,
        'site': fields.Nested(site_fields),
        'model_config': fields.Nested(model_config_fields, allow_null=True),
        'plan': fields.String,
        'can_replace_logo': fields.Boolean,
        'custom_config': fields.Raw(attribute='custom_config'),
    }

    @marshal_with(app_fields)
    def get(self, app_model, end_user):
        """
        获取应用站点信息。

        :param app_model: 应用模型实例，用于查询应用的详细信息。
        :param end_user: 终端用户实例，用于查询用户信息。
        :return: 返回应用站点的信息详情。
        """
        # 查询站点信息
        site = db.session.query(Site).filter(Site.app_id == app_model.id).first()

        if not site:
            raise Forbidden()  # 如果查询不到站点信息，抛出权限异常

        # 获取是否允许替换标志的特性
        can_replace_logo = FeatureService.get_features(app_model.tenant_id).can_replace_logo

        # 返回应用站点信息实例
        return AppSiteInfo(app_model.tenant, app_model, site, end_user.id, can_replace_logo)

api.add_resource(AppSiteApi, '/site')


class AppSiteInfo:
    """用于存储站点信息的类。"""

    def __init__(self, tenant, app, site, end_user, can_replace_logo):
        """
        初始化AppSiteInfo实例。

        :param tenant: 租户对象，包含租户相关信息
        :param app: 应用对象，包含应用的基本信息和配置
        :param site: 站点对象，包含站点的配置和状态
        :param end_user: 终端用户标识，用于标识应用的使用者
        :param can_replace_logo: 布尔值，指示是否允许替换应用的Logo
        """

        # 初始化基本属性
        self.app_id = app.id
        self.end_user_id = end_user
        self.enable_site = app.enable_site
        self.site = site
        self.model_config = None
        self.plan = tenant.plan
        self.can_replace_logo = can_replace_logo

        # 如果允许替换Logo，则配置自定义参数
        if can_replace_logo:
            base_url = current_app.config.get('FILES_URL')  # 获取文件服务的基础URL
            remove_webapp_brand = tenant.custom_config_dict.get('remove_webapp_brand', False)  # 是否移除Web应用的品牌标识
            replace_webapp_logo = f'{base_url}/files/workspaces/{tenant.id}/webapp-logo' if tenant.custom_config_dict.get('replace_webapp_logo') else None  # 替换Web应用Logo的URL
            self.custom_config = {
                'remove_webapp_brand': remove_webapp_brand,
                'replace_webapp_logo': replace_webapp_logo,
            }
