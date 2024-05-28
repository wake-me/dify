from flask_login import current_user
from flask_restful import Resource, fields, marshal_with, reqparse

from constants.languages import languages
from controllers.console import api
from controllers.console.wraps import account_initialization_required
from libs.login import login_required
from services.recommended_app_service import RecommendedAppService

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
    'app': fields.Nested(app_fields, attribute='app'),
    'app_id': fields.String,
    'description': fields.String(attribute='description'),
    'copyright': fields.String,
    'privacy_policy': fields.String,
    'custom_disclaimer': fields.String,
    'category': fields.String,
    'position': fields.Integer,
    'is_listed': fields.Boolean
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
        # language args
        parser = reqparse.RequestParser()
        parser.add_argument('language', type=str, location='args')
        args = parser.parse_args()

        if args.get('language') and args.get('language') in languages:
            language_prefix = args.get('language')
        elif current_user and current_user.interface_language:
            language_prefix = current_user.interface_language
        else:
            language_prefix = languages[0]

        return RecommendedAppService.get_recommended_apps_and_categories(language_prefix)


class RecommendedAppApi(Resource):
    @login_required
    @account_initialization_required
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
        return RecommendedAppService.get_recommend_app_detail(app_id)


api.add_resource(RecommendedAppListApi, '/explore/apps')
api.add_resource(RecommendedAppApi, '/explore/apps/<uuid:app_id>')
