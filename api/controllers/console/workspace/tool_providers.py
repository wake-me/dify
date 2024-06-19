import io

from flask import current_app, send_file
from flask_login import current_user
from flask_restful import Resource, reqparse
from werkzeug.exceptions import Forbidden

from controllers.console import api
from controllers.console.setup import setup_required
from controllers.console.wraps import account_initialization_required
from core.model_runtime.utils.encoders import jsonable_encoder
from libs.helper import alphanumeric, uuid_value
from libs.login import login_required
from services.tools.api_tools_manage_service import ApiToolManageService
from services.tools.builtin_tools_manage_service import BuiltinToolManageService
from services.tools.tool_labels_service import ToolLabelsService
from services.tools.tools_manage_service import ToolCommonService
from services.tools.workflow_tools_manage_service import WorkflowToolManageService


class ToolProviderListApi(Resource):
    """
    提供工具提供商列表的API接口
    """

    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        user_id = current_user.id
        tenant_id = current_user.current_tenant_id

        req = reqparse.RequestParser()
        req.add_argument('type', type=str, choices=['builtin', 'model', 'api', 'workflow'], required=False, nullable=True, location='args')
        args = req.parse_args()

        return ToolCommonService.list_tool_providers(user_id, tenant_id, args.get('type', None))

class ToolBuiltinProviderListToolsApi(Resource):
    """
    提供内置工具提供商工具列表的API接口
    
    方法: GET
    参数:
    - provider: 工具提供商的标识符
    
    返回值:
    - 返回工具管理服务中列出的指定提供商的内置工具信息
    """

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, provider):
        """
        获取指定提供商的内置工具列表
        
        需要完成设置、登录和账户初始化
        """
        
        # 获取当前登录用户的ID和所在租户的ID
        user_id = current_user.id
        tenant_id = current_user.current_tenant_id

        return jsonable_encoder(BuiltinToolManageService.list_builtin_tool_provider_tools(
            user_id,
            tenant_id,
            provider,
        ))

class ToolBuiltinProviderDeleteApi(Resource):
    """
    提供删除内置工具提供商的API接口。
    
    方法: POST
    路径: /api/tool/builtin/provider/delete
    参数:
    - provider: 要删除的工具提供商名称
    
    返回值:
    - 删除操作的结果，通常为一个包含操作成功与否信息的字典。
    
    需要身份验证和权限检查，确保只有管理员或工具所有者才能执行此操作。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    def post(self, provider):
        # 检查用户是否有权限删除工具提供商，如果不是管理员或所有者，则抛出权限异常
        if not current_user.is_admin_or_owner:
            raise Forbidden()
        
        # 获取当前用户的ID和所属租户的ID
        user_id = current_user.id
        tenant_id = current_user.current_tenant_id

        return BuiltinToolManageService.delete_builtin_tool_provider(
            user_id,
            tenant_id,
            provider,
        )
    
class ToolBuiltinProviderUpdateApi(Resource):
    """
    用于更新内置工具提供商的API接口类。
    
    方法:
    POST: 更新指定提供商的凭证信息。
    
    参数:
    provider (str): 工具提供商的标识符。
    
    返回值:
    更新操作的结果。    
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    def post(self, provider):
        """
        更新内置工具提供商的凭证信息。
        
        权限:
        必须是管理员或工具所有者才有权限执行此操作。
        
        参数:
        provider (str): 要更新的工具提供商标识符。
        
        返回:
        更新操作的结果。
        """
        # 检查当前用户是否有权限更新提供商信息
        if not current_user.is_admin_or_owner:
            raise Forbidden()
        
        # 获取当前用户的ID和租户ID
        user_id = current_user.id
        tenant_id = current_user.current_tenant_id

        # 解析请求中的凭证信息
        parser = reqparse.RequestParser()
        parser.add_argument('credentials', type=dict, required=True, nullable=False, location='json')

        args = parser.parse_args()

        return BuiltinToolManageService.update_builtin_tool_provider(
            user_id,
            tenant_id,
            provider,
            args['credentials'],
        )
    
class ToolBuiltinProviderGetCredentialsApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def get(self, provider):
        user_id = current_user.id
        tenant_id = current_user.current_tenant_id

        return BuiltinToolManageService.get_builtin_tool_provider_credentials(
            user_id,
            tenant_id,
            provider,
        )

class ToolBuiltinProviderIconApi(Resource):
    """
    提供内置工具提供商图标API的类。
    
    方法:
    - get: 根据提供的工具提供商获取其图标。
    
    参数:
    - provider: 工具提供商的标识符。
    
    返回值:
    - 返回工具提供商图标的文件响应，以便在浏览器中显示。
    """
    
    @setup_required
    def get(self, provider):
        icon_bytes, mimetype = BuiltinToolManageService.get_builtin_tool_provider_icon(provider)
        icon_cache_max_age = current_app.config.get('TOOL_ICON_CACHE_MAX_AGE')
        return send_file(io.BytesIO(icon_bytes), mimetype=mimetype, max_age=icon_cache_max_age)

class ToolApiProviderAddApi(Resource):
    """
    用于添加API工具提供者的资源类。
    
    要求用户已登录、账户已初始化且具有管理员或所有者权限。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    def post(self):
        """
        处理POST请求，以添加一个新的API工具提供者。
        
        需要管理员或所有者权限，否则将抛出Forbidden异常。
        
        返回：
            添加成功则返回相关信息，否则抛出异常。
        """
        
        # 检查当前用户是否具有管理员或所有者权限
        if not current_user.is_admin_or_owner:
            raise Forbidden()
        
        # 获取当前用户信息
        user_id = current_user.id
        tenant_id = current_user.current_tenant_id

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('credentials', type=dict, required=True, nullable=False, location='json')
        parser.add_argument('schema_type', type=str, required=True, nullable=False, location='json')
        parser.add_argument('schema', type=str, required=True, nullable=False, location='json')
        parser.add_argument('provider', type=str, required=True, nullable=False, location='json')
        parser.add_argument('icon', type=dict, required=True, nullable=False, location='json')
        parser.add_argument('privacy_policy', type=str, required=False, nullable=True, location='json')
        parser.add_argument('labels', type=list[str], required=False, nullable=True, location='json', default=[])
        parser.add_argument('custom_disclaimer', type=str, required=False, nullable=True, location='json')

        args = parser.parse_args()

        return ApiToolManageService.create_api_tool_provider(
            user_id,
            tenant_id,
            args['provider'],
            args['icon'],
            args['credentials'],
            args['schema_type'],
            args['schema'],
            args.get('privacy_policy', ''),
            args.get('custom_disclaimer', ''),
            args.get('labels', []),
        )

class ToolApiProviderGetRemoteSchemaApi(Resource):
    """
    提供获取远程模式的API接口。
    
    需要完成设置、登录和账户初始化。
    
    GET请求参数:
    - url: 字符串类型，必需，不可为空，通过查询参数传入。
    
    返回值:
    - 返回获取到的远程模式信息。
    """

    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        # 初始化请求解析器
        parser = reqparse.RequestParser()

        # 添加请求参数
        parser.add_argument('url', type=str, required=True, nullable=False, location='args')

        # 解析请求参数
        args = parser.parse_args()

        return ApiToolManageService.get_api_tool_provider_remote_schema(
            current_user.id,
            current_user.current_tenant_id,
            args['url'],
        )
    
class ToolApiProviderListToolsApi(Resource):
    """
    提供工具API提供者列表的接口类。
    
    该类用于通过API获取特定提供者的工具列表。需要用户登录、账户初始化且设定了特定的装饰器来确保安全性。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        """
        获取特定提供商的工具列表。
        
        路径参数：无
        
        查询参数：
        - provider (string): 必需，指定要查询工具的提供商名称。
        
        返回值：
        - 返回一个包含特定提供商工具列表的响应。
        """
        
        # 获取当前登录用户的ID和租户ID
        user_id = current_user.id
        tenant_id = current_user.current_tenant_id

        # 创建请求解析器用于解析查询参数
        parser = reqparse.RequestParser()

        # 添加查询参数'provider'，用于指定工具提供商
        parser.add_argument('provider', type=str, required=True, nullable=False, location='args')

        # 解析查询参数
        args = parser.parse_args()

        return jsonable_encoder(ApiToolManageService.list_api_tool_provider_tools(
            user_id,
            tenant_id,
            args['provider'],
        ))

