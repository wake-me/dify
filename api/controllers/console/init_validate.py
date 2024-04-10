import os

from flask import current_app, session
from flask_restful import Resource, reqparse

from libs.helper import str_len
from models.model import DifySetup
from services.account_service import TenantService

from . import api
from .error import AlreadySetupError, InitValidateFailedError
from .wraps import only_edition_self_hosted


class InitValidateAPI(Resource):
    """
    初始化验证API类，用于处理系统的初始化验证请求。
    """

    def get(self):
        """
        处理获取初始化验证状态的请求。
        
        返回:
            - 如果初始化已完成，则返回 {'status': 'finished'}；
            - 如果初始化未开始，则返回 {'status': 'not_started'}。
        """
        init_status = get_init_validate_status()  # 获取初始化验证的状态
        if init_status:
            return { 'status': 'finished' }  # 如果初始化已完成，返回完成状态
        return {'status': 'not_started'}  # 如果初始化未开始，返回未开始状态

    @only_edition_self_hosted
    def post(self):
        """
        处理提交初始化验证的请求。
        
        提交的JSON数据应包含一个'password'字段，用于验证初始化密码。
        
        返回:
            - 如果验证成功，则返回 {'result': 'success'}，并设置初始化验证通过的会话状态；
            - 如果验证失败（包括已初始化或密码错误），则抛出相应的错误。
        """
        # 检查租户是否已经创建
        tenant_count = TenantService.get_tenant_count()
        if tenant_count > 0:
            raise AlreadySetupError()  # 如果租户已存在，抛出已设置错误

        parser = reqparse.RequestParser()  # 创建请求解析器
        parser.add_argument('password', type=str_len(30),
                            required=True, location='json')  # 添加密码参数
        input_password = parser.parse_args()['password']  # 解析提交的密码

        # 验证密码是否正确
        if input_password != os.environ.get('INIT_PASSWORD'):
            session['is_init_validated'] = False  # 验证失败，设置会话状态
            raise InitValidateFailedError()  # 抛出初始化验证失败错误
            
        session['is_init_validated'] = True  # 验证成功，设置会话状态
        return {'result': 'success'}, 201  # 返回成功状态和HTTP 201创建响应码

def get_init_validate_status():
    """
    获取初始化验证的状态。
    
    返回:
        - 如果当前是自托管版本，并且初始化密码已设置，则返回会话中的初始化验证状态或数据库中的第一条设置记录；
        - 如果当前不是自托管版本，总是返回True。
    """
    if current_app.config['EDITION'] == 'SELF_HOSTED':  # 如果是自托管版本
        if os.environ.get('INIT_PASSWORD'):  # 并且初始化密码已设置
            return session.get('is_init_validated') or DifySetup.query.first()  # 返回会话或数据库中的初始化状态
    
    return True  # 如果不是自托管版本，返回True表示初始化已完成或未开始

api.add_resource(InitValidateAPI, '/init')
