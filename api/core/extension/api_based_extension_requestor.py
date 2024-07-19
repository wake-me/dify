import requests

from configs import dify_config
from models.api_based_extension import APIBasedExtensionPoint


class APIBasedExtensionRequestor:
    # 请求超时时间设置，包括连接超时和读取超时
    timeout: (int, int) = (5, 60)
    
    def __init__(self, api_endpoint: str, api_key: str) -> None:
        """
        初始化API请求器。

        :param api_endpoint: API的端点URL。
        :param api_key: 访问API所需的密钥。
        """
        self.api_endpoint = api_endpoint
        self.api_key = api_key

    def request(self, point: APIBasedExtensionPoint, params: dict) -> dict:
        """
        向API发送请求。

        :param point: API的请求点，指定要调用的API功能。
        :param params: 请求参数字典。
        :return: API响应的JSON数据。
        """
        # 构造请求头，包含内容类型和授权信息
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(self.api_key)
        }

        url = self.api_endpoint

        try:
            # 如果环境变量中设置了代理地址，则使用代理
            proxies = None
            if dify_config.SSRF_PROXY_HTTP_URL and dify_config.SSRF_PROXY_HTTPS_URL:
                proxies = {
                    'http': dify_config.SSRF_PROXY_HTTP_URL,
                    'https': dify_config.SSRF_PROXY_HTTPS_URL,
                }

            # 发起POST请求
            response = requests.request(
                method='POST',
                url=url,
                json={
                    'point': point.value,
                    'params': params
                },
                headers=headers,
                timeout=self.timeout,
                proxies=proxies
            )
        except requests.exceptions.Timeout:
            raise ValueError("请求超时")
        except requests.exceptions.ConnectionError:
            raise ValueError("请求连接错误")

        # 根据响应状态码判断请求是否成功
        if response.status_code != 200:
            raise ValueError("请求错误，状态码: {}, 内容: {}".format(
                response.status_code,
                response.text[:100]
            ))

        # 返回响应的JSON数据
        return response.json()