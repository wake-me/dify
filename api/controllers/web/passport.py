import uuid

from flask import request
from flask_restful import Resource
from werkzeug.exceptions import NotFound, Unauthorized

from controllers.web import api
from controllers.web.error import WebSSOAuthRequiredError
from extensions.ext_database import db
from libs.passport import PassportService
from models.model import App, EndUser, Site
from services.feature_service import FeatureService


class PassportResource(Resource):
    """访问令牌资源基类。"""
    
    def get(self):

        system_features = FeatureService.get_system_features()
        if system_features.sso_enforced_for_web:
            raise WebSSOAuthRequiredError()

        app_code = request.headers.get('X-App-Code')
        if app_code is None:
            raise Unauthorized('X-App-Code header is missing.')

        # 查询站点信息并验证站点状态
        site = db.session.query(Site).filter(
            Site.code == app_code,
            Site.status == 'normal'
        ).first()
        if not site:
            raise NotFound()
        
        # 查询应用信息并验证应用状态及是否启用该站点
        app_model = db.session.query(App).filter(App.id == site.app_id).first()
        if not app_model or app_model.status != 'normal' or not app_model.enable_site:
            raise NotFound()

        end_user = EndUser(
            tenant_id=app_model.tenant_id,
            app_id=app_model.id,
            type='browser',
            is_anonymous=True,
            session_id=generate_session_id(),
        )

        db.session.add(end_user)
        db.session.commit()

        # 准备令牌负载并发行令牌
        payload = {
            "iss": site.app_id,
            'sub': 'Web API Passport',
            'app_id': site.app_id,
            'app_code': app_code,
            'end_user_id': end_user.id,
        }

        tk = PassportService().issue(payload)

        # 返回包含访问令牌的响应
        return {
            'access_token': tk,
        }


api.add_resource(PassportResource, '/passport')


def generate_session_id():
    """
    生成一个唯一的会话ID。

    该函数没有参数。

    返回值:
        str: 一个唯一的会话ID字符串。
    """
    while True:
        # 生成一个随机的UUID作为会话ID
        session_id = str(uuid.uuid4())
        # 检查数据库中是否存在相同的会话ID
        existing_count = db.session.query(EndUser) \
            .filter(EndUser.session_id == session_id).count()
        # 如果不存在相同的会话ID，则返回这个ID
        if existing_count == 0:
            return session_id
