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
from models.account import TenantAccountRole
from services.model_load_balancing_service import ModelLoadBalancingService
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
        if not TenantAccountRole.is_privileged_role(current_user.current_tenant.current_role):
            raise Forbidden()

        tenant_id = current_user.current_tenant_id  # 获取当前租户ID

        # 解析请求体中的参数
        parser = reqparse.RequestParser()
        parser.add_argument('model', type=str, required=True, nullable=False, location='json')
        parser.add_argument('model_type', type=str, required=True, nullable=False,
                            choices=[mt.value for mt in ModelType], location='json')
        parser.add_argument('credentials', type=dict, required=False, nullable=True, location='json')
        parser.add_argument('load_balancing', type=dict, required=False, nullable=True, location='json')
        parser.add_argument('config_from', type=str, required=False, nullable=True, location='json')
        args = parser.parse_args()

        model_load_balancing_service = ModelLoadBalancingService()

        if ('load_balancing' in args and args['load_balancing'] and
                'enabled' in args['load_balancing'] and args['load_balancing']['enabled']):
            if 'configs' not in args['load_balancing']:
                raise ValueError('invalid load balancing configs')

            # save load balancing configs
            model_load_balancing_service.update_load_balancing_configs(
                tenant_id=tenant_id,
                provider=provider,
                model=args['model'],
                model_type=args['model_type'],
                configs=args['load_balancing']['configs']
            )

            # enable load balancing
            model_load_balancing_service.enable_model_load_balancing(
                tenant_id=tenant_id,
                provider=provider,
                model=args['model'],
                model_type=args['model_type']
            )
        else:
            # disable load balancing
            model_load_balancing_service.disable_model_load_balancing(
                tenant_id=tenant_id,
                provider=provider,
                model=args['model'],
                model_type=args['model_type']
            )

            if args.get('config_from', '') != 'predefined-model':
                model_provider_service = ModelProviderService()

                try:
                    model_provider_service.save_model_credentials(
                        tenant_id=tenant_id,
                        provider=provider,
                        model=args['model'],
                        model_type=args['model_type'],
                        credentials=args['credentials']
                    )
                except CredentialsValidateFailedError as ex:
                    raise ValueError(str(ex))

        return {'result': 'success'}, 200

    @setup_required
    @login_required
    @account_initialization_required
    def delete(self, provider: str):
        if not TenantAccountRole.is_privileged_role(current_user.current_tenant.current_role):
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

        model_load_balancing_service = ModelLoadBalancingService()
        is_load_balancing_enabled, load_balancing_configs = model_load_balancing_service.get_load_balancing_configs(
            tenant_id=tenant_id,
            provider=provider,
            model=args['model'],
            model_type=args['model_type']
        )

        return {
            "credentials": credentials,
            "load_balancing": {
                "enabled": is_load_balancing_enabled,
                "configs": load_balancing_configs
            }
        }


class ModelProviderModelEnableApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    def patch(self, provider: str):
        tenant_id = current_user.current_tenant_id

        parser = reqparse.RequestParser()
        parser.add_argument('model', type=str, required=True, nullable=False, location='json')
        parser.add_argument('model_type', type=str, required=True, nullable=False,
                            choices=[mt.value for mt in ModelType], location='json')
        args = parser.parse_args()

        model_provider_service = ModelProviderService()
        model_provider_service.enable_model(
            tenant_id=tenant_id,
            provider=provider,
            model=args['model'],
            model_type=args['model_type']
        )

        return {'result': 'success'}


class ModelProviderModelDisableApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    def patch(self, provider: str):
        tenant_id = current_user.current_tenant_id

        parser = reqparse.RequestParser()
        parser.add_argument('model', type=str, required=True, nullable=False, location='json')
        parser.add_argument('model_type', type=str, required=True, nullable=False,
                            choices=[mt.value for mt in ModelType], location='json')
        args = parser.parse_args()

        model_provider_service = ModelProviderService()
        model_provider_service.disable_model(
            tenant_id=tenant_id,
            provider=provider,
            model=args['model'],
            model_type=args['model_type']
        )

        return {'result': 'success'}


class ModelProviderModelValidateApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    def post(self, provider: str):
        tenant_id = current_user.current_tenant_id

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
    """
    提供模型参数规则的API接口类

    方法:
    - get: 根据提供者和模型名称获取模型的参数规则
    """

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, provider: str):
        """
        获取指定提供者和模型的参数规则
        
        参数:
        - provider: str，模型的提供者名称
        
        返回值:
        - 返回一个包含模型参数规则的JSON响应
        """
        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('model', type=str, required=True, nullable=False, location='args')
        args = parser.parse_args()

        # 获取当前用户所属的租户ID
        tenant_id = current_user.current_tenant_id

        # 使用模型提供者服务获取模型参数规则
        model_provider_service = ModelProviderService()
        parameter_rules = model_provider_service.get_model_parameter_rules(
            tenant_id=tenant_id,
            provider=provider,
            model=args['model']
        )

        # 返回参数规则的JSON编码结果
        return jsonable_encoder({
            "data": parameter_rules
        })

class ModelProviderAvailableModelApi(Resource):
    """
    提供可用模型的API接口类。
    
    方法:
    - get: 根据模型类型获取可用模型的信息。
    
    参数:
    - model_type: 模型的类型，用于筛选模型。
    
    返回值:
    - 返回一个JSON编码的响应，包含模型信息列表。
    """

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, model_type):
        """
        根据模型类型获取当前用户可用的模型信息。
        
        参数:
        - model_type: 模型的类型，用于查询特定类型的模型。
        
        返回值:
        - 返回一个包含模型信息的JSON响应。
        """
        # 获取当前用户的租户ID
        tenant_id = current_user.current_tenant_id

        # 实例化模型提供者服务，并查询指定类型和租户ID的模型
        model_provider_service = ModelProviderService()
        models = model_provider_service.get_models_by_model_type(
            tenant_id=tenant_id,
            model_type=model_type
        )

        # 返回编码后的模型信息
        return jsonable_encoder({
            "data": models
        })
api.add_resource(ModelProviderModelApi, '/workspaces/current/model-providers/<string:provider>/models')
api.add_resource(ModelProviderModelEnableApi, '/workspaces/current/model-providers/<string:provider>/models/enable',
                 endpoint='model-provider-model-enable')
api.add_resource(ModelProviderModelDisableApi, '/workspaces/current/model-providers/<string:provider>/models/disable',
                 endpoint='model-provider-model-disable')
api.add_resource(ModelProviderModelCredentialApi,
                 '/workspaces/current/model-providers/<string:provider>/models/credentials')
api.add_resource(ModelProviderModelValidateApi,
                 '/workspaces/current/model-providers/<string:provider>/models/credentials/validate')

api.add_resource(ModelProviderModelParameterRuleApi,
                 '/workspaces/current/model-providers/<string:provider>/models/parameter-rules')
api.add_resource(ModelProviderAvailableModelApi, '/workspaces/current/models/model-types/<string:model_type>')
api.add_resource(DefaultModelApi, '/workspaces/current/default-model')
