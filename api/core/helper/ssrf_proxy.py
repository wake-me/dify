"""
Proxy requests to avoid SSRF
"""

import os

from httpx import get as _get
from httpx import head as _head
from httpx import options as _options
from httpx import patch as _patch
from httpx import post as _post
from httpx import put as _put
from requests import delete as _delete

# 从环境变量中获取SSRF代理的HTTP和HTTPS URL，若未设置则默认为空字符串
SSRF_PROXY_HTTP_URL = os.getenv('SSRF_PROXY_HTTP_URL', '')
SSRF_PROXY_HTTPS_URL = os.getenv('SSRF_PROXY_HTTPS_URL', '')

# 根据SSRF代理URL构建请求库（requests）所需的代理字典，仅当两者均非空时启用代理
requests_proxies = {
    'http': SSRF_PROXY_HTTP_URL,
    'https': SSRF_PROXY_HTTPS_URL
} if SSRF_PROXY_HTTP_URL and SSRF_PROXY_HTTPS_URL else None

# 构建适用于httpx库的代理字典，格式与requests库略有不同，仅当两者均非空时启用代理
httpx_proxies = {
    'http://': SSRF_PROXY_HTTP_URL,
    'https://': SSRF_PROXY_HTTPS_URL
} if SSRF_PROXY_HTTP_URL and SSRF_PROXY_HTTPS_URL else None

# 定义一系列HTTP请求方法封装，均调用底层库并传入相应的代理设置

def get(url, *args, **kwargs):
    """
    发送GET请求。

    Args:
        url (str): 请求的URL。
        *args: 位置参数，传递给底层请求库。
        **kwargs: 关键字参数，包含请求的额外配置。

    Returns:
        返回请求的结果。
    """
    return _get(url=url, *args, proxies=httpx_proxies, **kwargs)

def post(url, *args, **kwargs):
    """
    发送POST请求。

    Args:
        url (str): 请求的URL。
        *args: 位置参数，传递给底层请求库。
        **kwargs: 关键字参数，包含请求的额外配置。

    Returns:
        返回请求的结果。
    """
    return _post(url=url, *args, proxies=httpx_proxies, **kwargs)

def put(url, *args, **kwargs):
    """
    发送PUT请求。

    Args:
        url (str): 请求的URL。
        *args: 位置参数，传递给底层请求库。
        **kwargs: 关键字参数，包含请求的额外配置。

    Returns:
        返回请求的结果。
    """
    return _put(url=url, *args, proxies=httpx_proxies, **kwargs)

def patch(url, *args, **kwargs):
    """
    发送PATCH请求。

    Args:
        url (str): 请求的URL。
        *args: 位置参数，传递给底层请求库。
        **kwargs: 关键字参数，包含请求的额外配置。

    Returns:
        返回请求的结果。
    """
    return _patch(url=url, *args, proxies=httpx_proxies, **kwargs)

def delete(url, *args, **kwargs):
    """
    发送DELETE请求。

    Args:
        url (str): 请求的URL。
        *args: 位置参数，传递给底层请求库。
        **kwargs: 关键字参数，包含请求的额外配置，如`follow_redirects`。

    Returns:
        返回请求的结果。

    Note:
        对于`delete`方法，处理`follow_redirects`参数：将其值映射到`allow_redirects`上，
        若设置为True，则启用重定向；否则，禁用重定向。原`follow_redirects`参数从kwargs中移除。
    """
    if 'follow_redirects' in kwargs:
        if kwargs['follow_redirects']:
            kwargs['allow_redirects'] = kwargs['follow_redirects']
        kwargs.pop('follow_redirects')
    if 'timeout' in kwargs:
        timeout = kwargs['timeout']
        if timeout is None:
            kwargs.pop('timeout')
        elif isinstance(timeout, tuple):
            # check length of tuple
            if len(timeout) == 2:
                kwargs['timeout'] = timeout
            elif len(timeout) == 1:
                kwargs['timeout'] = timeout[0]
            elif len(timeout) > 2:
                kwargs['timeout'] = (timeout[0], timeout[1])
        else:
            kwargs['timeout'] = (timeout, timeout)
    return _delete(url=url, *args, proxies=requests_proxies, **kwargs)

def head(url, *args, **kwargs):
    """
    发送HEAD请求。

    Args:
        url (str): 请求的URL。
        *args: 位置参数，传递给底层请求库。
        **kwargs: 关键字参数，包含请求的额外配置。

    Returns:
        返回请求的结果。
    """
    return _head(url=url, *args, proxies=httpx_proxies, **kwargs)

def options(url, *args, **kwargs):
    """
    发送OPTIONS请求。

    Args:
        url (str): 请求的URL。
        *args: 位置参数，传递给底层请求库。
        **kwargs: 关键字参数，包含请求的额外配置。

    Returns:
        返回请求的结果。
    """
    return _options(url=url, *args, proxies=httpx_proxies, **kwargs)