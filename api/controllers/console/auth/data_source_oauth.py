import logging

import requests
from flask import current_app, redirect, request
from flask_login import current_user
from flask_restful import Resource
from werkzeug.exceptions import Forbidden

from configs import dify_config
from controllers.console import api
from libs.login import login_required
from libs.oauth_data_source import NotionOAuth

from ..setup import setup_required
from ..wraps import account_initialization_required


def get_oauth_providers():
    """
    获取OAuth提供者配置。
    
    该函数不接受参数。
    
    返回值:
        dict: 包含OAuth提供者名称及其对应实例的字典。
    """
    with current_app.app_context():
        if not dify_config.NOTION_CLIENT_ID or not dify_config.NOTION_CLIENT_SECRET:
            return {}
        notion_oauth = NotionOAuth(client_id=dify_config.NOTION_CLIENT_ID,
                                   client_secret=dify_config.NOTION_CLIENT_SECRET,
                                   redirect_uri=dify_config.CONSOLE_API_URL + '/console/api/oauth/data-source/callback/notion')

        # 定义OAuth提供者字典
        OAUTH_PROVIDERS = {
            'notion': notion_oauth
        }
        return OAUTH_PROVIDERS


class OAuthDataSource(Resource):
    """
    OAuth数据源类，用于处理OAuth认证相关的请求。
    
    方法:
    - get: 根据提供的provider获取OAuth认证所需的URL或数据。
    
    参数:
    - provider: 字符串，指定OAuth提供者的名称。
    
    返回值:
    - 根据不同的配置和OAuth提供者，返回包含授权URL的字典或空字典。
    - 如果用户角色不是管理员或所有者，将抛出Forbidden异常。
    """

    def get(self, provider: str):
        # 检查当前用户是否具有管理员或所有者的角色
        if not current_user.is_admin_or_owner:
            raise Forbidden()
        
        # 获取所有配置的OAuth提供者
        OAUTH_DATASOURCE_PROVIDERS = get_oauth_providers()
        
        # 在当前应用的上下文中处理OAuth逻辑
        with current_app.app_context():
            # 根据provider获取特定的OAuth提供者实例
            oauth_provider = OAUTH_DATASOURCE_PROVIDERS.get(provider)
            print(vars(oauth_provider))
        
        # 检查是否找到了指定的OAuth提供者
        if not oauth_provider:
            return {'error': 'Invalid provider'}, 400
        if dify_config.NOTION_INTEGRATION_TYPE == 'internal':
            internal_secret = dify_config.NOTION_INTERNAL_SECRET
            if not internal_secret:
                return {'error': 'Internal secret is not set'},
            oauth_provider.save_internal_access_token(internal_secret)
            return { 'data': '' }
        else:
            # 外部集成：获取授权URL并返回
            auth_url = oauth_provider.get_authorization_url()
            return { 'data': auth_url }, 200



class OAuthDataSourceCallback(Resource):
    """
    处理OAuth数据源回调的类。
    
    方法:
    - get: 根据提供的OAuth提供者名称处理回调请求。
    
    参数:
    - provider (str): OAuth提供者的名称。
    
    返回值:
    - 根据不同的回调情况返回不同的JSON或重定向响应。
    """

    def get(self, provider: str):
        # 获取所有配置的OAuth提供者
        OAUTH_DATASOURCE_PROVIDERS = get_oauth_providers()
        # 设置当前应用上下文
        with current_app.app_context():
            # 根据provider参数获取对应的OAuth提供者配置
            oauth_provider = OAUTH_DATASOURCE_PROVIDERS.get(provider)
        
        # 检查是否提供了无效的provider
        if not oauth_provider:
            return {'error': 'Invalid provider'}, 400

        # 处理请求参数中的code
        if 'code' in request.args:
            code = request.args.get('code')

            return redirect(f'{dify_config.CONSOLE_WEB_URL}?type=notion&code={code}')
        elif 'error' in request.args:
            error = request.args.get('error')

            return redirect(f'{dify_config.CONSOLE_WEB_URL}?type=notion&error={error}')
        else:
            return redirect(f'{dify_config.CONSOLE_WEB_URL}?type=notion&error=Access denied')
        

