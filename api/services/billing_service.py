import os

import requests

from extensions.ext_database import db
from models.account import TenantAccountJoin


class BillingService:
    # 类`BillingService`负责处理账单服务相关的API请求。
    base_url = os.environ.get('BILLING_API_URL', 'BILLING_API_URL')
    secret_key = os.environ.get('BILLING_API_SECRET_KEY', 'BILLING_API_SECRET_KEY')

    @classmethod
    def get_info(cls, tenant_id: str):
        """
        获取指定租户的账单信息。
        
        :param tenant_id: 租户ID，用于标识特定的租户。
        :return: 返回租户的账单信息。
        """
        params = {'tenant_id': tenant_id}

        billing_info = cls._send_request('GET', '/subscription/info', params=params)

        return billing_info

    @classmethod
    def get_subscription(cls, plan: str,
                         interval: str,
                         prefilled_email: str = '',
                         tenant_id: str = ''):
        """
        获取订阅支付链接。
        
        :param plan: 订阅计划。
        :param interval: 订阅间隔（如：月，年）。
        :param prefilled_email: 预填充的电子邮件地址，可选。
        :param tenant_id: 租户ID，可选。
        :return: 返回订阅的支付链接。
        """
        params = {
            'plan': plan,
            'interval': interval,
            'prefilled_email': prefilled_email,
            'tenant_id': tenant_id
        }
        return cls._send_request('GET', '/subscription/payment-link', params=params)

    @classmethod
    def get_model_provider_payment_link(cls,
                                        provider_name: str,
                                        tenant_id: str,
                                        account_id: str,
                                        prefilled_email: str):
        """
        获取模型提供者的支付链接。
        
        :param provider_name: 模型提供者名称。
        :param tenant_id: 租户ID。
        :param account_id: 账户ID。
        :param prefilled_email: 预填充的电子邮件地址。
        :return: 返回模型提供者的支付链接。
        """
        params = {
            'provider_name': provider_name,
            'tenant_id': tenant_id,
            'account_id': account_id,
            'prefilled_email': prefilled_email
        }
        return cls._send_request('GET', '/model-provider/payment-link', params=params)

    @classmethod
    def get_invoices(cls, prefilled_email: str = '', tenant_id: str = ''):
        """
        获取发票信息。
        
        :param prefilled_email: 预填充的电子邮件地址，可选。
        :param tenant_id: 租户ID，可选。
        :return: 返回发票信息。
        """
        params = {
            'prefilled_email': prefilled_email,
            'tenant_id': tenant_id
        }
        return cls._send_request('GET', '/invoices', params=params)

    @classmethod
    def _send_request(cls, method, endpoint, json=None, params=None):
        """
        发送API请求。
        
        :param method: HTTP请求方法（如：GET，POST）。
        :param endpoint: API的端点。
        :param json: 请求体中的JSON数据，可选。
        :param params: 查询参数，可选。
        :return: 返回API响应的JSON数据。
        """
        headers = {
            "Content-Type": "application/json",
            "Billing-Api-Secret-Key": cls.secret_key
        }

        url = f"{cls.base_url}{endpoint}"
        response = requests.request(method, url, json=json, params=params, headers=headers)

        return response.json()

    @staticmethod
    def is_tenant_owner_or_admin(current_user):
        """
        检查当前用户是否为租户的所有者或管理员。
        
        :param current_user: 当前用户对象。
        :raises ValueError: 如果用户不是所有者或管理员，则抛出异常。
        """
        tenant_id = current_user.current_tenant_id

        join = db.session.query(TenantAccountJoin).filter(
            TenantAccountJoin.tenant_id == tenant_id,
            TenantAccountJoin.account_id == current_user.id
        ).first()

        if join.role not in ['owner', 'admin']:
            raise ValueError('Only team owner or team admin can perform this action')