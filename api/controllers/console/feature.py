from flask_login import current_user
from flask_restful import Resource

from libs.login import login_required
from services.feature_service import FeatureService

from . import api
from .setup import setup_required
from .wraps import account_initialization_required, cloud_utm_record


class FeatureApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    @cloud_utm_record
    def get(self):
        """
        获取当前租户的特性信息。
        
        装饰器: @cloud_utm_record - 用于记录云UTM的某些操作或事件。
        
        参数: 无
        
        返回值:
        - dict: 返回当前用户当前租户的特性信息字典。
        """
        # 获取当前租户的特性信息并将其转换为字典格式返回
        return FeatureService.get_features(current_user.current_tenant_id).dict()


class SystemFeatureApi(Resource):
    def get(self):
        return FeatureService.get_system_features().dict()


api.add_resource(FeatureApi, '/features')
api.add_resource(SystemFeatureApi, '/system-features')
