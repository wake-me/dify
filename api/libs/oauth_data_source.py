import urllib.parse

import requests
from flask_login import current_user

from extensions.ext_database import db
from models.source import DataSourceOauthBinding


class OAuthDataSource:
    """
    OAuth数据源类，用于提供OAuth认证的基本信息和支持。
    
    参数:
    client_id : str
        客户端ID，用于识别应用程序。
    client_secret : str
        客户端密钥，用于验证应用程序的身份。
    redirect_uri : str
        重定向URI，用于OAuth授权流程完成后的回调。
    """

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        """
        初始化OAuth数据源。
        
        参数:
        client_id : str
            客户端ID，用于识别应用程序。
        client_secret : str
            客户端密钥，用于验证应用程序的身份。
        redirect_uri : str
            重定向URI，用于OAuth授权流程完成后的回调。
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    def get_authorization_url(self):
        """
        获取授权URL，用于开始OAuth授权流程。
        
        返回:
        str
            授权页面的URL。
        """
        raise NotImplementedError()

    def get_access_token(self, code: str):
        """
        使用授权码获取访问令牌。
        
        参数:
        code : str
            授权码，用于换取访问令牌。
        
        返回:
        str
            获取到的访问令牌。
        """
        raise NotImplementedError()


class NotionOAuth(OAuthDataSource):
    _AUTH_URL = "https://api.notion.com/v1/oauth/authorize"
    _TOKEN_URL = "https://api.notion.com/v1/oauth/token"
    _NOTION_PAGE_SEARCH = "https://api.notion.com/v1/search"
    _NOTION_BLOCK_SEARCH = "https://api.notion.com/v1/blocks"
    _NOTION_BOT_USER = "https://api.notion.com/v1/users/me"

    def get_authorization_url(self):
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "owner": "user",
        }
        return f"{self._AUTH_URL}?{urllib.parse.urlencode(params)}"  # 组装URL

    def get_access_token(self, code: str):
        data = {"code": code, "grant_type": "authorization_code", "redirect_uri": self.redirect_uri}
        headers = {"Accept": "application/json"}
        auth = (self.client_id, self.client_secret)
        response = requests.post(self._TOKEN_URL, data=data, auth=auth, headers=headers)

        response_json = response.json()
        access_token = response_json.get("access_token")
        if not access_token:
            raise ValueError(f"Error in Notion OAuth: {response_json}")
        workspace_name = response_json.get("workspace_name")
        workspace_icon = response_json.get("workspace_icon")
        workspace_id = response_json.get("workspace_id")
        # get all authorized pages
        pages = self.get_authorized_pages(access_token)
        source_info = {
            "workspace_name": workspace_name,
            "workspace_icon": workspace_icon,
            "workspace_id": workspace_id,
            "pages": pages,
            "total": len(pages),
        }
        # save data source binding
        data_source_binding = DataSourceOauthBinding.query.filter(
            db.and_(
                DataSourceOauthBinding.tenant_id == current_user.current_tenant_id,
                DataSourceOauthBinding.provider == "notion",
                DataSourceOauthBinding.access_token == access_token,
            )
        ).first()
        if data_source_binding:
            # 更新已存在的数据源绑定
            data_source_binding.source_info = source_info
            data_source_binding.disabled = False
            db.session.commit()
        else:
            new_data_source_binding = DataSourceOauthBinding(
                tenant_id=current_user.current_tenant_id,
                access_token=access_token,
                source_info=source_info,
                provider="notion",
            )
            db.session.add(new_data_source_binding)
            db.session.commit()

    def save_internal_access_token(self, access_token: str):
        """
        保存内部访问令牌到数据源绑定中。
        
        参数:
        access_token (str): 需要保存的访问令牌。
        
        该方法不会返回任何内容。
        """
        # 根据访问令牌获取工作空间名称
        workspace_name = self.notion_workspace_name(access_token)
        workspace_icon = None
        workspace_id = current_user.current_tenant_id
        # 获取所有授权页面
        pages = self.get_authorized_pages(access_token)
        # 准备数据源信息
        source_info = {
            "workspace_name": workspace_name,
            "workspace_icon": workspace_icon,
            "workspace_id": workspace_id,
            "pages": pages,
            "total": len(pages),
        }
        # save data source binding
        data_source_binding = DataSourceOauthBinding.query.filter(
            db.and_(
                DataSourceOauthBinding.tenant_id == current_user.current_tenant_id,
                DataSourceOauthBinding.provider == "notion",
                DataSourceOauthBinding.access_token == access_token,
            )
        ).first()
        if data_source_binding:
            # 如果数据源绑定已存在，则更新其信息并启用
            data_source_binding.source_info = source_info
            data_source_binding.disabled = False
            db.session.commit()
        else:
            new_data_source_binding = DataSourceOauthBinding(
                tenant_id=current_user.current_tenant_id,
                access_token=access_token,
                source_info=source_info,
                provider="notion",
            )
            db.session.add(new_data_source_binding)
            db.session.commit()

    def sync_data_source(self, binding_id: str):
        # save data source binding
        data_source_binding = DataSourceOauthBinding.query.filter(
            db.and_(
                DataSourceOauthBinding.tenant_id == current_user.current_tenant_id,
                DataSourceOauthBinding.provider == "notion",
                DataSourceOauthBinding.id == binding_id,
                DataSourceOauthBinding.disabled == False,
            )
        ).first()
        if data_source_binding:
            # 使用访问令牌获取所有授权页面
            pages = self.get_authorized_pages(data_source_binding.access_token)
            source_info = data_source_binding.source_info
            # 更新数据源信息，包括工作区名称、图标、ID以及授权页面列表
            new_source_info = {
                "workspace_name": source_info["workspace_name"],
                "workspace_icon": source_info["workspace_icon"],
                "workspace_id": source_info["workspace_id"],
                "pages": pages,
                "total": len(pages),
            }
            data_source_binding.source_info = new_source_info
            data_source_binding.disabled = False
            # 提交数据库会话，保存更新
            db.session.commit()
        else:
            raise ValueError("Data source binding not found")

    def get_authorized_pages(self, access_token: str):
        """
        使用访问令牌获取授权页面和数据库的详细信息。
        
        参数:
        - access_token: 用户授权后的访问令牌，用于访问Notion API。
        
        返回值:
        - pages: 包含页面和数据库详情的列表，每个元素都是一个字典，含有页面或数据库的ID、名称、图标、父页面ID和类型。
        """
        pages = []
        # 搜索页面和数据库
        page_results = self.notion_page_search(access_token)
        database_results = self.notion_database_search(access_token)
        # get page detail
        # 遍历搜索结果，获取每个页面的详细信息
        for page_result in page_results:
            page_id = page_result["id"]
            page_name = "Untitled"
            for key in page_result["properties"]:
                if "title" in page_result["properties"][key] and page_result["properties"][key]["title"]:
                    title_list = page_result["properties"][key]["title"]
                    if len(title_list) > 0 and "plain_text" in title_list[0]:
                        page_name = title_list[0]["plain_text"]
            page_icon = page_result["icon"]
            if page_icon:
                icon_type = page_icon["type"]
                if icon_type == "external" or icon_type == "file":
                    url = page_icon[icon_type]["url"]
                    icon = {"type": "url", "url": url if url.startswith("http") else f"https://www.notion.so{url}"}
                else:
                    icon = {"type": "emoji", "emoji": page_icon[icon_type]}
            else:
                icon = None
            parent = page_result["parent"]
            parent_type = parent["type"]
            if parent_type == "block_id":
                parent_id = self.notion_block_parent_page_id(access_token, parent[parent_type])
            elif parent_type == "workspace":
                parent_id = "root"
            else:
                parent_id = parent[parent_type]
            # 构建页面信息字典
            page = {
                "page_id": page_id,
                "page_name": page_name,
                "page_icon": icon,
                "parent_id": parent_id,
                "type": "page",
            }
            pages.append(page)
            
        # 遍历数据库搜索结果，获取每个数据库的详细信息
        for database_result in database_results:
            page_id = database_result["id"]
            if len(database_result["title"]) > 0:
                page_name = database_result["title"][0]["plain_text"]
            else:
                page_name = "Untitled"
            page_icon = database_result["icon"]
            if page_icon:
                icon_type = page_icon["type"]
                if icon_type == "external" or icon_type == "file":
                    url = page_icon[icon_type]["url"]
                    icon = {"type": "url", "url": url if url.startswith("http") else f"https://www.notion.so{url}"}
                else:
                    icon = {"type": icon_type, icon_type: page_icon[icon_type]}
            else:
                icon = None
            parent = database_result["parent"]
            parent_type = parent["type"]
            if parent_type == "block_id":
                parent_id = self.notion_block_parent_page_id(access_token, parent[parent_type])
            elif parent_type == "workspace":
                parent_id = "root"
            else:
                parent_id = parent[parent_type]
            # 构建数据库信息字典
            page = {
                "page_id": page_id,
                "page_name": page_name,
                "page_icon": icon,
                "parent_id": parent_id,
                "type": "database",
            }
            pages.append(page)
        return pages

    def notion_page_search(self, access_token: str):
        data = {"filter": {"value": "page", "property": "object"}}
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
            "Notion-Version": "2022-06-28",
        }
        response = requests.post(url=self._NOTION_PAGE_SEARCH, json=data, headers=headers)
        response_json = response.json()
        results = response_json.get("results", [])
        return results

    def notion_block_parent_page_id(self, access_token: str, block_id: str):
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Notion-Version": "2022-06-28",
        }
        response = requests.get(url=f"{self._NOTION_BLOCK_SEARCH}/{block_id}", headers=headers)
        response_json = response.json()
        parent = response_json["parent"]
        parent_type = parent["type"]
        if parent_type == "block_id":
            return self.notion_block_parent_page_id(access_token, parent[parent_type])
        return parent[parent_type]

    def notion_workspace_name(self, access_token: str):
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Notion-Version": "2022-06-28",
        }
        response = requests.get(url=self._NOTION_BOT_USER, headers=headers)
        response_json = response.json()
        if "object" in response_json and response_json["object"] == "user":
            user_type = response_json["type"]
            user_info = response_json[user_type]
            if "workspace_name" in user_info:
                return user_info["workspace_name"]
        return "workspace"

    def notion_database_search(self, access_token: str):
        data = {"filter": {"value": "database", "property": "object"}}
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
            "Notion-Version": "2022-06-28",
        }
        response = requests.post(url=self._NOTION_PAGE_SEARCH, json=data, headers=headers)
        response_json = response.json()
        results = response_json.get("results", [])
        return results
