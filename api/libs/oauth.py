import urllib.parse
from dataclasses import dataclass

import requests


@dataclass
class OAuthUserInfo:
    """
    OAuth用户信息类，包含用户的基本信息。
    
    参数:
    - id: 用户的唯一标识符，类型为str。
    - name: 用户的名称，类型为str。
    - email: 用户的电子邮件地址，类型为str。
    """
    id: str
    name: str
    email: str

class OAuth:
    """
    OAuth认证类，用于处理OAuth认证流程。
    
    参数:
    - client_id: 客户端ID，用于识别应用，类型为str。
    - client_secret: 客户端密钥，用于验证应用的身份，类型为str。
    - redirect_uri: 授权成功后，OAuth服务器重定向的URI，类型为str。
    """
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    def get_authorization_url(self):
        """
        获取用户授权的URL。
        
        返回:
        - 授权页面的URL，类型为str。
        
        抛出:
        - NotImplementedError: 当前方法是个抽象方法，需要在子类中实现。
        """
        raise NotImplementedError()

    def get_access_token(self, code: str):
        """
        使用授权码获取访问令牌。
        
        参数:
        - code: 用户授权后返回的授权码，类型为str。
        
        返回:
        - 访问令牌，类型为str。
        
        抛出:
        - NotImplementedError: 当前方法是个抽象方法，需要在子类中实现。
        """
        raise NotImplementedError()

    def get_raw_user_info(self, token: str):
        """
        使用访问令牌获取未经处理的用户信息。
        
        参数:
        - token: 访问令牌，用于获取用户信息，类型为str。
        
        返回:
        - 未经处理的用户信息，通常为字典类型。
        
        抛出:
        - NotImplementedError: 当前方法是个抽象方法，需要在子类中实现。
        """
        raise NotImplementedError()

    def get_user_info(self, token: str) -> OAuthUserInfo:
        """
        使用访问令牌获取处理后的用户信息。
        
        参数:
        - token: 访问令牌，类型为str。
        
        返回:
        - OAuthUserInfo实例，包含用户的id、name和email。
        
        抛出:
        - NotImplementedError: 当前方法是个抽象方法，需要在子类中实现。
        """
        raw_info = self.get_raw_user_info(token)
        return self._transform_user_info(raw_info)

    def _transform_user_info(self, raw_info: dict) -> OAuthUserInfo:
        """
        将未经处理的用户信息转换为OAuthUserInfo实例。
        
        参数:
        - raw_info: 未经处理的用户信息，类型为dict。
        
        返回:
        - 转换后的OAuthUserInfo实例。
        
        抛出:
        - NotImplementedError: 当前方法是个抽象方法，需要在子类中实现。
        """
        raise NotImplementedError()


