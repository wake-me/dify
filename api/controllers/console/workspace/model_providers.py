import io

from flask import send_file
from flask_login import current_user
from flask_restful import Resource, reqparse
from werkzeug.exceptions import Forbidden

from controllers.console import api
from controllers.console.setup import setup_required
from controllers.console.wraps import account_initialization_required
from core.model_runtime.entities.model_entities import ModelType
from core.model_runtime.errors.validate import CredentialsValidateFailedError
from core.model_runtime.utils.encoders import jsonable_encoder
from libs.login import login_required
from services.billing_service import BillingService
from services.model_provider_service import ModelProviderService


class ModelProviderListApi(Resource):
    """
    提供模型服务提供商列表的API接口
    """

    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        """
        获取模型服务提供商列表
        
        要求用户已登录、账号已初始化且系统已设置好。
        
        返回值:
            - JSON编码的模型服务提供商列表信息
        """
        # 获取当前用户所属的租户ID
        tenant_id = current_user.current_tenant_id

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('model_type', type=str, required=False, nullable=True,
                            choices=[mt.value for mt in ModelType], location='args')
        args = parser.parse_args()

        # 调用服务层获取提供商列表
        model_provider_service = ModelProviderService()
        provider_list = model_provider_service.get_provider_list(
            tenant_id=tenant_id,
            model_type=args.get('model_type')
        )

        # 返回编码后的提供商列表数据
        return jsonable_encoder({"data": provider_list})


class ModelProviderCredentialApi(Resource):
    """
    提供模型提供者凭证的API接口类。
    
    方法:
    - get: 根据提供的模型提供者名称，获取相应的凭证信息。
    """

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, provider: str):
        """
        获取指定模型提供者的凭证信息。
        
        参数:
        - provider: 字符串，指定的模型提供者名称。
        
        返回值:
        - 一个字典，包含模型提供者的凭证信息。
        """
        
        # 获取当前用户所属的租户ID
        tenant_id = current_user.current_tenant_id

        # 实例化模型提供者服务，并获取指定提供者的凭证信息
        model_provider_service = ModelProviderService()
        credentials = model_provider_service.get_provider_credentials(
            tenant_id=tenant_id,
            provider=provider
        )

        # 返回凭证信息
        return {
            "credentials": credentials
        }


class ModelProviderValidateApi(Resource):
    """
    提供者验证API模型，用于验证特定提供者的凭证。

    方法:
    - post: 验证提供者的凭证。
    """

    @setup_required
    @login_required
    @account_initialization_required
    def post(self, provider: str):
        """
        验证给定提供者的凭证。

        参数:
        - provider: 字符串，指定要验证凭证的提供者名称。

        返回值:
        - 字典，包含验证结果和可能的错误信息。
        """

        # 解析请求中的凭证信息
        parser = reqparse.RequestParser()
        parser.add_argument('credentials', type=dict, required=True, nullable=False, location='json')
        args = parser.parse_args()

        # 获取当前用户的租户ID
        tenant_id = current_user.current_tenant_id

        # 初始化模型提供者服务
        model_provider_service = ModelProviderService()

        # 验证结果和错误信息的初始设置
        result = True
        error = None

        try:
            # 尝试使用提供的凭证进行验证
            model_provider_service.provider_credentials_validate(
                tenant_id=tenant_id,
                provider=provider,
                credentials=args['credentials']
            )
        except CredentialsValidateFailedError as ex:
            # 如果验证失败，捕获异常并记录错误信息
            result = False
            error = str(ex)

        # 准备响应信息
        response = {'result': 'success' if result else 'error'}

        # 如果验证失败，添加错误信息到响应中
        if not result:
            response['error'] = error

        return response


