
from flask_login import current_user

from configs import dify_config
from extensions.ext_database import db
from models.account import Tenant, TenantAccountJoin, TenantAccountJoinRole
from services.account_service import TenantService
from services.feature_service import FeatureService


class WorkspaceService:
    """
    工作空间服务类，提供工作空间相关的信息获取和操作方法。
    """
    
    @classmethod
    def get_tenant_info(cls, tenant: Tenant):
        """
        获取租户的信息。

        参数:
        - tenant: Tenant 类型，表示需要获取信息的租户对象。

        返回值:
        - 一个字典，包含租户的各种信息；如果租户对象为空，则返回 None。
        """
        if not tenant:
            return None  # 如果没有租户对象，则直接返回 None

        # 初始化租户信息字典
        tenant_info = {
            'id': tenant.id,
            'name': tenant.name,
            'plan': tenant.plan,
            'status': tenant.status,
            'created_at': tenant.created_at,
            'in_trail': True,
            'trial_end_reason': None,
            'role': 'normal',  # 默认角色为'normal'
        }

        # 查询用户在租户中的角色，并更新到租户信息中
        tenant_account_join = db.session.query(TenantAccountJoin).filter(
            TenantAccountJoin.tenant_id == tenant.id,
            TenantAccountJoin.account_id == current_user.id
        ).first()
        tenant_info['role'] = tenant_account_join.role if tenant_account_join else 'normal'

        # 检查是否可以替换应用图标
        can_replace_logo = FeatureService.get_features(tenant_info['id']).can_replace_logo

        # 如果允许替换图标，并且用户是所有者或管理员，那么提供自定义配置信息
        if can_replace_logo and TenantService.has_roles(tenant, 
        [TenantAccountJoinRole.OWNER, TenantAccountJoinRole.ADMIN]):
            base_url = dify_config.FILES_URL
            replace_webapp_logo = f'{base_url}/files/workspaces/{tenant.id}/webapp-logo' if tenant.custom_config_dict.get('replace_webapp_logo') else None
            remove_webapp_brand = tenant.custom_config_dict.get('remove_webapp_brand', False)

            # 更新租户信息中的自定义配置
            tenant_info['custom_config'] = {
                'remove_webapp_brand': remove_webapp_brand,
                'replace_webapp_logo': replace_webapp_logo,
            }

        return tenant_info  # 返回租户信息字典