class OAuthDataSourceBinding(Resource):
    """
    OAuth数据源绑定类，用于处理OAuth认证提供商的数据源绑定请求。
    
    方法:
    - get: 根据提供的OAuth提供商名称进行操作，如果提供了认证代码，则尝试完成OAuth授权流程。
    
    参数:
    - provider (str): OAuth提供商的名称。
    
    返回值:
    - 当提供商无效时，返回一个包含错误信息的字典和HTTP状态码400；
    - 当请求中包含有效的认证代码时，尝试获取访问令牌，成功则返回成功信息和HTTP状态码200；
    - 当获取访问令牌过程中出现错误时，返回一个包含错误信息的字典和HTTP状态码400。
    """

    def get(self, provider: str):
        # 获取所有配置的OAuth提供商
        OAUTH_DATASOURCE_PROVIDERS = get_oauth_providers()
        with current_app.app_context():
            # 根据提供商名称获取具体的OAuth提供者实例
            oauth_provider = OAUTH_DATASOURCE_PROVIDERS.get(provider)
        if not oauth_provider:
            # 当提供商不存在时，返回错误信息
            return {'error': 'Invalid provider'}, 400
        if 'code' in request.args:
            # 如果请求中包含认证代码，尝试使用该代码获取访问令牌
            code = request.args.get('code')
            try:
                oauth_provider.get_access_token(code)
            except requests.exceptions.HTTPError as e:
                # 当获取访问令牌失败时，记录异常并返回错误信息
                logging.exception(
                    f"An error occurred during the OAuthCallback process with {provider}: {e.response.text}")
                return {'error': 'OAuth data source process failed'}, 400

            # 获取访问令牌成功，返回成功信息
            return {'result': 'success'}, 200


class OAuthDataSourceSync(Resource):
    """
    处理OAuth数据源同步的类。
    
    方法:
    - get: 同步指定提供商和绑定ID的数据源。
    
    参数:
    - provider: string，数据源提供商的标识符。
    - binding_id: string，与数据源绑定的ID。
    
    返回值:
    - 当提供商无效时，返回包含错误信息的字典和HTTP状态码400。
    - 当OAuth数据源处理失败时，返回包含错误信息的字典和HTTP状态码400。
    - 否则，返回包含成功信息的字典和HTTP状态码200。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    def get(self, provider, binding_id):
        # 将提供商和绑定ID转换为字符串类型
        provider = str(provider)
        binding_id = str(binding_id)
        
        # 获取所有OAuth数据源提供商
        OAUTH_DATASOURCE_PROVIDERS = get_oauth_providers()
        
        # 设置当前应用上下文
        with current_app.app_context():
            # 尝试根据提供商获取OAuth数据源提供者实例
            oauth_provider = OAUTH_DATASOURCE_PROVIDERS.get(provider)
        
        if not oauth_provider:
            # 当提供商不存在时返回错误信息
            return {'error': 'Invalid provider'}, 400
        
        try:
            # 尝试同步指定的数据源
            oauth_provider.sync_data_source(binding_id)
        except requests.exceptions.HTTPError as e:
            # 当同步过程中出现HTTP错误时记录异常并返回错误信息
            logging.exception(
                f"An error occurred during the OAuthCallback process with {provider}: {e.response.text}")
            return {'error': 'OAuth data source process failed'}, 400

        # 当同步成功时返回成功信息
        return {'result': 'success'}, 200


api.add_resource(OAuthDataSource, '/oauth/data-source/<string:provider>')
api.add_resource(OAuthDataSourceCallback, '/oauth/data-source/callback/<string:provider>')
api.add_resource(OAuthDataSourceBinding, '/oauth/data-source/binding/<string:provider>')
api.add_resource(OAuthDataSourceSync, '/oauth/data-source/<string:provider>/<uuid:binding_id>/sync')
