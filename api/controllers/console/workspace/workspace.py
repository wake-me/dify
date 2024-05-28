import logging

from flask import request
from flask_login import current_user
from flask_restful import Resource, fields, inputs, marshal, marshal_with, reqparse
from werkzeug.exceptions import Unauthorized

import services
from controllers.console import api
from controllers.console.admin import admin_required
from controllers.console.datasets.error import (
    FileTooLargeError,
    NoFileUploadedError,
    TooManyFilesError,
    UnsupportedFileTypeError,
)
from controllers.console.error import AccountNotLinkTenantError
from controllers.console.setup import setup_required
from controllers.console.wraps import account_initialization_required, cloud_edition_billing_resource_check
from extensions.ext_database import db
from libs.helper import TimestampField
from libs.login import login_required
from models.account import Tenant, TenantStatus
from services.account_service import TenantService
from services.file_service import FileService
from services.workspace_service import WorkspaceService

# 定义provider的字段信息
provider_fields = {
    'provider_name': fields.String,  # 提供者名称
    'provider_type': fields.String,  # 提供者类型
    'is_valid': fields.Boolean,  # 是否有效
    'token_is_set': fields.Boolean,  # 是否设置了token
}

# 定义tenant的字段信息
tenant_fields = {
    'id': fields.String,  # 租户ID
    'name': fields.String,  # 租户名称
    'plan': fields.String,  # 计划类型
    'status': fields.String,  # 状态
    'created_at': TimestampField,  # 创建时间
    'role': fields.String,  # 角色
    'in_trial': fields.Boolean,  # 是否在试用期
    'trial_end_reason': fields.String,  # 试用结束原因
    'custom_config': fields.Raw(attribute='custom_config'),  # 自定义配置
}

# 定义租户信息的字段结构
tenants_fields = {
    'id': fields.String,  # 租户唯一标识符
    'name': fields.String,  # 租户名称
    'plan': fields.String,  # 租户订阅的计划
    'status': fields.String,  # 租户状态
    'created_at': TimestampField,  # 租户创建时间
    'current': fields.Boolean  # 标记是否为当前租户
}

# 定义工作空间信息的字段结构
workspace_fields = {
    'id': fields.String,  # 工作空间唯一标识符
    'name': fields.String,  # 工作空间名称
    'status': fields.String,  # 工作空间状态
    'created_at': TimestampField  # 工作空间创建时间
}


class TenantListApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        tenants = TenantService.get_join_tenants(current_user)

        for tenant in tenants:
            if tenant.id == current_user.current_tenant_id:
                tenant.current = True  # Set current=True for current tenant
        return {'workspaces': marshal(tenants, tenants_fields)}, 200


class WorkspaceListApi(Resource):
    """
    工作空间列表API，提供获取工作空间列表的功能。
    """

    @setup_required
    @admin_required
    def get(self):
        """
        获取工作空间列表。
        
        参数:
        - page: 请求的页码，默认为1。
        - limit: 每页的工作空间数量，默认为20。
        
        返回值:
        - data: 工作空间列表信息。
        - has_more: 是否还有更多页面。
        - limit: 请求的每页数量。
        - page: 请求的页码。
        - total: 总的工作空间数量。
        """
        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('page', type=inputs.int_range(1, 99999), required=False, default=1, location='args')
        parser.add_argument('limit', type=inputs.int_range(1, 100), required=False, default=20, location='args')
        args = parser.parse_args()

        # 从数据库中获取工作空间信息，并进行分页
        tenants = db.session.query(Tenant).order_by(Tenant.created_at.desc())\
            .paginate(page=args['page'], per_page=args['limit'])

        # 判断是否还有更多的工作空间页
        has_more = False
        if len(tenants.items) == args['limit']:
            current_page_first_tenant = tenants[-1]
            rest_count = db.session.query(Tenant).filter(
                Tenant.created_at < current_page_first_tenant.created_at,
                Tenant.id != current_page_first_tenant.id
            ).count()

            if rest_count > 0:
                has_more = True
        
        # 计算总工作空间数
        total = db.session.query(Tenant).count()
        # 返回工作空间列表信息
        return {
            'data': marshal(tenants.items, workspace_fields),
            'has_more': has_more,
            'limit': args['limit'],
            'page': args['page'],
            'total': total
                }, 200


class TenantApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(tenant_fields)
    def get(self):
        if request.path == '/info':
            logging.warning('Deprecated URL /info was used.')

        tenant = current_user.current_tenant

        if tenant.status == TenantStatus.ARCHIVE:
            tenants = TenantService.get_join_tenants(current_user)
            # if there is any tenant, switch to the first one
            if len(tenants) > 0:
                TenantService.switch_tenant(current_user, tenants[0].id)
                tenant = tenants[0]
            # else, raise Unauthorized
            else:
                raise Unauthorized('workspace is archived')

        return WorkspaceService.get_tenant_info(tenant), 200