class ModelProviderApi(Resource):
    """
    模型提供者API类，用于处理与模型提供者相关的请求。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    def post(self, provider: str):
        """
        保存指定提供商的凭证信息。
        
        参数:
        - provider: str，指定的模型提供商名称。
        
        返回值:
        - dict，包含结果信息的字典，成功时返回 {'result': 'success'}。
        - int，HTTP状态码，成功时为201。
        
        异常:
        - Forbidden，如果当前用户不是管理员或所有者则抛出。
        - ValueError，如果凭证验证失败则抛出。
        """
        # 检查用户权限
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        # 解析请求中的凭证信息
        parser = reqparse.RequestParser()
        parser.add_argument('credentials', type=dict, required=True, nullable=False, location='json')
        args = parser.parse_args()

        # 使用服务层保存提供商凭证
        model_provider_service = ModelProviderService()
        try:
            model_provider_service.save_provider_credentials(
                tenant_id=current_user.current_tenant_id,
                provider=provider,
                credentials=args['credentials']
            )
        except CredentialsValidateFailedError as ex:
            raise ValueError(str(ex))

        # 返回成功响应
        return {'result': 'success'}, 201

    @setup_required
    @login_required
    @account_initialization_required
    def delete(self, provider: str):
        """
        删除指定提供商的凭证信息。
        
        参数:
        - provider: str，指定的模型提供商名称。
        
        返回值:
        - dict，包含结果信息的字典，成功时返回 {'result': 'success'}。
        - int，HTTP状态码，成功时为204。
        
        异常:
        - Forbidden，如果当前用户不是管理员或所有者则抛出。
        """
        # 检查用户权限
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        # 使用服务层删除提供商凭证
        model_provider_service = ModelProviderService()
        model_provider_service.remove_provider_credentials(
            tenant_id=current_user.current_tenant_id,
            provider=provider
        )

        # 返回成功响应
        return {'result': 'success'}, 204


class ModelProviderIconApi(Resource):
    """
    获取模型提供者图标

    参数:
    - provider: 模型提供者的字符串标识
    - icon_type: 图标类型的字符串标识
    - lang: 图标语言的字符串标识

    返回值:
    - 返回一个发送文件的响应，该文件为模型提供者的图标
    """

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, provider: str, icon_type: str, lang: str):
        # 初始化模型提供者服务
        model_provider_service = ModelProviderService()
        # 从服务获取模型提供者的图标及其MIME类型
        icon, mimetype = model_provider_service.get_model_provider_icon(
            provider=provider,
            icon_type=icon_type,
            lang=lang
        )

        # 发送图标文件作为响应
        return send_file(io.BytesIO(icon), mimetype=mimetype)


class PreferredProviderTypeUpdateApi(Resource):
    """
    用于更新首选服务提供商类型的API接口类

    方法:
        post: 更新指定提供商的首选服务提供商类型
    """

    @setup_required
    @login_required
    @account_initialization_required
    def post(self, provider: str):
        """
        更新指定提供商的首选服务提供商类型
        
        参数:
            provider (str): 要更新首选服务提供商类型的服务提供商名称
        
        返回:
            dict: 包含操作结果信息的字典
        """
        # 检查用户是否有权限进行操作，如果不是管理员或所有者，则抛出Forbidden异常
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        # 获取当前用户所属的租户ID
        tenant_id = current_user.current_tenant_id

        # 解析请求参数，要求提供'preferred_provider_type'参数
        parser = reqparse.RequestParser()
        parser.add_argument('preferred_provider_type', type=str, required=True, nullable=False,
                            choices=['system', 'custom'], location='json')
        args = parser.parse_args()

        # 调用服务层方法，切换指定租户和提供商的首选服务提供商类型
        model_provider_service = ModelProviderService()
        model_provider_service.switch_preferred_provider(
            tenant_id=tenant_id,
            provider=provider,
            preferred_provider_type=args['preferred_provider_type']
        )

        # 返回操作成功的结果
        return {'result': 'success'}


class ModelProviderPaymentCheckoutUrlApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def get(self, provider: str):
        if provider != 'anthropic':
            raise ValueError(f'provider name {provider} is invalid')
        BillingService.is_tenant_owner_or_admin(current_user)
        data = BillingService.get_model_provider_payment_link(provider_name=provider,
                                                              tenant_id=current_user.current_tenant_id,
                                                              account_id=current_user.id,
                                                              prefilled_email=current_user.email)
        return data


class ModelProviderFreeQuotaSubmitApi(Resource):
    """
    提供免费配额提交接口的API类。
    
    方法：
    - post: 提交免费配额申请。
    
    参数：
    - provider (str): 服务提供商名称。
    
    返回值：
    - 提交结果，具体类型和结构由ModelProviderService的free_quota_submit方法决定。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    def post(self, provider: str):
        """
        提交免费配额申请。
        
        参数：
        - provider (str): 服务提供商名称。
        
        返回值：
        - 提交结果，具体类型和结构由ModelProviderService的free_quota_submit方法决定。
        """
        # 初始化模型服务提供者服务
        model_provider_service = ModelProviderService()
        # 提交免费配额申请
        result = model_provider_service.free_quota_submit(
            tenant_id=current_user.current_tenant_id,
            provider=provider
        )

        return result


class ModelProviderFreeQuotaQualificationVerifyApi(Resource):
    """
    提供模型服务免费额度资格验证的API接口
    
    方法:
    GET: 根据提供的provider和token验证用户的免费额度资格
    
    参数:
    - provider (str): 模型服务提供者的标识
    
    返回值:
    - 验证结果，具体结构由实现决定
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    def get(self, provider: str):
        """
        处理GET请求，验证用户对指定提供者的免费额度资格
        
        参数:
        - provider (str): 模型服务提供者的标识
        
        返回值:
        - 验证结果，具体结构由实现决定
        """
        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('token', type=str, required=False, nullable=True, location='args')
        args = parser.parse_args()

        # 初始化模型服务提供者服务，并调用验证资格方法
        model_provider_service = ModelProviderService()
        result = model_provider_service.free_quota_qualification_verify(
            tenant_id=current_user.current_tenant_id,
            provider=provider,
            token=args['token']
        )

        # 返回验证结果
        return result

api.add_resource(ModelProviderListApi, '/workspaces/current/model-providers')

api.add_resource(ModelProviderCredentialApi, '/workspaces/current/model-providers/<string:provider>/credentials')
api.add_resource(ModelProviderValidateApi, '/workspaces/current/model-providers/<string:provider>/credentials/validate')
api.add_resource(ModelProviderApi, '/workspaces/current/model-providers/<string:provider>')
api.add_resource(ModelProviderIconApi, '/workspaces/current/model-providers/<string:provider>/'
                                       '<string:icon_type>/<string:lang>')

api.add_resource(PreferredProviderTypeUpdateApi,
                 '/workspaces/current/model-providers/<string:provider>/preferred-provider-type')
api.add_resource(ModelProviderPaymentCheckoutUrlApi,
                 '/workspaces/current/model-providers/<string:provider>/checkout-url')
api.add_resource(ModelProviderFreeQuotaSubmitApi,
                 '/workspaces/current/model-providers/<string:provider>/free-quota-submit')
api.add_resource(ModelProviderFreeQuotaQualificationVerifyApi,
                 '/workspaces/current/model-providers/<string:provider>/free-quota-qualification-verify')