class GitHubOAuth(OAuth):
    """
    GitHub OAuth认证类，继承自OAuth类。
    """
    _AUTH_URL = 'https://github.com/login/oauth/authorize'  # GitHub授权URL
    _TOKEN_URL = 'https://github.com/login/oauth/access_token'  # GitHub获取访问令牌URL
    _USER_INFO_URL = 'https://api.github.com/user'  # GitHub用户信息URL
    _EMAIL_INFO_URL = 'https://api.github.com/user/emails'  # GitHub用户邮箱信息URL

    def get_authorization_url(self):
        """
        获取用户授权页面的URL。
        
        返回:
            str: 用户授权页面的URL，携带客户端ID、重定向URI和请求权限范围等参数。
        """
        params = {  # 构建请求参数
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'scope': 'user:email'  # 仅请求基本用户信息和邮箱权限
        }
        return f"{self._AUTH_URL}?{urllib.parse.urlencode(params)}"  # 拼接URL

    def get_access_token(self, code: str):
        """
        通过授权码获取访问令牌。
        
        参数:
            code (str): 授权码，由用户授权后返回。
            
        返回:
            str: 获取的访问令牌。
            
        抛出:
            ValueError: 如果获取访问令牌失败。
        """
        data = {  # 构建请求数据
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
            'redirect_uri': self.redirect_uri
        }
        headers = {'Accept': 'application/json'}  # 设置请求头部
        response = requests.post(self._TOKEN_URL, data=data, headers=headers)  # 发送请求

        response_json = response.json()  # 解析响应数据
        access_token = response_json.get('access_token')

        if not access_token:
            raise ValueError(f"Error in GitHub OAuth: {response_json}")  # 处理错误

        return access_token

    def get_raw_user_info(self, token: str):
        """
        使用访问令牌获取用户的基本信息和邮箱信息。
        
        参数:
            token (str): 访问令牌。
            
        返回:
            dict: 包含用户信息和邮箱信息的字典。
        """
        headers = {'Authorization': f"token {token}"}  # 设置请求头部，携带访问令牌
        response = requests.get(self._USER_INFO_URL, headers=headers)  # 获取用户基本信息
        response.raise_for_status()  # 检查请求状态
        user_info = response.json()  # 解析响应数据

        email_response = requests.get(self._EMAIL_INFO_URL, headers=headers)  # 获取用户邮箱信息
        email_info = email_response.json()
        primary_email = next((email for email in email_info if email['primary'] == True), None)  # 获取主邮箱地址

        return {**user_info, 'email': primary_email['email']}  # 返回用户和邮箱信息

    def _transform_user_info(self, raw_info: dict) -> OAuthUserInfo:
        """
        处理原始用户信息，构造OAuthUserInfo对象。
        
        参数:
            raw_info (dict): 原始用户信息。
            
        返回:
            OAuthUserInfo: 包含用户ID、姓名和邮箱的实例。
        """
        email = raw_info.get('email')  # 尝试从原始信息中获取邮箱
        if not email:  # 如果没有找到邮箱，则构造默认邮箱地址
            email = f"{raw_info['id']}+{raw_info['login']}@users.noreply.github.com"
        return OAuthUserInfo(
            id=str(raw_info['id']),
            name=raw_info['name'],
            email=email
        )  # 返回构造的用户信息对象


class GoogleOAuth(OAuth):
    """
    Google OAuth认证类，用于实现Google认证流程。
    """
    _AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'  # 授权URL
    _TOKEN_URL = 'https://oauth2.googleapis.com/token'  # 令牌获取URL
    _USER_INFO_URL = 'https://www.googleapis.com/oauth2/v3/userinfo'  # 用户信息URL

    def get_authorization_url(self):
        """
        获取用户授权页面的URL。

        返回:
            str: 用户授权页面的URL。
        """
        params = {  # 构建请求参数
            'client_id': self.client_id,
            'response_type': 'code',
            'redirect_uri': self.redirect_uri,
            'scope': 'openid email'
        }
        return f"{self._AUTH_URL}?{urllib.parse.urlencode(params)}"  # 组装URL

    def get_access_token(self, code: str):
        """
        通过授权码获取访问令牌。

        参数:
            code (str): 授权码。

        返回:
            str: 访问令牌。

        异常:
            ValueError: 如果无法获取访问令牌。
        """
        data = {  # 构建请求数据
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': self.redirect_uri
        }
        headers = {'Accept': 'application/json'}  # 设置请求头部
        response = requests.post(self._TOKEN_URL, data=data, headers=headers)  # 发送请求

        response_json = response.json()  # 解析响应
        access_token = response_json.get('access_token')  # 获取访问令牌

        if not access_token:
            raise ValueError(f"Error in Google OAuth: {response_json}")  # 处理错误

        return access_token

    def get_raw_user_info(self, token: str):
        """
        使用访问令牌获取用户信息。

        参数:
            token (str): 访问令牌。

        返回:
            dict: 包含用户信息的字典。
        """
        headers = {'Authorization': f"Bearer {token}"}  # 设置请求头部
        response = requests.get(self._USER_INFO_URL, headers=headers)  # 发送请求
        response.raise_for_status()  # 检查状态码
        return response.json()  # 返回用户信息

    def _transform_user_info(self, raw_info: dict) -> OAuthUserInfo:
        """
        转换原始用户信息为OAuthUserInfo对象。

        参数:
            raw_info (dict): 原始用户信息。

        返回:
            OAuthUserInfo: 包含用户ID和电子邮件的OAuthUserInfo对象。
        """
        return OAuthUserInfo(
            id=str(raw_info['sub']),
            name=None,
            email=raw_info['email']
        )


