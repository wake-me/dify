from flask import current_app
from pydantic import BaseModel

from services.billing_service import BillingService
from services.enterprise.enterprise_service import EnterpriseService


class SubscriptionModel(BaseModel):
    # 订阅模型，定义订阅计划和间隔
    plan: str = 'sandbox'  # 订阅计划，默认为'sandbox'
    interval: str = ''  # 订阅间隔，默认为空


class BillingModel(BaseModel):
    # 计费模型，定义计费是否启用及订阅信息
    enabled: bool = False  # 计费是否启用，默认为False
    subscription: SubscriptionModel = SubscriptionModel()  # 订阅信息，默认为SubscriptionModel实例


class LimitationModel(BaseModel):
    # 限制模型，定义大小和限制数量
    size: int = 0  # 大小，默认为0
    limit: int = 0  # 限制数量，默认为0


class FeatureModel(BaseModel):
    billing: BillingModel = BillingModel()
    members: LimitationModel = LimitationModel(size=0, limit=1)
    apps: LimitationModel = LimitationModel(size=0, limit=10)
    vector_space: LimitationModel = LimitationModel(size=0, limit=5)
    annotation_quota_limit: LimitationModel = LimitationModel(size=0, limit=10)
    documents_upload_quota: LimitationModel = LimitationModel(size=0, limit=50)
    docs_processing: str = 'standard'
    can_replace_logo: bool = False
    model_load_balancing_enabled: bool = False


class SystemFeatureModel(BaseModel):
    sso_enforced_for_signin: bool = False
    sso_enforced_for_signin_protocol: str = ''
    sso_enforced_for_web: bool = False
    sso_enforced_for_web_protocol: str = ''


class FeatureService:
    """
    功能服务类，用于获取和处理功能信息。
    """

    @classmethod
    def get_features(cls, tenant_id: str) -> FeatureModel:
        """
        根据租户ID获取功能模型实例。

        :param tenant_id: 租户ID，用于从计费服务获取计费信息。
        :return: 返回一个填充好的FeatureModel实例。
        """
        features = FeatureModel()

        cls._fulfill_params_from_env(features)  # 从环境变量填充参数

        if current_app.config['BILLING_ENABLED']:
            cls._fulfill_params_from_billing_api(features, tenant_id)  # 如果计费启用，则从计费API填充参数

        return features

    @classmethod
    def get_system_features(cls) -> SystemFeatureModel:
        system_features = SystemFeatureModel()

        if current_app.config['ENTERPRISE_ENABLED']:
            cls._fulfill_params_from_enterprise(system_features)

        return system_features

    @classmethod
    def _fulfill_params_from_env(cls, features: FeatureModel):
        features.can_replace_logo = current_app.config['CAN_REPLACE_LOGO']
        features.model_load_balancing_enabled = current_app.config['MODEL_LB_ENABLED']

    @classmethod
    def _fulfill_params_from_billing_api(cls, features: FeatureModel, tenant_id: str):
        """
        从计费API填充功能模型的参数。

        :param features: 要填充参数的FeatureModel实例。
        :param tenant_id: 租户ID，用于从计费服务获取计费信息。
        """
        billing_info = BillingService.get_info(tenant_id)  # 从计费服务获取计费信息

        # 填充计费和订阅信息
        features.billing.enabled = billing_info['enabled']
        features.billing.subscription.plan = billing_info['subscription']['plan']
        features.billing.subscription.interval = billing_info['subscription']['interval']

        if 'members' in billing_info:
            features.members.size = billing_info['members']['size']
            features.members.limit = billing_info['members']['limit']

        if 'apps' in billing_info:
            features.apps.size = billing_info['apps']['size']
            features.apps.limit = billing_info['apps']['limit']

        if 'vector_space' in billing_info:
            features.vector_space.size = billing_info['vector_space']['size']
            features.vector_space.limit = billing_info['vector_space']['limit']

        if 'documents_upload_quota' in billing_info:
            features.documents_upload_quota.size = billing_info['documents_upload_quota']['size']
            features.documents_upload_quota.limit = billing_info['documents_upload_quota']['limit']

        if 'annotation_quota_limit' in billing_info:
            features.annotation_quota_limit.size = billing_info['annotation_quota_limit']['size']
            features.annotation_quota_limit.limit = billing_info['annotation_quota_limit']['limit']

        if 'docs_processing' in billing_info:
            features.docs_processing = billing_info['docs_processing']

        if 'can_replace_logo' in billing_info:
            features.can_replace_logo = billing_info['can_replace_logo']

        if 'model_load_balancing_enabled' in billing_info:
            features.model_load_balancing_enabled = billing_info['model_load_balancing_enabled']

    @classmethod
    def _fulfill_params_from_enterprise(cls, features):
        enterprise_info = EnterpriseService.get_info()

        features.sso_enforced_for_signin = enterprise_info['sso_enforced_for_signin']
        features.sso_enforced_for_signin_protocol = enterprise_info['sso_enforced_for_signin_protocol']
        features.sso_enforced_for_web = enterprise_info['sso_enforced_for_web']
        features.sso_enforced_for_web_protocol = enterprise_info['sso_enforced_for_web_protocol']