class ToolApiProviderUpdateApi(Resource):
    """
    用于更新API工具的提供者信息的接口类。
    
    要求用户已登录、账户已初始化且具有管理员或所有者权限。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    def post(self):
        """
        更新API工具的提供者信息。
        
        需要管理员或工具所有者的权限。接收并更新工具的提供者认证信息、架构类型、架构、图标、隐私政策等。
        
        返回值:
            调用ToolManageService.update_api_tool_provider方法的结果。
        """
        
        # 检查用户是否有权限
        if not current_user.is_admin_or_owner:
            raise Forbidden()
        
        # 获取当前用户信息
        user_id = current_user.id
        tenant_id = current_user.current_tenant_id

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('credentials', type=dict, required=True, nullable=False, location='json')
        parser.add_argument('schema_type', type=str, required=True, nullable=False, location='json')
        parser.add_argument('schema', type=str, required=True, nullable=False, location='json')
        parser.add_argument('provider', type=str, required=True, nullable=False, location='json')
        parser.add_argument('original_provider', type=str, required=True, nullable=False, location='json')
        parser.add_argument('icon', type=dict, required=True, nullable=False, location='json')
        parser.add_argument('privacy_policy', type=str, required=True, nullable=True, location='json')
        parser.add_argument('labels', type=list[str], required=False, nullable=True, location='json')
        parser.add_argument('custom_disclaimer', type=str, required=True, nullable=True, location='json')

        args = parser.parse_args()

        return ApiToolManageService.update_api_tool_provider(
            user_id,
            tenant_id,
            args['provider'],
            args['original_provider'],
            args['icon'],
            args['credentials'],
            args['schema_type'],
            args['schema'],
            args['privacy_policy'],
            args['custom_disclaimer'],
            args.get('labels', []),
        )

class ToolApiProviderDeleteApi(Resource):
    """
    提供删除API供应商的功能接口。
    
    要求用户已登录、账号已初始化且有管理员或所有者权限。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    def post(self):
        """
        删除指定的API供应商。
        
        参数:
        - 无（所有必要的参数通过JSON体传入）
        
        返回值:
        - 删除操作的结果。
        
        异常:
        - 如果用户不是管理员或所有者，则抛出Forbidden异常。
        """
        
        # 检查用户权限
        if not current_user.is_admin_or_owner:
            raise Forbidden()
        
        # 获取当前用户信息
        user_id = current_user.id
        tenant_id = current_user.current_tenant_id

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('provider', type=str, required=True, nullable=False, location='json')
        args = parser.parse_args()

        return ApiToolManageService.delete_api_tool_provider(
            user_id,
            tenant_id,
            args['provider'],
        )

