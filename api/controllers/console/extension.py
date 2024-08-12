from flask_login import current_user
from flask_restful import Resource, marshal_with, reqparse

from constants import HIDDEN_VALUE
from controllers.console import api
from controllers.console.setup import setup_required
from controllers.console.wraps import account_initialization_required
from fields.api_based_extension_fields import api_based_extension_fields
from libs.login import login_required
from models.api_based_extension import APIBasedExtension
from services.api_based_extension_service import APIBasedExtensionService
from services.code_based_extension_service import CodeBasedExtensionService


class CodeBasedExtensionAPI(Resource):
    """
    代码扩展API类，提供通过代码模块名获取代码扩展信息的功能。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        """
        处理GET请求，获取指定模块的代码扩展信息。
        
        参数:
        - 无
        
        返回值:
        - 一个包含模块名和对应代码扩展信息的字典。
        """
        # 创建请求参数解析器并添加'module'参数
        parser = reqparse.RequestParser()
        parser.add_argument('module', type=str, required=True, location='args')
        # 解析请求参数
        args = parser.parse_args()

        # 返回模块名和对应的代码扩展信息
        return {
            'module': args['module'],
            'data': CodeBasedExtensionService.get_code_based_extension(args['module'])
        }

class APIBasedExtensionAPI(Resource):
    """
    基于API的扩展API类，提供创建和获取基于API的扩展信息的接口。
    """

    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(api_based_extension_fields)
    def get(self):
        """
        获取当前租户的所有API扩展信息。
        
        需要身份验证和账户初始化。
        
        返回值:
            根据api_based_extension_fields字段定义的列表，包含所有租户的API扩展信息。
        """
        tenant_id = current_user.current_tenant_id  # 获取当前用户所属的租户ID
        return APIBasedExtensionService.get_all_by_tenant_id(tenant_id)  # 根据租户ID查询并返回所有API扩展信息

    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(api_based_extension_fields)
    def post(self):
        """
        创建一个新的API扩展信息。
        
        需要身份验证和账户初始化。
        
        参数:
            - name: 扩展的名称，必填。
            - api_endpoint: API端点地址，必填。
            - api_key: API的密钥，必填。
        
        返回值:
            创建的API扩展信息。
        """
        parser = reqparse.RequestParser()  # 创建请求解析器
        parser.add_argument('name', type=str, required=True, location='json')
        parser.add_argument('api_endpoint', type=str, required=True, location='json')
        parser.add_argument('api_key', type=str, required=True, location='json')
        args = parser.parse_args()  # 解析请求参数

        # 创建API扩展实例
        extension_data = APIBasedExtension(
            tenant_id=current_user.current_tenant_id,
            name=args['name'],
            api_endpoint=args['api_endpoint'],
            api_key=args['api_key']
        )

        return APIBasedExtensionService.save(extension_data)  # 保存API扩展信息


class APIBasedExtensionDetailAPI(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(api_based_extension_fields)
    def get(self, id):
        api_based_extension_id = str(id)
        tenant_id = current_user.current_tenant_id

        return APIBasedExtensionService.get_with_tenant_id(tenant_id, api_based_extension_id)

    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(api_based_extension_fields)
    def post(self, id):
        api_based_extension_id = str(id)
        tenant_id = current_user.current_tenant_id

        extension_data_from_db = APIBasedExtensionService.get_with_tenant_id(tenant_id, api_based_extension_id)

        parser = reqparse.RequestParser()
        parser.add_argument('name', type=str, required=True, location='json')
        parser.add_argument('api_endpoint', type=str, required=True, location='json')
        parser.add_argument('api_key', type=str, required=True, location='json')
        args = parser.parse_args()

        extension_data_from_db.name = args['name']
        extension_data_from_db.api_endpoint = args['api_endpoint']

        if args['api_key'] != HIDDEN_VALUE:
            extension_data_from_db.api_key = args['api_key']

        return APIBasedExtensionService.save(extension_data_from_db)

    @setup_required
    @login_required
    @account_initialization_required
    def delete(self, id):
        api_based_extension_id = str(id)
        tenant_id = current_user.current_tenant_id

        extension_data_from_db = APIBasedExtensionService.get_with_tenant_id(tenant_id, api_based_extension_id)

        APIBasedExtensionService.delete(extension_data_from_db)

        return {'result': 'success'}


api.add_resource(CodeBasedExtensionAPI, '/code-based-extension')

api.add_resource(APIBasedExtensionAPI, '/api-based-extension')
api.add_resource(APIBasedExtensionDetailAPI, '/api-based-extension/<uuid:id>')
