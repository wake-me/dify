from flask_login import current_user
from flask_restful import Resource, marshal_with, reqparse
from werkzeug.exceptions import Forbidden, NotFound

from constants.languages import supported_language
from controllers.console import api
from controllers.console.app import _get_app
from controllers.console.setup import setup_required
from controllers.console.wraps import account_initialization_required
from extensions.ext_database import db
from fields.app_fields import app_site_fields
from libs.login import login_required
from models.model import Site


def parse_app_site_args():
    """
    解析应用程序站点参数。

    从请求的JSON体中解析应用程序站点的配置参数，包括标题、图标、图标背景、描述、默认语言、自定义域名、版权声明、隐私政策、自定义令牌策略、是否提示公开等信息。

    返回值:
        dict: 包含所有解析出的参数及其值的字典。
    """
    parser = reqparse.RequestParser()
    # 添加应用程序标题参数
    parser.add_argument('title', type=str, required=False, location='json')
    # 添加应用程序图标参数
    parser.add_argument('icon', type=str, required=False, location='json')
    # 添加应用程序图标背景颜色参数
    parser.add_argument('icon_background', type=str, required=False, location='json')
    # 添加应用程序描述参数
    parser.add_argument('description', type=str, required=False, location='json')
    # 添加应用程序默认语言参数，需为支持的语言
    parser.add_argument('default_language', type=supported_language, required=False, location='json')
    # 添加应用程序自定义域名参数
    parser.add_argument('customize_domain', type=str, required=False, location='json')
    # 添加应用程序版权声明参数
    parser.add_argument('copyright', type=str, required=False, location='json')
    # 添加应用程序隐私政策链接参数
    parser.add_argument('privacy_policy', type=str, required=False, location='json')
    # 添加应用程序自定义令牌策略参数，可选值为'must', 'allow', 'not_allow'
    parser.add_argument('customize_token_strategy', type=str, choices=['must', 'allow', 'not_allow'],
                        required=False,
                        location='json')
    # 添加是否提示用户公开应用程序的参数
    parser.add_argument('prompt_public', type=bool, required=False, location='json')
    # 解析并返回所有参数
    return parser.parse_args()


class AppSite(Resource):
    """
    AppSite 类，用于处理应用站点相关的API请求。

    继承自 Resource，使用了多个装饰器来确保请求的设置、登录状态、账户初始化状态以及数据的正确格式。
    """

    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(app_site_fields)
    def post(self, app_id):
        """
        处理创建或更新应用站点信息的POST请求。

        需要用户登录且角色为管理员或所有者才能访问。会根据请求中提供的参数更新相应的应用和站点信息。

        参数:
        - app_id: 应用的唯一标识符。

        返回值:
        - 更新后的站点信息。
        """
        args = parse_app_site_args()  # 解析请求参数

        app_id = str(app_id)  # 确保app_id为字符串类型
        app_model = _get_app(app_id)  # 获取应用模型

        # 检查当前用户是否有权限进行操作
        if not current_user.is_admin_or_owner:
            raise Forbidden()  # 如果不是管理员或所有者，则抛出权限异常

        # 从数据库中获取对应的站点信息
        site = db.session.query(Site). \
            filter(Site.app_id == app_model.id). \
            one_or_404()

        # 遍历需要更新的属性列表，并根据请求参数更新站点和应用信息
        for attr_name in [
            'title',
            'icon',
            'icon_background',
            'description',
            'default_language',
            'customize_domain',
            'copyright',
            'privacy_policy',
            'customize_token_strategy',
            'prompt_public'
        ]:
            value = args.get(attr_name)
            if value is not None:
                setattr(site, attr_name, value)  # 更新站点信息
                # 根据属性名称更新应用信息
                if attr_name == 'title':
                    app_model.name = value
                elif attr_name == 'icon':
                    app_model.icon = value
                elif attr_name == 'icon_background':
                    app_model.icon_background = value

        db.session.commit()  # 提交数据库事务

        return site  # 返回更新后的站点信息


class AppSiteAccessTokenReset(Resource):
    """
    用于重置应用站点的访问令牌的接口类。

    方法:
    - post: 重置指定应用的访问令牌。

    参数:
    - app_id: 应用的唯一标识符。

    返回值:
    - 返回更新后的站点信息。
    """

    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(app_site_fields)
    def post(self, app_id):
        app_id = str(app_id)  # 将传入的app_id转换为字符串格式
        app_model = _get_app(app_id)  # 获取指定app_id的应用模型

        # 检查当前用户在ta表中的角色是否为管理员或所有者
        if not current_user.is_admin_or_owner:
            raise Forbidden()  # 如果不是，抛出权限禁止的异常

        # 查询数据库，尝试根据应用ID获取站点信息
        site = db.session.query(Site).filter(Site.app_id == app_model.id).first()

        if not site:
            raise NotFound  # 如果找不到对应的站点信息，抛出未找到的异常

        # 生成新的16位代码，并更新数据库中的站点代码
        site.code = Site.generate_code(16)
        db.session.commit()  # 提交数据库事务

        return site  # 返回更新后的站点信息


api.add_resource(AppSite, '/apps/<uuid:app_id>/site')
api.add_resource(AppSiteAccessTokenReset, '/apps/<uuid:app_id>/site/access-token-reset')