class ToolApiProviderGetApi(Resource):
    """
    获取工具API提供者的接口类。
    
    该类用于通过提供的参数获取特定工具API的提供者信息。
    需要用户登录、账户初始化并且设置完成后方可使用。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        """
        获取指定工具API的提供者信息。
        
        参数:
        - 无（所有必要的参数通过URL的查询参数提供）
        
        返回值:
        - 返回一个包含工具API提供者信息的响应。
        """
        
        # 获取当前登录用户的ID和当前租户的ID
        user_id = current_user.id
        tenant_id = current_user.current_tenant_id

        # 创建请求解析器用于解析查询参数
        parser = reqparse.RequestParser()

        # 添加必要的查询参数'provider'，用于指定要查询的API提供者
        parser.add_argument('provider', type=str, required=True, nullable=False, location='args')

        # 解析并获取查询参数
        args = parser.parse_args()

        return ApiToolManageService.get_api_tool_provider(
            user_id,
            tenant_id,
            args['provider'],
        )

class ToolBuiltinProviderCredentialsSchemaApi(Resource):
    """
    提供内置提供商凭证架构的API接口类。
    
    方法:
    - get: 获取指定提供商的内置凭证架构信息。
    
    参数:
    - provider: 字符串，指定的工具提供商标识。
    
    返回值:
    - 返回一个列表，包含指定提供商的凭证架构信息。
    """

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, provider):
        return BuiltinToolManageService.list_builtin_provider_credentials_schema(provider)

class ToolApiProviderSchemaApi(Resource):
    """
    ToolApiProviderSchemaApi类，用于处理工具API提供者模式的API请求。

    属性:
        Resource: 父类，提供RESTful API资源的基本方法。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    def post(self):
        """
        处理POST请求，用于解析并验证API模式。

        要求用户已登录、账号已初始化，且系统已设置。

        参数:
            无

        返回:
            调用ToolManageService.parser_api_schema方法后的返回结果。
        """
        
        parser = reqparse.RequestParser()
        # 创建请求解析器，用于解析JSON请求体中的'schema'参数

        parser.add_argument('schema', type=str, required=True, nullable=False, location='json')
        # 添加'schema'参数解析规则，要求为非空字符串

        args = parser.parse_args()
        # 解析请求体中的参数

        return ApiToolManageService.parser_api_schema(
            schema=args['schema'],
        )
        # 调用服务层方法，处理解析后的API模式

