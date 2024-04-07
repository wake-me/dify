import uuid

from flask import request
from flask_restful import Resource
from werkzeug.exceptions import NotFound, Unauthorized

from controllers.web import api
from extensions.ext_database import db
from libs.passport import PassportService
from models.model import App, EndUser, Site


class PassportResource(Resource):
    """访问令牌资源基类。"""
    
    def get(self):
        """
        处理客户端的GET请求，验证X-App-Code头部信息，并生成访问令牌（access token）返回给客户端。
        
        验证流程包括：
        - 验证X-App-Code头部是否存在；
        - 根据X-App-Code查询站点信息，并验证站点状态是否为正常；
        - 查询关联的应用信息，并验证应用状态是否为正常以及是否启用该站点。
        
        如果验证通过，将创建一个匿名的终端用户记录，并返回访问令牌。
        
        返回值:
            - 包含访问令牌的字典。
            
        异常:
            - Unauthorized: 当X-App-Code头部缺失时抛出。
            - NotFound: 当对应的站点或应用信息不存在或状态不正常时抛出。
        """
        
        # 验证X-App-Code头部信息
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
        
        # 创建终端用户实例，并保存到数据库
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
