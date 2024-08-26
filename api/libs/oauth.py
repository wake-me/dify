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
    _AUTH_URL = "https://github.com/login/oauth/authorize"
    _TOKEN_URL = "https://github.com/login/oauth/access_token"
    _USER_INFO_URL = "https://api.github.com/user"
    _EMAIL_INFO_URL = "https://api.github.com/user/emails"

    def get_authorization_url(self):
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": "user:email",  # Request only basic user information
        }
        return f"{self._AUTH_URL}?{urllib.parse.urlencode(params)}"  # 拼接URL

    def get_access_token(self, code: str):
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": self.redirect_uri,
        }
        headers = {"Accept": "application/json"}
        response = requests.post(self._TOKEN_URL, data=data, headers=headers)

        response_json = response.json()
        access_token = response_json.get("access_token")

        if not access_token:
            raise ValueError(f"Error in GitHub OAuth: {response_json}")  # 处理错误

        return access_token

    def get_raw_user_info(self, token: str):
        headers = {"Authorization": f"token {token}"}
        response = requests.get(self._USER_INFO_URL, headers=headers)
        response.raise_for_status()
        user_info = response.json()

        email_response = requests.get(self._EMAIL_INFO_URL, headers=headers)  # 获取用户邮箱信息
        email_info = email_response.json()
        primary_email = next((email for email in email_info if email["primary"] == True), None)

        return {**user_info, "email": primary_email["email"]}

    def _transform_user_info(self, raw_info: dict) -> OAuthUserInfo:
        email = raw_info.get("email")
        if not email:
            email = f"{raw_info['id']}+{raw_info['login']}@users.noreply.github.com"
        return OAuthUserInfo(id=str(raw_info["id"]), name=raw_info["name"], email=email)


class GoogleOAuth(OAuth):
    _AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    _TOKEN_URL = "https://oauth2.googleapis.com/token"
    _USER_INFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

    def get_authorization_url(self):
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": "openid email",
        }
        return f"{self._AUTH_URL}?{urllib.parse.urlencode(params)}"  # 组装URL

    def get_access_token(self, code: str):
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri,
        }
        headers = {"Accept": "application/json"}
        response = requests.post(self._TOKEN_URL, data=data, headers=headers)

        response_json = response.json()
        access_token = response_json.get("access_token")

        if not access_token:
            raise ValueError(f"Error in Google OAuth: {response_json}")  # 处理错误

        return access_token

    def get_raw_user_info(self, token: str):
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(self._USER_INFO_URL, headers=headers)
        response.raise_for_status()
        return response.json()

    def _transform_user_info(self, raw_info: dict) -> OAuthUserInfo:
        return OAuthUserInfo(id=str(raw_info["sub"]), name=None, email=raw_info["email"])