class SwitchWorkspaceApi(Resource):
    """
    切换工作空间的API接口类。
    
    需要完成的步骤包括：
    1. 验证用户是否已登录并完成账号初始化；
    2. 接收并解析请求中的tenant_id参数；
    3. 根据tenant_id切换当前用户的工作空间；
    4. 返回切换成功的信息及新工作空间的详细信息。
    
    方法：
    - post: 执行工作空间切换。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    def post(self):
        """
        执行工作空间切换的POST请求处理。
        
        验证用户身份并检查账号是否已链接到租户。若验证通过，尝试切换用户的工作空间至指定租户。
        若切换成功，返回成功信息及新工作空间的详细数据。
        
        参数:
        - 请求体中的json字段包含tenant_id，表示要切换到的目标租户ID，必填。
        
        返回值:
        - 包含切换结果及新工作空间信息的字典。
        """
        parser = reqparse.RequestParser()
        parser.add_argument('tenant_id', type=str, required=True, location='json')
        args = parser.parse_args()

        # 尝试根据提供的tenant_id切换租户，若失败则抛出特定错误
        try:
            TenantService.switch_tenant(current_user, args['tenant_id'])
        except Exception:
            raise AccountNotLinkTenantError("Account not link tenant")

        new_tenant = db.session.query(Tenant).get(args['tenant_id'])  # 获取新切换的租户信息

        # 返回切换成功的消息及新工作空间的详细信息
        return {'result': 'success', 'new_tenant': marshal(WorkspaceService.get_tenant_info(new_tenant), tenant_fields)}


class CustomConfigWorkspaceApi(Resource):
    """
    自定义配置工作空间API接口类，用于处理工作空间的自定义配置请求。
    
    方法:
    - post: 更新工作空间的自定义配置信息。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    @cloud_edition_billing_resource_check('workspace_custom')
    def post(self):
        """
        更新工作空间的自定义配置信息。
        
        接收JSON格式的请求数据，支持修改是否移除Web应用的品牌标识和替换Web应用的Logo。
        
        返回值:
        - 成功更新配置后返回包含成功信息和租户信息的JSON对象。
        """
        
        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('remove_webapp_brand', type=bool, location='json')
        parser.add_argument('replace_webapp_logo', type=str,  location='json')
        args = parser.parse_args()

        tenant = db.session.query(Tenant).filter(Tenant.id == current_user.current_tenant_id).one_or_404()

        custom_config_dict = {
            'remove_webapp_brand': args['remove_webapp_brand'],
            'replace_webapp_logo': args['replace_webapp_logo'] if args['replace_webapp_logo'] is not None else tenant.custom_config_dict.get('replace_webapp_logo') ,
        }

        # 更新租户的自定义配置信息
        tenant.custom_config_dict = custom_config_dict
        db.session.commit()

        # 返回更新成功的信息及租户详细信息
        return {'result': 'success', 'tenant': marshal(WorkspaceService.get_tenant_info(tenant), tenant_fields)}
    

class WebappLogoWorkspaceApi(Resource):
    """
    处理Web应用Logo工作空间API的请求。
    
    要求：
    - 需要设置
    - 需要用户登录
    - 需要账户初始化
    - 需要检查云版本账单资源（工作空间自定义）
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    @cloud_edition_billing_resource_check('workspace_custom')
    def post(self):
        """
        上传文件到工作空间。
        
        接收一个文件，并检查其类型和大小，然后将其上传到服务器。
        
        返回：
        - 上传文件的ID
        - HTTP状态码201（创建成功）
        
        抛出：
        - NoFileUploadedError：如果没有文件被上传
        - TooManyFilesError：如果上传了多个文件
        - UnsupportedFileTypeError：如果文件类型不是SVG或PNG
        - FileTooLargeError：如果文件大小超过限制
        """
        
        # 从请求中获取文件
        file = request.files['file']

        # 检查文件是否上传以及上传的文件数量
        if 'file' not in request.files:
            raise NoFileUploadedError()

        if len(request.files) > 1:
            raise TooManyFilesError()

        # 检查文件扩展名是否支持
        extension = file.filename.split('.')[-1]
        if extension.lower() not in ['svg', 'png']:
            raise UnsupportedFileTypeError()

        try:
            # 尝试上传文件
            upload_file = FileService.upload_file(file, current_user, True)

        except services.errors.file.FileTooLargeError as file_too_large_error:
            # 如果文件过大，抛出异常
            raise FileTooLargeError(file_too_large_error.description)
        except services.errors.file.UnsupportedFileTypeError:
            # 如果文件类型不支持，抛出异常
            raise UnsupportedFileTypeError()
        
        # 返回上传文件的ID
        return { 'id': upload_file.id }, 201


api.add_resource(TenantListApi, '/workspaces')  # GET for getting all tenants
api.add_resource(WorkspaceListApi, '/all-workspaces')  # GET for getting all tenants
api.add_resource(TenantApi, '/workspaces/current', endpoint='workspaces_current')  # GET for getting current tenant info
api.add_resource(TenantApi, '/info', endpoint='info')  # Deprecated
api.add_resource(SwitchWorkspaceApi, '/workspaces/switch')  # POST for switching tenant
api.add_resource(CustomConfigWorkspaceApi, '/workspaces/custom-config')
api.add_resource(WebappLogoWorkspaceApi, '/workspaces/custom-config/webapp-logo/upload')