class ToolApiProviderPreviousTestApi(Resource):
    """
    提供工具API的先前测试接口。
    
    该资源需要登录、账户初始化并且设置好之后才能访问。
    使用POST方法来请求一个工具的API测试预览。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    def post(self):
        """
        执行工具API的测试预览。
        
        请求参数:
        - tool_name: 工具名称，必需。
        - provider_name: 提供者名称，可选。
        - credentials: 凭证信息，必需。
        - parameters: 参数，必需。
        - schema_type: 架构类型，必需。
        - schema: 架构信息，必需。
        
        返回值:
        - 返回测试API工具预览的结果。
        """
        parser = reqparse.RequestParser()

        # 解析请求参数
        parser.add_argument('tool_name', type=str, required=True, nullable=False, location='json')
        parser.add_argument('provider_name', type=str, required=False, nullable=False, location='json')
        parser.add_argument('credentials', type=dict, required=True, nullable=False, location='json')
        parser.add_argument('parameters', type=dict, required=True, nullable=False, location='json')
        parser.add_argument('schema_type', type=str, required=True, nullable=False, location='json')
        parser.add_argument('schema', type=str, required=True, nullable=False, location='json')

        args = parser.parse_args()

        return ApiToolManageService.test_api_tool_preview(
            current_user.current_tenant_id,
            args['provider_name'] if args['provider_name'] else '',
            args['tool_name'],
            args['credentials'],
            args['parameters'],
            args['schema_type'],
            args['schema'],
        )

class ToolWorkflowProviderCreateApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def post(self):
        if not current_user.is_admin_or_owner:
            raise Forbidden()
        
        user_id = current_user.id
        tenant_id = current_user.current_tenant_id

        reqparser = reqparse.RequestParser()
        reqparser.add_argument('workflow_app_id', type=uuid_value, required=True, nullable=False, location='json')
        reqparser.add_argument('name', type=alphanumeric, required=True, nullable=False, location='json')
        reqparser.add_argument('label', type=str, required=True, nullable=False, location='json')
        reqparser.add_argument('description', type=str, required=True, nullable=False, location='json')
        reqparser.add_argument('icon', type=dict, required=True, nullable=False, location='json')
        reqparser.add_argument('parameters', type=list[dict], required=True, nullable=False, location='json')
        reqparser.add_argument('privacy_policy', type=str, required=False, nullable=True, location='json', default='')
        reqparser.add_argument('labels', type=list[str], required=False, nullable=True, location='json')

        args = reqparser.parse_args()

        return WorkflowToolManageService.create_workflow_tool(
            user_id,
            tenant_id,
            args['workflow_app_id'],
            args['name'],
            args['label'],
            args['icon'],
            args['description'],
            args['parameters'],
            args['privacy_policy'],
            args.get('labels', []),
        )

class ToolWorkflowProviderUpdateApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def post(self):
        if not current_user.is_admin_or_owner:
            raise Forbidden()
        
        user_id = current_user.id
        tenant_id = current_user.current_tenant_id

        reqparser = reqparse.RequestParser()
        reqparser.add_argument('workflow_tool_id', type=uuid_value, required=True, nullable=False, location='json')
        reqparser.add_argument('name', type=alphanumeric, required=True, nullable=False, location='json')
        reqparser.add_argument('label', type=str, required=True, nullable=False, location='json')
        reqparser.add_argument('description', type=str, required=True, nullable=False, location='json')
        reqparser.add_argument('icon', type=dict, required=True, nullable=False, location='json')
        reqparser.add_argument('parameters', type=list[dict], required=True, nullable=False, location='json')
        reqparser.add_argument('privacy_policy', type=str, required=False, nullable=True, location='json', default='')
        reqparser.add_argument('labels', type=list[str], required=False, nullable=True, location='json')
        
        args = reqparser.parse_args()

        if not args['workflow_tool_id']:
            raise ValueError('incorrect workflow_tool_id')
        
        return WorkflowToolManageService.update_workflow_tool(
            user_id,
            tenant_id,
            args['workflow_tool_id'],
            args['name'],
            args['label'],
            args['icon'],
            args['description'],
            args['parameters'],
            args['privacy_policy'],
            args.get('labels', []),
        )

class ToolWorkflowProviderDeleteApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def post(self):
        if not current_user.is_admin_or_owner:
            raise Forbidden()
        
        user_id = current_user.id
        tenant_id = current_user.current_tenant_id

        reqparser = reqparse.RequestParser()
        reqparser.add_argument('workflow_tool_id', type=uuid_value, required=True, nullable=False, location='json')

        args = reqparser.parse_args()

        return WorkflowToolManageService.delete_workflow_tool(
            user_id,
            tenant_id,
            args['workflow_tool_id'],
        )
        
class ToolWorkflowProviderGetApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        user_id = current_user.id
        tenant_id = current_user.current_tenant_id

        parser = reqparse.RequestParser()
        parser.add_argument('workflow_tool_id', type=uuid_value, required=False, nullable=True, location='args')
        parser.add_argument('workflow_app_id', type=uuid_value, required=False, nullable=True, location='args')

        args = parser.parse_args()

        if args.get('workflow_tool_id'):
            tool = WorkflowToolManageService.get_workflow_tool_by_tool_id(
                user_id,
                tenant_id,
                args['workflow_tool_id'],
            )
        elif args.get('workflow_app_id'):
            tool = WorkflowToolManageService.get_workflow_tool_by_app_id(
                user_id,
                tenant_id,
                args['workflow_app_id'],
            )
        else:
            raise ValueError('incorrect workflow_tool_id or workflow_app_id')

        return jsonable_encoder(tool)
    
class ToolWorkflowProviderListToolApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        user_id = current_user.id
        tenant_id = current_user.current_tenant_id

        parser = reqparse.RequestParser()
        parser.add_argument('workflow_tool_id', type=uuid_value, required=True, nullable=False, location='args')

        args = parser.parse_args()

        return jsonable_encoder(WorkflowToolManageService.list_single_workflow_tools(
            user_id,
            tenant_id,
            args['workflow_tool_id'],
        ))

class ToolBuiltinListApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        user_id = current_user.id
        tenant_id = current_user.current_tenant_id

        return jsonable_encoder([provider.to_dict() for provider in BuiltinToolManageService.list_builtin_tools(
            user_id,
            tenant_id,
        )])
    
class ToolApiListApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        user_id = current_user.id
        tenant_id = current_user.current_tenant_id

        return jsonable_encoder([provider.to_dict() for provider in ApiToolManageService.list_api_tools(
            user_id,
            tenant_id,
        )])
    
class ToolWorkflowListApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        user_id = current_user.id
        tenant_id = current_user.current_tenant_id

        return jsonable_encoder([provider.to_dict() for provider in WorkflowToolManageService.list_tenant_workflow_tools(
            user_id,
            tenant_id,
        )])
    
class ToolLabelsApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        return jsonable_encoder(ToolLabelsService.list_tool_labels())

# tool provider
api.add_resource(ToolProviderListApi, '/workspaces/current/tool-providers')

# builtin tool provider
api.add_resource(ToolBuiltinProviderListToolsApi, '/workspaces/current/tool-provider/builtin/<provider>/tools')
api.add_resource(ToolBuiltinProviderDeleteApi, '/workspaces/current/tool-provider/builtin/<provider>/delete')
api.add_resource(ToolBuiltinProviderUpdateApi, '/workspaces/current/tool-provider/builtin/<provider>/update')
api.add_resource(ToolBuiltinProviderGetCredentialsApi, '/workspaces/current/tool-provider/builtin/<provider>/credentials')
api.add_resource(ToolBuiltinProviderCredentialsSchemaApi, '/workspaces/current/tool-provider/builtin/<provider>/credentials_schema')
api.add_resource(ToolBuiltinProviderIconApi, '/workspaces/current/tool-provider/builtin/<provider>/icon')

# api tool provider
api.add_resource(ToolApiProviderAddApi, '/workspaces/current/tool-provider/api/add')
api.add_resource(ToolApiProviderGetRemoteSchemaApi, '/workspaces/current/tool-provider/api/remote')
api.add_resource(ToolApiProviderListToolsApi, '/workspaces/current/tool-provider/api/tools')
api.add_resource(ToolApiProviderUpdateApi, '/workspaces/current/tool-provider/api/update')
api.add_resource(ToolApiProviderDeleteApi, '/workspaces/current/tool-provider/api/delete')
api.add_resource(ToolApiProviderGetApi, '/workspaces/current/tool-provider/api/get')
api.add_resource(ToolApiProviderSchemaApi, '/workspaces/current/tool-provider/api/schema')
api.add_resource(ToolApiProviderPreviousTestApi, '/workspaces/current/tool-provider/api/test/pre')

# workflow tool provider
api.add_resource(ToolWorkflowProviderCreateApi, '/workspaces/current/tool-provider/workflow/create')
api.add_resource(ToolWorkflowProviderUpdateApi, '/workspaces/current/tool-provider/workflow/update')
api.add_resource(ToolWorkflowProviderDeleteApi, '/workspaces/current/tool-provider/workflow/delete')
api.add_resource(ToolWorkflowProviderGetApi, '/workspaces/current/tool-provider/workflow/get')
api.add_resource(ToolWorkflowProviderListToolApi, '/workspaces/current/tool-provider/workflow/tools')

api.add_resource(ToolBuiltinListApi, '/workspaces/current/tools/builtin')
api.add_resource(ToolApiListApi, '/workspaces/current/tools/api')
api.add_resource(ToolWorkflowListApi, '/workspaces/current/tools/workflow')

api.add_resource(ToolLabelsApi, '/workspaces/current/tool-labels')