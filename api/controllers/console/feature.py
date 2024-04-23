from flask_login import current_user
from flask_restful import Resource

from services.enterprise.enterprise_feature_service import EnterpriseFeatureService
from services.feature_service import FeatureService

from . import api
from .wraps import cloud_utm_record


class FeatureApi(Resource):
    """
    特性API类，用于通过RESTful接口获取特性信息。
    """
    
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


class EnterpriseFeatureApi(Resource):
    def get(self):
        return EnterpriseFeatureService.get_enterprise_features().dict()


api.add_resource(FeatureApi, '/features')
api.add_resource(EnterpriseFeatureApi, '/enterprise-features')
