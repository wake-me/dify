from flask import current_app
from pydantic import BaseModel

from services.billing_service import BillingService


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
    # 功能模型，定义计费信息和各功能的限制
    billing: BillingModel = BillingModel()  # 计费信息，默认为BillingModel实例
    members: LimitationModel = LimitationModel(size=0, limit=1)  # 成员限制，默认大小为0，限制数量为1
    apps: LimitationModel = LimitationModel(size=0, limit=10)  # 应用限制，默认大小为0，限制数量为10
    vector_space: LimitationModel = LimitationModel(size=0, limit=5)  # 向量空间限制，默认大小为0，限制数量为5
    annotation_quota_limit: LimitationModel = LimitationModel(size=0, limit=10)  # 注解配额限制，默认大小为0，限制数量为10
    documents_upload_quota: LimitationModel = LimitationModel(size=0, limit=50)  # 文档上传配额限制，默认大小为0，限制数量为50
    docs_processing: str = 'standard'  # 文档处理类型，默认为'standard'
    can_replace_logo: bool = False  # 是否可以替换标志，默认为False


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
    def _fulfill_params_from_env(cls, features: FeatureModel):
        """
        从环境变量填充功能模型的参数。

        :param features: 要填充参数的FeatureModel实例。
        """
        features.can_replace_logo = current_app.config['CAN_REPLACE_LOGO']  # 是否可以替换标志的值来自环境变量

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

        # 填充各功能限制信息
        features.members.size = billing_info['members']['size']
        features.members.limit = billing_info['members']['limit']

        features.apps.size = billing_info['apps']['size']
        features.apps.limit = billing_info['apps']['limit']

        features.vector_space.size = billing_info['vector_space']['size']
        features.vector_space.limit = billing_info['vector_space']['limit']

        features.documents_upload_quota.size = billing_info['documents_upload_quota']['size']
        features.documents_upload_quota.limit = billing_info['documents_upload_quota']['limit']

        features.annotation_quota_limit.size = billing_info['annotation_quota_limit']['size']
        features.annotation_quota_limit.limit = billing_info['annotation_quota_limit']['limit']

        features.docs_processing = billing_info['docs_processing']
        features.can_replace_logo = billing_info['can_replace_logo']

