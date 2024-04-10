import logging

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
from services.model_provider_service import ModelProviderService


class DefaultModelApi(Resource):
    """
    默认模型API接口类，提供获取和更新默认模型的功能。
    """

    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        """
        获取指定模型类型的默认模型实体。
        
        参数:
        - model_type: 模型类型，必须是ModelType枚举值之一。
        
        返回值:
        - 默认模型实体的JSON编码字典。
        """
        parser = reqparse.RequestParser()
        # 解析请求参数，校验模型类型
        parser.add_argument('model_type', type=str, required=True, nullable=False,
                            choices=[mt.value for mt in ModelType], location='args')
        args = parser.parse_args()

        tenant_id = current_user.current_tenant_id  # 获取当前租户ID

        model_provider_service = ModelProviderService()
        # 根据模型类型获取默认模型实体
        default_model_entity = model_provider_service.get_default_model_of_model_type(
            tenant_id=tenant_id,
            model_type=args['model_type']
        )

        return jsonable_encoder({
            "data": default_model_entity
        })

    @setup_required
    @login_required
    @account_initialization_required
    def post(self):
        """
        更新默认模型设置。
        
        参数:
        - model_settings: 模型设置列表，每个设置项包含模型类型、提供者和模型名称。
        
        返回值:
        - 字典，包含结果信息。
        """
        parser = reqparse.RequestParser()
        # 解析请求体中的模型设置列表
        parser.add_argument('model_settings', type=list, required=True, nullable=False, location='json')
        args = parser.parse_args()

        tenant_id = current_user.current_tenant_id  # 获取当前租户ID

        model_provider_service = ModelProviderService()
        model_settings = args['model_settings']
        for model_setting in model_settings:
            # 校验模型类型有效性
            if 'model_type' not in model_setting or model_setting['model_type'] not in [mt.value for mt in ModelType]:
                raise ValueError('invalid model type')

            # 如果提供者信息不存在，则跳过
            if 'provider' not in model_setting:
                continue

            # 如果模型名称不存在，则抛出异常
            if 'model' not in model_setting:
                raise ValueError('invalid model')

            try:
                # 尝试更新指定模型类型的默认模型设置
                model_provider_service.update_default_model_of_model_type(
                    tenant_id=tenant_id,
                    model_type=model_setting['model_type'],
                    provider=model_setting['provider'],
                    model=model_setting['model']
                )
            except Exception:
                # 记录保存错误的日志
                logging.warning(f"{model_setting['model_type']} save error")

        return {'result': 'success'}


class ModelProviderModelApi(Resource):
    """
    提供者模型API接口类，用于处理与模型提供者相关的请求。
    """

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, provider):
        """
        获取指定提供者的模型信息。
        
        参数:
        - provider: 模型提供者的标识符。
        
        返回值:
        - 一个包含模型信息的JSON对象。
        """
        tenant_id = current_user.current_tenant_id  # 获取当前租户ID

        # 获取模型提供者的服务实例，并查询指定提供者的模型信息
        model_provider_service = ModelProviderService()
        models = model_provider_service.get_models_by_provider(
            tenant_id=tenant_id,
            provider=provider
        )

        return jsonable_encoder({
            "data": models
        })

    @setup_required
    @login_required
    @account_initialization_required
    def post(self, provider: str):
        """
        为指定提供者和模型添加认证信息。
        
        参数:
        - provider: 模型提供者的标识符。
        
        请求体:
        - model: 模型的标识符。
        - model_type: 模型的类型。
        - credentials: 模型访问所需的认证信息。
        
        返回值:
        - 一个表示操作成功的JSON对象，以及状态码200。
        
        异常:
        - Forbidden: 如果当前用户角色不是管理员或所有者。
        """
        # 检查用户角色是否具有权限
        if current_user.current_tenant.current_role not in ['admin', 'owner']:
            raise Forbidden()

        tenant_id = current_user.current_tenant_id  # 获取当前租户ID

        # 解析请求体中的参数
        parser = reqparse.RequestParser()
        parser.add_argument('model', type=str, required=True, nullable=False, location='json')
        parser.add_argument('model_type', type=str, required=True, nullable=False,
                            choices=[mt.value for mt in ModelType], location='json')
        parser.add_argument('credentials', type=dict, required=True, nullable=False, location='json')
        args = parser.parse_args()

        model_provider_service = ModelProviderService()

        try:
            # 尝试保存模型的认证信息
            model_provider_service.save_model_credentials(
                tenant_id=tenant_id,
                provider=provider,
                model=args['model'],
                model_type=args['model_type'],
                credentials=args['credentials']
            )
        except CredentialsValidateFailedError as ex:
            # 如果认证信息验证失败，则抛出ValueError异常
            raise ValueError(str(ex))

        return {'result': 'success'}, 200

    @setup_required
    @login_required
    @account_initialization_required
    def delete(self, provider: str):
        """
        删除指定提供者和模型的认证信息。
        
        参数:
        - provider: 模型提供者的标识符。
        
        请求体:
        - model: 模型的标识符。
        - model_type: 模型的类型。
        
        返回值:
        - 一个表示操作成功的JSON对象，以及状态码204。
        
        异常:
        - Forbidden: 如果当前用户角色不是管理员或所有者。
        """
        # 检查用户角色是否具有权限
        if current_user.current_tenant.current_role not in ['admin', 'owner']:
            raise Forbidden()

        tenant_id = current_user.current_tenant_id  # 获取当前租户ID

        # 解析请求体中的参数
        parser = reqparse.RequestParser()
        parser.add_argument('model', type=str, required=True, nullable=False, location='json')
        parser.add_argument('model_type', type=str, required=True, nullable=False,
                            choices=[mt.value for mt in ModelType], location='json')
        args = parser.parse_args()

        model_provider_service = ModelProviderService()
        # 尝试移除模型的认证信息
        model_provider_service.remove_model_credentials(
            tenant_id=tenant_id,
            provider=provider,
            model=args['model'],
            model_type=args['model_type']
        )

        return {'result': 'success'}, 204


