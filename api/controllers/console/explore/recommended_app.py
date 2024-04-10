from flask_login import current_user
from flask_restful import Resource, fields, marshal_with
from sqlalchemy import and_

from constants.languages import languages
from controllers.console import api
from controllers.console.app.error import AppNotFoundError
from controllers.console.wraps import account_initialization_required
from extensions.ext_database import db
from libs.login import login_required
from models.model import App, InstalledApp, RecommendedApp
from services.account_service import TenantService

# 定义应用程序的字段结构
app_fields = {
    'id': fields.String,  # 应用程序的唯一标识符
    'name': fields.String,  # 应用程序的名称
    'mode': fields.String,  # 应用程序的模式
    'icon': fields.String,  # 应用程序的图标链接
    'icon_background': fields.String  # 应用程序图标背景颜色或图片链接
}

# 定义推荐应用程序的字段结构，包括应用程序的详细信息和状态
recommended_app_fields = {
    'app': fields.Nested(app_fields, attribute='app'),  # 包含应用程序详细信息的嵌套字段
    'app_id': fields.String,  # 应用程序的ID，可能与'id'字段重复，取决于使用场景
    'description': fields.String(attribute='description'),  # 应用程序的描述
    'copyright': fields.String,  # 应用程序的版权信息
    'privacy_policy': fields.String,  # 应用程序的隐私政策链接或内容
    'category': fields.String,  # 应用程序所属的类别
    'position': fields.Integer,  # 应用程序在推荐列表中的位置
    'is_listed': fields.Boolean,  # 应用程序是否在公开列表中显示
    'install_count': fields.Integer,  # 应用程序的安装次数
    'installed': fields.Boolean,  # 表示该应用程序是否已安装
    'editable': fields.Boolean,  # 表示应用程序的配置是否可以被编辑
    'is_agent': fields.Boolean  # 表示应用程序是否由代理发布
}

# 定义推荐应用程序列表的字段结构，包含多个推荐应用程序和类别信息
recommended_app_list_fields = {
    'recommended_apps': fields.List(fields.Nested(recommended_app_fields)),  # 推荐应用程序的列表
    'categories': fields.List(fields.String)  # 可用的应用程序类别列表
}

class RecommendedAppListApi(Resource):
    """
    提供推荐应用列表的API接口。
    
    要求用户登录且账号初始化完成后才能访问，返回的数据通过字段列表进行格式化。
    """
    
    @login_required
    @account_initialization_required
    @marshal_with(recommended_app_list_fields)
    def get(self):
        """
        获取推荐应用列表。
        
        根据当前用户的界面语言选择相应的推荐应用，如果无则默认为系统设置的第一语言。
        返回的推荐应用信息包括应用的基本信息、是否已安装、是否可编辑等。
        
        返回值:
            - 包含推荐应用信息和类别列表的字典。
        """
        
        # 根据用户界面语言设置获取推荐应用的语言前缀
        language_prefix = current_user.interface_language if current_user.interface_language else languages[0]

        # 查询与用户界面语言匹配的推荐应用
        recommended_apps = db.session.query(RecommendedApp).filter(
            RecommendedApp.is_listed == True,
            RecommendedApp.language == language_prefix
        ).all()

        # 如果没有找到匹配的语言，则查询默认语言的推荐应用
        if len(recommended_apps) == 0:
            recommended_apps = db.session.query(RecommendedApp).filter(
                RecommendedApp.is_listed == True,
                RecommendedApp.language == languages[0]
            ).all()

        categories = set()  # 用于存储所有推荐应用的类别，以去重
        # 获取当前用户的角色
        current_user.role = TenantService.get_user_role(current_user, current_user.current_tenant)
        recommended_apps_result = []
        for recommended_app in recommended_apps:
            # 检查应用是否已安装
            installed = db.session.query(InstalledApp).filter(
                and_(
                    InstalledApp.app_id == recommended_app.app_id,
                    InstalledApp.tenant_id == current_user.current_tenant_id
                )
            ).first() is not None

            app = recommended_app.app
            if not app or not app.is_public:  # 过滤掉不存在或非公开的应用
                continue

            site = app.site
            if not site:  # 过滤掉没有网站信息的应用
                continue

            # 构建并存储每个推荐应用的信息
            recommended_app_result = {
                'id': recommended_app.id,
                'app': app,
                'app_id': recommended_app.app_id,
                'description': site.description,
                'copyright': site.copyright,
                'privacy_policy': site.privacy_policy,
                'category': recommended_app.category,
                'position': recommended_app.position,
                'is_listed': recommended_app.is_listed,
                'install_count': recommended_app.install_count,
                'installed': installed,
                'editable': current_user.role in ['owner', 'admin'],
                "is_agent": app.is_agent
            }
            recommended_apps_result.append(recommended_app_result)

            categories.add(recommended_app.category)  # 累加类别信息

        return {'recommended_apps': recommended_apps_result, 'categories': list(categories)}


class RecommendedAppApi(Resource):
    """
    推荐应用API类，用于处理推荐应用的相关接口请求。
    
    属性:
    - model_config_fields: 定义了模型配置信息的字段。
    - app_simple_detail_fields: 定义了应用简单详情信息的字段。
    """
    
    model_config_fields = {
        # 模型配置字段定义
        'opening_statement': fields.String,
        'suggested_questions': fields.Raw(attribute='suggested_questions_list'),
        'suggested_questions_after_answer': fields.Raw(attribute='suggested_questions_after_answer_dict'),
        'more_like_this': fields.Raw(attribute='more_like_this_dict'),
        'model': fields.Raw(attribute='model_dict'),
        'user_input_form': fields.Raw(attribute='user_input_form_list'),
        'pre_prompt': fields.String,
        'agent_mode': fields.Raw(attribute='agent_mode_dict'),
    }

    app_simple_detail_fields = {
        # 应用简单详情字段定义
        'id': fields.String,
        'name': fields.String,
        'icon': fields.String,
        'icon_background': fields.String,
        'mode': fields.String,
        'app_model_config': fields.Nested(model_config_fields),
    }

    @login_required
    @account_initialization_required
    @marshal_with(app_simple_detail_fields)
    def get(self, app_id):
        """
        获取指定应用的简单详情信息。
        
        参数:
        - app_id: 应用的ID标识符。
        
        返回值:
        - 返回应用的简单详情信息。
        
        异常:
        - AppNotFoundError: 当指定的应用不存在或不在推荐列表中时抛出。
        """
        app_id = str(app_id)

        # 检查应用是否在推荐列表中
        recommended_app = db.session.query(RecommendedApp).filter(
            RecommendedApp.is_listed == True,
            RecommendedApp.app_id == app_id
        ).first()

        if not recommended_app:
            raise AppNotFoundError

        # 获取应用详细信息
        app = db.session.query(App).filter(App.id == app_id).first()
        if not app or not app.is_public:
            raise AppNotFoundError

        return app


api.add_resource(RecommendedAppListApi, '/explore/apps')
api.add_resource(RecommendedAppApi, '/explore/apps/<uuid:app_id>')
