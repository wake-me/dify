import os

import requests


class OperationService:
    base_url = os.environ.get("BILLING_API_URL", "BILLING_API_URL")
    secret_key = os.environ.get("BILLING_API_SECRET_KEY", "BILLING_API_SECRET_KEY")

    @classmethod
    def _send_request(cls, method, endpoint, json=None, params=None):
        headers = {"Content-Type": "application/json", "Billing-Api-Secret-Key": cls.secret_key}

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
            "tenant_id": tenant_id,
            "utm_source": utm_info.get("utm_source", ""),
            "utm_medium": utm_info.get("utm_medium", ""),
            "utm_campaign": utm_info.get("utm_campaign", ""),
            "utm_content": utm_info.get("utm_content", ""),
            "utm_term": utm_info.get("utm_term", ""),
        }
        return cls._send_request("POST", "/tenant_utms", params=params)