class ModelProviderModelCredentialApi(Resource):
    """
    提供模型凭证的API接口类。
    
    方法：
    - get: 根据提供的模型提供商、模型类型和模型名称获取模型凭证。
    
    参数：
    - provider: 模型提供商的字符串标识。
    
    返回值：
    - 一个包含模型凭证的字典。
    """

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, provider: str):
        """
        获取指定模型提供商的模型凭证。
        
        参数：
        - provider: 模型提供商的字符串标识。
        
        返回值：
        - 包含模型凭证的字典。
        """
        tenant_id = current_user.current_tenant_id  # 获取当前用户所属的租户ID

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('model', type=str, required=True, nullable=False, location='args')
        parser.add_argument('model_type', type=str, required=True, nullable=False,
                            choices=[mt.value for mt in ModelType], location='args')
        args = parser.parse_args()

        # 调用服务层获取模型凭证
        model_provider_service = ModelProviderService()
        credentials = model_provider_service.get_model_credentials(
            tenant_id=tenant_id,
            provider=provider,
            model_type=args['model_type'],
            model=args['model']
        )

        return {
            "credentials": credentials
        }


class ModelProviderModelValidateApi(Resource):
    """
    提供者模型验证API，用于验证模型提供者的模型及其凭证是否有效。
    
    方法: POST
    参数:
    - provider: 字符串，模型提供者的标识符。
    
    请求体参数:
    - model: 字符串，模型的标识符。
    - model_type: 字符串，模型的类型，从预定义的ModelType枚举中选择。
    - credentials: 字典，包含用于验证模型的凭证信息。
    
    返回值:
    - 字典，包含验证结果和错误信息（如果有）。
    """

    @setup_required
    @login_required
    @account_initialization_required
    def post(self, provider: str):
        tenant_id = current_user.current_tenant_id  # 获取当前用户所属的租户ID

        # 解析请求体中的参数
        parser = reqparse.RequestParser()
        parser.add_argument('model', type=str, required=True, nullable=False, location='json')
        parser.add_argument('model_type', type=str, required=True, nullable=False,
                            choices=[mt.value for mt in ModelType], location='json')
        parser.add_argument('credentials', type=dict, required=True, nullable=False, location='json')
        args = parser.parse_args()

        model_provider_service = ModelProviderService()

        result = True
        error = None

        try:
            # 尝试使用提供的凭证验证模型
            model_provider_service.model_credentials_validate(
                tenant_id=tenant_id,
                provider=provider,
                model=args['model'],
                model_type=args['model_type'],
                credentials=args['credentials']
            )
        except CredentialsValidateFailedError as ex:
            result = False
            error = str(ex)  # 将捕获到的验证失败异常信息转换为字符串

        # 准备响应
        response = {'result': 'success' if result else 'error'}

        if not result:
            response['error'] = error  # 如果验证失败，将错误信息添加到响应中

        return response


class ModelProviderModelParameterRuleApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, provider: str):
        parser = reqparse.RequestParser()
        parser.add_argument('model', type=str, required=True, nullable=False, location='args')
        args = parser.parse_args()

        tenant_id = current_user.current_tenant_id

        model_provider_service = ModelProviderService()
        parameter_rules = model_provider_service.get_model_parameter_rules(
            tenant_id=tenant_id,
            provider=provider,
            model=args['model']
        )

        return jsonable_encoder({
            "data": parameter_rules
        })


class ModelProviderAvailableModelApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, model_type):
        tenant_id = current_user.current_tenant_id

        model_provider_service = ModelProviderService()
        models = model_provider_service.get_models_by_model_type(
            tenant_id=tenant_id,
            model_type=model_type
        )

        return jsonable_encoder({
            "data": models
        })


api.add_resource(ModelProviderModelApi, '/workspaces/current/model-providers/<string:provider>/models')
api.add_resource(ModelProviderModelCredentialApi,
                 '/workspaces/current/model-providers/<string:provider>/models/credentials')
api.add_resource(ModelProviderModelValidateApi,
                 '/workspaces/current/model-providers/<string:provider>/models/credentials/validate')

api.add_resource(ModelProviderModelParameterRuleApi,
                 '/workspaces/current/model-providers/<string:provider>/models/parameter-rules')
api.add_resource(ModelProviderAvailableModelApi, '/workspaces/current/models/model-types/<string:model_type>')
api.add_resource(DefaultModelApi, '/workspaces/current/default-model')
