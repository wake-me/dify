import os

import requests


class OperationService:
    # 类变量：初始化API的基础URL和密钥
    base_url = os.environ.get('BILLING_API_URL', 'BILLING_API_URL')
    secret_key = os.environ.get('BILLING_API_SECRET_KEY', 'BILLING_API_SECRET_KEY')

    @classmethod
    def _send_request(cls, method, endpoint, json=None, params=None):
        """
        发送请求到Billing API。

        :param method: 请求方法（如：'GET', 'POST'）。
        :param endpoint: API端点路径。
        :param json: 要发送的JSON数据。
        :param params: 查询参数。
        :return: API响应的JSON数据。
        """
        # 设置请求头
        headers = {
            "Content-Type": "application/json",
            "Billing-Api-Secret-Key": cls.secret_key
        }

        # 构造完整URL
        url = f"{cls.base_url}{endpoint}"
        # 发送请求并获取响应
        response = requests.request(method, url, json=json, params=params, headers=headers)

        # 解析并返回JSON响应
        return response.json()

    @classmethod
    def record_utm(cls, tenant_id: str, utm_info: dict):
        """
        记录租户的UTM信息。

        :param tenant_id: 租户ID。
        :param utm_info: 包含UTM参数的字典。
        :return: API响应的JSON数据。
        """
        # 准备请求参数
        params = {
            'tenant_id': tenant_id,
            'utm_source': utm_info.get('utm_source', ''),
            'utm_medium': utm_info.get('utm_medium', ''),
            'utm_campaign': utm_info.get('utm_campaign', ''),
            'utm_content': utm_info.get('utm_content', ''),
            'utm_term': utm_info.get('utm_term', '')
        }
        # 发送POST请求
        return cls._send_request('POST', '/tenant_utms', params=params)
