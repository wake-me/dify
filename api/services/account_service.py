import base64
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any, Optional

from sqlalchemy import func
from werkzeug.exceptions import Unauthorized

from configs import dify_config
from constants.languages import language_timezone_mapping, languages
from events.tenant_event import tenant_was_created
from extensions.ext_redis import redis_client
from libs.helper import RateLimiter, TokenManager
from libs.passport import PassportService
from libs.password import compare_password, hash_password, valid_password
from libs.rsa import generate_key_pair
from models.account import *
from models.model import DifySetup
from services.errors.account import (
    AccountAlreadyInTenantError,
    AccountLoginError,
    AccountNotLinkTenantError,
    AccountRegisterError,
    CannotOperateSelfError,
    CurrentPasswordIncorrectError,
    InvalidActionError,
    LinkAccountIntegrateError,
    MemberNotInTenantError,
    NoPermissionError,
    RateLimitExceededError,
    RoleAlreadyAssignedError,
    TenantNotFound,
)
from tasks.mail_invite_member_task import send_invite_member_mail_task
from tasks.mail_reset_password_task import send_reset_password_mail_task


class AccountService:

    reset_password_rate_limiter = RateLimiter(
        prefix="reset_password_rate_limit",
        max_attempts=5,
        time_window=60 * 60
    )

    @staticmethod
    def load_user(user_id: str) -> Account:
        """
        根据用户ID加载用户账号信息。
        
        参数:
        user_id (str): 用户的唯一标识符。
        
        返回值:
        Account: 如果找到且账号状态正常，则返回Account对象；否则返回None。
        
        抛出:
        Forbidden: 如果账号被禁用或关闭，抛出Forbidden异常。
        """
        # 从数据库查询账号信息
        account = Account.query.filter_by(id=user_id).first()
        if not account:
            return None  # 账号不存在时返回None

        # 检查账号状态是否为禁用或关闭
        if account.status in [AccountStatus.BANNED.value, AccountStatus.CLOSED.value]:
            raise Unauthorized("Account is banned or closed.")

        # 查询当前有效的租户关联，如果存在则更新账号的当前租户ID
        current_tenant = TenantAccountJoin.query.filter_by(account_id=account.id, current=True).first()
        if current_tenant:
            account.current_tenant_id = current_tenant.tenant_id
        else:
            # 如果没有当前有效的租户关联，查找第一个可用的租户关联并设置为当前
            available_ta = TenantAccountJoin.query.filter_by(account_id=account.id) \
                .order_by(TenantAccountJoin.id.asc()).first()
            if not available_ta:
                return None  # 如果账号没有关联任何租户，则返回None

            account.current_tenant_id = available_ta.tenant_id
            available_ta.current = True
            db.session.commit()  # 提交数据库更改

        if datetime.now(timezone.utc).replace(tzinfo=None) - account.last_active_at > timedelta(minutes=10):
            account.last_active_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.session.commit()

        return account


    @staticmethod
    def get_account_jwt_token(account, *, exp: timedelta = timedelta(days=30)):
        payload = {
            "user_id": account.id,
            "exp": datetime.now(timezone.utc).replace(tzinfo=None) + exp,
            "iss": dify_config.EDITION,
            "sub": 'Console API Passport',
        }

        # 调用PassportService的issue方法，根据负载生成JWT令牌
        token = PassportService().issue(payload)
        return token

    @staticmethod
    def authenticate(email: str, password: str) -> Account:
        """
        使用电子邮件和密码验证账户。

        参数:
        email (str): 用户的电子邮件地址。
        password (str): 用户的密码。

        返回:
        Account: 验证成功返回账户对象。

        异常:
        AccountLoginError: 验证失败时抛出，包括无效的电子邮件或密码、账户被禁用或关闭、账户待激活等情况。
        """

        # 根据电子邮件查询账户信息
        account = Account.query.filter_by(email=email).first()
        if not account:
            raise AccountLoginError('Invalid email or password.')

        # 检查账户状态，禁用或关闭的账户不能登录
        if account.status == AccountStatus.BANNED.value or account.status == AccountStatus.CLOSED.value:
            raise AccountLoginError('Account is banned or closed.')

        # 如果账户状态为待激活，则将其激活
        if account.status == AccountStatus.PENDING.value:
            account.status = AccountStatus.ACTIVE.value
            account.initialized_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.session.commit()

        # 验证密码，不匹配则抛出登录错误
        if account.password is None or not compare_password(password, account.password, account.password_salt):
            raise AccountLoginError('Invalid email or password.')
        return account

    @staticmethod
    def update_account_password(account, password, new_password):
        """
        更新账户密码
        
        参数:
        account: 账户对象，需要包含密码和密码盐的属性。
        password: 当前密码，用于验证用户身份。
        new_password: 新密码，用户设定的用于替换旧密码的密码。
        
        返回值:
        更新后的账户对象。
        
        异常:
        CurrentPasswordIncorrectError: 如果提供的当前密码不正确，则抛出此错误。
        """
        # 验证当前密码是否正确
        if account.password and not compare_password(password, account.password, account.password_salt):
            raise CurrentPasswordIncorrectError("Current password is incorrect.")

        # 验证新密码的有效性
        valid_password(new_password)

        # 生成新的密码盐
        salt = secrets.token_bytes(16)
        base64_salt = base64.b64encode(salt).decode()

        # 使用新密码和盐加密密码
        password_hashed = hash_password(new_password, salt)
        base64_password_hashed = base64.b64encode(password_hashed).decode()
        account.password = base64_password_hashed  # 更新加密后的密码
        account.password_salt = base64_salt  # 更新密码盐
        db.session.commit()  # 提交数据库事务
        return account

    @staticmethod
    def create_account(email: str,
                       name: str,
                       interface_language: str,
                       password: Optional[str] = None,
                       interface_theme: str = 'light') -> Account:
        """create account"""
        account = Account()
        account.email = email
        account.name = name

        if password:
            # 为账户生成密码盐并加密密码
            salt = secrets.token_bytes(16)  # 随机生成密码盐
            base64_salt = base64.b64encode(salt).decode()  # 将密码盐编码为base64格式

            # 使用密码盐加密密码
            password_hashed = hash_password(password, salt)  # 加密密码
            base64_password_hashed = base64.b64encode(password_hashed).decode()  # 将加密后的密码编码为base64格式

            account.password = base64_password_hashed  # 设置加密后的密码
            account.password_salt = base64_salt  # 设置密码盐

        account.interface_language = interface_language  # 设置界面语言
        account.interface_theme = interface_theme  # 设置界面主题

        # 根据界面语言设置时区，默认为UTC
        account.timezone = language_timezone_mapping.get(interface_language, 'UTC')

        db.session.add(account)  # 将新账户添加到数据库会话
        db.session.commit()  # 提交数据库会话，保存新账户
        return account  # 返回新创建的账户对象

    @staticmethod
    def link_account_integrate(provider: str, open_id: str, account: Account) -> None:
        """
        链接账户整合
        
        参数:
        provider: str - 提供者名称，例如'github'、'google'等。
        open_id: str - 由提供者颁发的开放ID。
        account: Account - 需要链接的账户对象。
        
        返回值:
        None
        """
        try:
            # 查询是否存在相同提供者的绑定记录
            account_integrate: Optional[AccountIntegrate] = AccountIntegrate.query.filter_by(account_id=account.id,
                                                                                            provider=provider).first()

            if account_integrate:
                # 如果存在，更新记录
                account_integrate.open_id = open_id
                account_integrate.encrypted_token = ""  # todo
                account_integrate.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            else:
                # 如果不存在，创建新记录
                account_integrate = AccountIntegrate(account_id=account.id, provider=provider, open_id=open_id,
                                                    encrypted_token="")
                db.session.add(account_integrate)

            db.session.commit()
            logging.info(f'Account {account.id} linked {provider} account {open_id}.')
        except Exception as e:
            logging.exception(f'Failed to link {provider} account {open_id} to Account {account.id}')
            # 抛出链接账户整合错误的异常
            raise LinkAccountIntegrateError('Failed to link account.') from e

    @staticmethod
    def close_account(account: Account) -> None:
        """Close account"""
        account.status = AccountStatus.CLOSED.value
        db.session.commit()

    @staticmethod
    def update_account(account, **kwargs):
        """
        更新账户字段
        :param account: 账户对象，需要更新的账户
        :param kwargs: 关键字参数，键为字段名，值为更新的值
        :return: 更新后的账户对象
        """
        # 遍历kwargs，更新account对象的属性
        for field, value in kwargs.items():
            if hasattr(account, field):
                setattr(account, field, value)
            else:
                # 如果账户对象没有该字段，则抛出异常
                raise AttributeError(f"Invalid field: {field}")

        # 提交数据库会话，保存更新
        db.session.commit()
        return account

    @staticmethod
    def update_last_login(account: Account, *, ip_address: str) -> None:
        """Update last login time and ip"""
        account.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)
        account.last_login_ip = ip_address
        db.session.add(account)
        db.session.commit()

    @staticmethod
    def login(account: Account, *, ip_address: Optional[str] = None):
        if ip_address:
            AccountService.update_last_login(account, ip_address=ip_address)
        exp = timedelta(days=30)
        token = AccountService.get_account_jwt_token(account, exp=exp)
        redis_client.set(_get_login_cache_key(account_id=account.id, token=token), '1', ex=int(exp.total_seconds()))
        return token

    @staticmethod
    def logout(*, account: Account, token: str):
        redis_client.delete(_get_login_cache_key(account_id=account.id, token=token))

    @staticmethod
    def load_logged_in_account(*, account_id: str, token: str):
        if not redis_client.get(_get_login_cache_key(account_id=account_id, token=token)):
            return None
        return AccountService.load_user(account_id)

    @classmethod
    def send_reset_password_email(cls, account):
        if cls.reset_password_rate_limiter.is_rate_limited(account.email):
            raise RateLimitExceededError(f"Rate limit exceeded for email: {account.email}. Please try again later.")

        token = TokenManager.generate_token(account, 'reset_password')
        send_reset_password_mail_task.delay(
            language=account.interface_language,
            to=account.email,
            token=token
        )
        cls.reset_password_rate_limiter.increment_rate_limit(account.email)
        return token

    @classmethod
    def revoke_reset_password_token(cls, token: str):
        TokenManager.revoke_token(token, 'reset_password')

    @classmethod
    def get_reset_password_data(cls, token: str) -> Optional[dict[str, Any]]:
        return TokenManager.get_token_data(token, 'reset_password')


def _get_login_cache_key(*, account_id: str, token: str):
    return f"account_login:{account_id}:{token}"


class TenantService:
    """
    租户服务类，提供了一系列静态方法来处理与租户相关的操作，包括创建租户、管理租户成员、切换当前工作空间等。
    
    方法：
    - `create_tenant`: 创建新的租户，并将其与公钥加密关联并保存到数据库。
    - `create_owner_tenant_if_not_exist`: 若不存在所有者租户，则创建一个新的所有者租户，并将指定账户添加为该租户的所有者。
    - `create_tenant_member`: 将账户添加为租户成员，并可指定角色（默认为“normal”）。
    - `get_join_tenants`: 获取指定账户加入的所有租户列表。
    - `get_current_tenant_by_account`: 获取账户当前关联的租户并为其添加角色信息。
    - `switch_tenant`: 切换账户当前的工作空间至指定租户。
    - `get_tenant_members`: 获取租户的所有成员及其对应的角色。
    - `has_roles`: 检查用户在指定租户下是否具有给定的任意角色。
    - `get_user_role`: 获取账户在特定租户下的角色。
    - `get_tenant_count`: 获取数据库中租户的数量。
    - `check_member_permission`: 检查操作员是否有权限对成员进行增删改操作。
    - `remove_member_from_tenant`: 从租户中移除指定成员。
    - `update_member_role`: 更新租户内成员的角色。
    - `dissolve_tenant`: 解散租户，删除其所有成员关系及租户本身。
    - `get_custom_config`: 获取指定租户的自定义配置。
    """

    @staticmethod
    def create_tenant(name: str) -> Tenant:
        """
        创建一个租户

        参数:
        name (str): 租户的名称

        返回值:
        Tenant: 创建的租户对象
        """
        # 创建租户对象
        tenant = Tenant(name=name)

        # 将租户对象添加到数据库会话并提交
        db.session.add(tenant)
        db.session.commit()

        # 为租户生成并设置加密公钥，再次提交数据库
        tenant.encrypt_public_key = generate_key_pair(tenant.id)
        db.session.commit()
        return tenant

    @staticmethod
    def create_owner_tenant_if_not_exist(account: Account):
        """
        如果还未存在，创建一个属于指定账户的owner租户
        参数:
            account: Account - 需要创建租户的账户对象
        返回值:
            无
        """
        # 查询当前账户是否已经关联了租户
        available_ta = TenantAccountJoin.query.filter_by(account_id=account.id) \
            .order_by(TenantAccountJoin.id.asc()).first()

        # 如果已经存在关联租户，则不进行操作
        if available_ta:
            return

        # 创建新的租户，并将账户作为owner角色加入到租户中
        tenant = TenantService.create_tenant(f"{account.name}'s Workspace")
        TenantService.create_tenant_member(tenant, account, role='owner')
        account.current_tenant = tenant
        db.session.commit()  # 提交数据库会话，确保更改被保存
        tenant_was_created.send(tenant)  # 发送租户创建成功的信号

    @staticmethod
    def create_tenant_member(tenant: Tenant, account: Account, role: str = 'normal') -> TenantAccountJoin:
        """
        创建租户成员
        
        参数:
        tenant: Tenant - 租户对象，表示需要添加成员的租户。
        account: Account - 账户对象，表示要添加到租户的成员。
        role: str - 成员的角色，默认为 'normal'。可接受的值包括但不限于 'normal'、'owner'。

        返回值:
        TenantAccountJoin - 表示租户成员关系的对象。

        异常:
        如果尝试将多个‘owner’角色分配给一个租户，将引发异常。
        """

        # 检查是否尝试添加第二个‘owner’角色，如果是，则抛出异常
        if role == TenantAccountJoinRole.OWNER.value:
            if TenantService.has_roles(tenant, [TenantAccountJoinRole.OWNER]):
                logging.error(f'Tenant {tenant.id} has already an owner.')
                raise Exception('Tenant already has an owner.')

        # 创建租户成员关系对象并将其添加到数据库
        ta = TenantAccountJoin(
            tenant_id=tenant.id,
            account_id=account.id,
            role=role
        )
        db.session.add(ta)
        db.session.commit()
        return ta

    @staticmethod
    def get_join_tenants(account: Account) -> list[Tenant]:
        """
        获取账户已加入的租户列表
        
        参数:
        account: Account - 需要查询加入租户的账户对象
        
        返回值:
        list[Tenant] - 账户已加入的租户列表
        """
        return db.session.query(Tenant).join(
            TenantAccountJoin, Tenant.id == TenantAccountJoin.tenant_id
        ).filter(TenantAccountJoin.account_id == account.id, Tenant.status == TenantStatus.NORMAL).all()

    @staticmethod
    def get_current_tenant_by_account(account: Account):
        """
        根据账户获取当前租户，并为其添加角色。
        
        参数:
        account: Account - 需要获取租户信息的账户对象。
        
        返回值:
        返回当前账户所属的租户对象。
        
        抛出异常:
        TenantNotFound - 如果无法找到对应的租户或账户与租户关系时抛出。
        """
        tenant = account.current_tenant  # 尝试从账户获取当前租户
        if not tenant:
            raise TenantNotFound("Tenant not found.")  # 如果租户不存在，则抛出异常

        # 查询账户与租户的关系，尝试更新租户的角色
        ta = TenantAccountJoin.query.filter_by(tenant_id=tenant.id, account_id=account.id).first()
        if ta:
            tenant.role = ta.role  # 如果找到关系，则更新租户角色
        else:
            raise TenantNotFound("Tenant not found for the account.")  # 如果找不到租户与账户的关系，则抛出异常
        return tenant  # 返回更新后的租户对象

    @staticmethod
    def switch_tenant(account: Account, tenant_id: int = None) -> None:
        """
        为账户切换当前的工作空间

        参数:
        account: Account - 需要切换工作空间的账户对象。
        tenant_id: int - 目标工作空间的ID。如果未提供，则抛出异常。

        返回值:
        无
        """

        # 确保提供了tenant_id
        if tenant_id is None:
            raise ValueError("Tenant ID must be provided.")

        tenant_account_join = db.session.query(TenantAccountJoin).join(Tenant, TenantAccountJoin.tenant_id == Tenant.id).filter(
            TenantAccountJoin.account_id == account.id,
            TenantAccountJoin.tenant_id == tenant_id,
            Tenant.status == TenantStatus.NORMAL,
        ).first()

        if not tenant_account_join:
            # 如果未找到关联或账户不是租户的成员，则抛出异常
            raise AccountNotLinkTenantError("Tenant not found or account is not a member of the tenant.")
        else:
            # 更新除当前租户外的所有租户关联的当前状态为False
            TenantAccountJoin.query.filter(TenantAccountJoin.account_id == account.id, TenantAccountJoin.tenant_id != tenant_id).update({'current': False})
            tenant_account_join.current = True
            # 设置账户的当前租户ID
            account.current_tenant_id = tenant_account_join.tenant_id
            db.session.commit()  # 提交数据库会话更改

    @staticmethod
    def get_tenant_members(tenant: Tenant) -> list[Account]:
        """
        获取指定租户的成员列表
        
        参数:
        tenant: Tenant - 需要获取成员的租户对象
        
        返回值:
        list[Account] - 更新后的账户列表，每个账户都附加了其在租户中的角色信息
        """
        
        # 构建SQL查询，获取账户及其在租户中的角色信息
        query = (
            db.session.query(Account, TenantAccountJoin.role)
            .select_from(Account)
            .join(
                TenantAccountJoin, Account.id == TenantAccountJoin.account_id
            )
            .filter(TenantAccountJoin.tenant_id == tenant.id)
        )

        # 初始化一个空列表，用于存储更新后的账户
        updated_accounts = []

        # 执行查询，并为每个账户附加角色信息，将更新后的账户添加到列表中
        for account, role in query:
            account.role = role
            updated_accounts.append(account)

        return updated_accounts

    @staticmethod
    def get_dataset_operator_members(tenant: Tenant) -> list[Account]:
        """Get dataset admin members"""
        query = (
            db.session.query(Account, TenantAccountJoin.role)
            .select_from(Account)
            .join(
                TenantAccountJoin, Account.id == TenantAccountJoin.account_id
            )
            .filter(TenantAccountJoin.tenant_id == tenant.id)
            .filter(TenantAccountJoin.role == 'dataset_operator')
        )

        # Initialize an empty list to store the updated accounts
        updated_accounts = []

        for account, role in query:
            account.role = role
            updated_accounts.append(account)

        return updated_accounts

    @staticmethod
    def get_dataset_operator_members(tenant: Tenant) -> list[Account]:
        """Get dataset admin members"""
        query = (
            db.session.query(Account, TenantAccountJoin.role)
            .select_from(Account)
            .join(
                TenantAccountJoin, Account.id == TenantAccountJoin.account_id
            )
            .filter(TenantAccountJoin.tenant_id == tenant.id)
            .filter(TenantAccountJoin.role == 'dataset_operator')
        )

        # Initialize an empty list to store the updated accounts
        updated_accounts = []

        for account, role in query:
            account.role = role
            updated_accounts.append(account)

        return updated_accounts

    @staticmethod
    def has_roles(tenant: Tenant, roles: list[TenantAccountJoinRole]) -> bool:
        """
        检查用户是否拥有指定租户中的任意一个角色。
        
        参数:
        tenant - 租户对象，用于确定用户所属的租户。
        roles - 角色列表，包含用户可能拥有的多个角色。
        
        返回值:
        bool - 如果用户拥有指定租户中的任意一个角色，则返回True；否则返回False。
        """
        # 检查roles列表中的所有元素是否都为TenantAccountJoinRole类型
        if not all(isinstance(role, TenantAccountJoinRole) for role in roles):
            raise ValueError('all roles must be TenantAccountJoinRole')

        # 查询数据库，检查是否存在租户、角色匹配的记录
        return db.session.query(TenantAccountJoin).filter(
            TenantAccountJoin.tenant_id == tenant.id,
            TenantAccountJoin.role.in_([role.value for role in roles])
        ).first() is not None

    @staticmethod
    def get_user_role(account: Account, tenant: Tenant) -> Optional[TenantAccountJoinRole]:
        """
        获取指定租户下当前账户的角色

        参数:
        account: Account - 需要查询角色的账户对象
        tenant: Tenant - 指定的租户对象

        返回值:
        Optional[TenantAccountJoinRole] - 如果账户在租户中，返回其角色对象；否则返回None
        """
        # 查询数据库，尝试获取账户和租户关联的角色信息
        join = db.session.query(TenantAccountJoin).filter(
            TenantAccountJoin.tenant_id == tenant.id,
            TenantAccountJoin.account_id == account.id
        ).first()
        # 如果找到了关联信息，返回角色对象；否则返回None
        return join.role if join else None

    @staticmethod
    def get_tenant_count() -> int:
        """
        获取租户数量
        
        无参数
        
        返回值:
        int: 租户的数量
        """
        # 从数据库中查询租户数量
        return db.session.query(func.count(Tenant.id)).scalar()

    @staticmethod
    def check_member_permission(tenant: Tenant, operator: Account, member: Account, action: str) -> None:
        """
        检查成员权限

        参数:
        - tenant: 租户对象，表示当前操作的租户
        - operator: 操作者账户对象，执行操作的账户
        - member: 成员账户对象，被操作的账户
        - action: 字符串，指定的操作类型（'add', 'remove', 'update'）

        返回值:
        - 无

        异常:
        - InvalidActionError: 如果操作类型不在['add', 'remove', 'update']中
        - CannotOperateSelfError: 如果操作者尝试操作自己
        - NoPermissionError: 如果操作者没有执行指定操作的权限
        """

        # 定义可执行操作及其所需权限
        perms = {
            'add': [TenantAccountRole.OWNER, TenantAccountRole.ADMIN],
            'remove': [TenantAccountRole.OWNER],
            'update': [TenantAccountRole.OWNER]
        }

        # 检查操作类型是否有效
        if action not in ['add', 'remove', 'update']:
            raise InvalidActionError("Invalid action.")

        # 如果成员账户非空且操作者尝试操作自己，抛出异常
        if member:
            if operator.id == member.id:
                raise CannotOperateSelfError("Cannot operate self.")

        # 查询操作者是否在租户中具有相应权限
        ta_operator = TenantAccountJoin.query.filter_by(
            tenant_id=tenant.id,
            account_id=operator.id
        ).first()

        # 如果查询结果为空或角色不在可执行操作的权限列表中，抛出无权限异常
        if not ta_operator or ta_operator.role not in perms[action]:
            raise NoPermissionError(f'No permission to {action} member.')

    @staticmethod
    def remove_member_from_tenant(tenant: Tenant, account: Account, operator: Account) -> None:
        """
        从租户中移除成员
        
        参数:
        tenant: Tenant - 租户对象，表示需要操作的租户。
        account: Account - 需要被移除的成员账户对象。
        operator: Account - 执行移除操作的管理员账户对象。
        
        返回值:
        None
        """
        # 检查操作者是否尝试移除自己，如果是，则抛出错误
        if operator.id == account.id and TenantService.check_member_permission(tenant, operator, account, 'remove'):
            raise CannotOperateSelfError("Cannot operate self.")

        # 查询指定租户和成员是否存在关联，不存在则抛出错误
        ta = TenantAccountJoin.query.filter_by(tenant_id=tenant.id, account_id=account.id).first()
        if not ta:
            raise MemberNotInTenantError("Member not in tenant.")

        # 删除成员与租户的关联，并提交数据库事务
        db.session.delete(ta)
        db.session.commit()

    @staticmethod
    def update_member_role(tenant: Tenant, member: Account, new_role: str, operator: Account) -> None:
        """
        更新成员的角色
        :param tenant: 租户对象，表示需要操作的租户
        :param member: 账户对象，表示需要更新角色的成员
        :param new_role: 字符串，表示成员新的角色
        :param operator: 账户对象，表示执行操作的管理员
        :return: 无返回值
        """
        # 检查操作者是否有权限更新成员的角色
        TenantService.check_member_permission(tenant, operator, member, 'update')

        # 查询目标成员的加入信息
        target_member_join = TenantAccountJoin.query.filter_by(
            tenant_id=tenant.id,
            account_id=member.id
        ).first()

        # 如果新角色与旧角色相同，则抛出角色已分配错误
        if target_member_join.role == new_role:
            raise RoleAlreadyAssignedError("The provided role is already assigned to the member.")

        # 如果新角色为owner，则查找当前owner并将其角色改为admin
        if new_role == 'owner':
            current_owner_join = TenantAccountJoin.query.filter_by(
                tenant_id=tenant.id,
                role='owner'
            ).first()
            current_owner_join.role = 'admin'

        # 更新目标成员的角色
        target_member_join.role = new_role
        db.session.commit()

    @staticmethod
    def dissolve_tenant(tenant: Tenant, operator: Account) -> None:
        """
        解散租户
        
        参数:
        tenant: Tenant - 需要被解散的租户对象。
        operator: Account - 执行解散操作的账户对象。
        
        返回值:
        None
        
        抛出:
        NoPermissionError - 如果操作者没有权限解散租户，则抛出无权限错误。
        """
        # 检查操作者是否有权限解散租户
        if not TenantService.check_member_permission(tenant, operator, operator, 'remove'):
            raise NoPermissionError('No permission to dissolve tenant.')
        
        # 从数据库中删除租户与账户之间的关联
        db.session.query(TenantAccountJoin).filter_by(tenant_id=tenant.id).delete()
        # 删除租户对象
        db.session.delete(tenant)
        # 提交数据库事务
        db.session.commit()

    @staticmethod
    def get_custom_config(tenant_id: str) -> None:
        """
        获取指定租户的自定义配置。

        参数:
        tenant_id (str): 租户的唯一标识符。

        返回:
        None: 函数直接返回租户的自定义配置字典。
        """
        # 从数据库中查询指定ID的租户信息，如果不存在则返回404错误
        tenant = db.session.query(Tenant).filter(Tenant.id == tenant_id).one_or_404()

        return tenant.custom_config_dict  # 返回租户的自定义配置字典


class RegisterService:
    """
    注册服务类，提供账户注册、邀请成员、生成和验证邀请令牌等功能。

    方法：
    - _get_invitation_token_key(token: str) -> str：根据邀请令牌生成存储在Redis中的键名。
    - register(email, name, ...) -> Account：处理账户注册逻辑，包括创建账户、关联第三方账号（如有）、初始化workspace等操作，并返回注册成功的账户对象。
    - invite_new_member(tenant: Tenant, email: str, ...) -> str：邀请新成员加入指定租户，如果成员不存在则先进行注册，然后添加至租户并发送邀请邮件，最后返回邀请令牌。
    - generate_invite_token(tenant: Tenant, account: Account) -> str：为已注册的账户生成一个邀请令牌，并将其与相关数据一同存储到Redis中，有效期由配置决定。
    - revoke_token(workspace_id: str, email: str, token: str)：撤销特定工作区、邮箱及令牌对应的邀请信息。
    - get_invitation_if_token_valid(workspace_id: str, email: str, token: str) -> Optional[dict[str, Any]]：检查邀请令牌是否有效，并获取对应的有效邀请数据，若有效则返回包含账户、租户等信息的字典，否则返回None。
    - _get_invitation_by_token(token: str, workspace_id: str, email: str) -> Optional[dict[str, str]]：从Redis中根据给定条件获取邀请数据，如果没有找到则返回None。

    """

    @classmethod
    def _get_invitation_token_key(cls, token: str) -> str:
        """
        获取邀请令牌的键名。
        
        参数:
        cls - 类的引用，用于表示这是一个类方法。
        token - 字符串类型，表示邀请令牌。
        
        返回值:
        返回一个字符串，表示邀请令牌在存储系统中的键名。
        """
        return f'member_invite:token:{token}'

    @classmethod
    def setup(cls, email: str, name: str, password: str, ip_address: str) -> None:
        """
        Setup dify

        :param email: email
        :param name: username
        :param password: password
        :param ip_address: ip address
        """
        try:
            # Register
            account = AccountService.create_account(
                email=email,
                name=name,
                interface_language=languages[0],
                password=password,
            )

            account.last_login_ip = ip_address
            account.initialized_at = datetime.now(timezone.utc).replace(tzinfo=None)

            TenantService.create_owner_tenant_if_not_exist(account)

            dify_setup = DifySetup(
                version=dify_config.CURRENT_VERSION
            )
            db.session.add(dify_setup)
            db.session.commit()
        except Exception as e:
            db.session.query(DifySetup).delete()
            db.session.query(TenantAccountJoin).delete()
            db.session.query(Account).delete()
            db.session.query(Tenant).delete()
            db.session.commit()

            logging.exception(f'Setup failed: {e}')
            raise ValueError(f'Setup failed: {e}')

    @classmethod
    def register(cls, email, name,
                 password: Optional[str] = None,
                 open_id: Optional[str] = None,
                 provider: Optional[str] = None,
                 language: Optional[str] = None,
                 status: Optional[AccountStatus] = None) -> Account:
        db.session.begin_nested()
        """
        注册账户

        参数:
        cls - 未知用途，可能与ORM有关
        email - 账户邮箱
        name - 用户名
        password - 账户密码，可选
        open_id - 第三方平台的用户ID，可选
        provider - 第三方平台提供商，如微信、Google，可选
        language - 用户首选语言，如果未指定，则默认为系统配置的第一语言
        status - 账户状态，如果未指定，则默认为激活状态

        返回值:
        Account - 注册成功的账户对象
        """
        try:
            # 创建账户，如果未指定语言则使用默认语言；如果指定了密码，则进行加密处理
            account = AccountService.create_account(
                email=email,
                name=name,
                interface_language=language if language else languages[0],
                password=password
            )
            # 设置账户状态，优先使用传入的状态，若无则设置为激活状态
            account.status = AccountStatus.ACTIVE.value if not status else status.value
            account.initialized_at = datetime.now(timezone.utc).replace(tzinfo=None)

            # 如果有提供open_id和provider，则绑定账户的第三方身份认证
            if open_id is not None or provider is not None:
                AccountService.link_account_integrate(provider, open_id, account)
            if dify_config.EDITION != 'SELF_HOSTED':
                tenant = TenantService.create_tenant(f"{account.name}'s Workspace")
                TenantService.create_tenant_member(tenant, account, role='owner')
                account.current_tenant = tenant
                # 发送租户创建事件
                tenant_was_created.send(tenant)

            db.session.commit()  # 提交数据库事务
        except Exception as e:
            db.session.rollback()
            logging.error(f'Register failed: {e}')
            raise AccountRegisterError(f'Registration failed: {e}') from e

        return account  # 返回创建的账户对象

    @classmethod
    def invite_new_member(cls, tenant: Tenant, email: str, language: str, role: str = 'normal', inviter: Account = None) -> str:
        """
        邀请新的成员加入租户。
        
        参数:
        - cls: 类的引用。
        - tenant: 租户对象，表示邀请加入的租户。
        - email: 被邀请人的邮箱地址，同时也是账户的登录标识。
        - language: 被邀请人的语言偏好。
        - role: 被邀请人在租户中的角色，默认为 'normal'。
        - inviter: 发起邀请的账户对象，默认为 None，表示系统邀请。
        
        返回值:
        - token: 生成的邀请令牌，用于邮件中确认邀请。
        """
        
        # 查询是否已存在该邮箱对应的账户
        account = Account.query.filter_by(email=email).first()

        if not account:
            # 检查邀请者是否有权限添加成员
            TenantService.check_member_permission(tenant, inviter, None, 'add')
            # 从邮箱中提取用户名
            name = email.split('@')[0]

            # 为新邀请的成员注册账户
            account = cls.register(email=email, name=name, language=language, status=AccountStatus.PENDING)
            # 创建新的租户成员关系
            TenantService.create_tenant_member(tenant, account, role)
            # 切换当前账户所属租户为被邀请人
            TenantService.switch_tenant(account, tenant.id)
        else:
            # 检查邀请者是否有权限添加已有账户成员
            TenantService.check_member_permission(tenant, inviter, account, 'add')
            
            # 查询该账户是否已经是当前租户的成员
            ta = TenantAccountJoin.query.filter_by(
                tenant_id=tenant.id,
                account_id=account.id
            ).first()

            if not ta:
                # 如果账户还不是当前租户的成员，则创建成员关系
                TenantService.create_tenant_member(tenant, account, role)

            # 如果账户状态不是待确认（PENDING），则抛出异常，提示账户已存在于租户中
            if account.status != AccountStatus.PENDING.value:
                raise AccountAlreadyInTenantError("Account already in tenant.")

        # 生成邀请令牌
        token = cls.generate_invite_token(tenant, account)

        # 发送邀请邮件
        send_invite_member_mail_task.delay(
            language=account.interface_language,
            to=email,
            token=token,
            inviter_name=inviter.name if inviter else 'Dify',
            workspace_name=tenant.name,
        )

        return token

    @classmethod
    def generate_invite_token(cls, tenant: Tenant, account: Account) -> str:
        """
        生成邀请令牌。

        为指定的租户和账户生成一个唯一的邀请令牌，并将相关邀请信息存储在Redis中，
        以便后续验证和处理。

        参数:
        - cls: 类的引用，用于调用类方法。
        - tenant: 租户对象，包含租户信息。
        - account: 账户对象，包含被邀请人的账户信息。

        返回值:
        - 生成的邀请令牌（字符串）。
        """
        token = str(uuid.uuid4())  # 生成一个随机的UUID作为邀请令牌。
        invitation_data = {
            'account_id': account.id,
            'email': account.email,
            'workspace_id': tenant.id,
        }
        expiryHours = dify_config.INVITE_EXPIRY_HOURS
        redis_client.setex(
            cls._get_invitation_token_key(token),
            expiryHours * 60 * 60,
            json.dumps(invitation_data)
        )
        return token  # 返回生成的邀请令牌。

    @classmethod
    def revoke_token(cls, workspace_id: str, email: str, token: str):
        """
        撤销指定的工作空间ID和电子邮件对应的邀请令牌。
        
        参数:
        - cls: 类的引用，用于调用类方法。
        - workspace_id: str，工作空间的唯一标识符。
        - email: str，被邀请人的电子邮件地址。
        - token: str，需要被撤销的邀请令牌。
        
        返回值:
        - 无返回值。
        """
        if workspace_id and email:
            # 根据电子邮件生成哈希值，并构造缓存键
            email_hash = sha256(email.encode()).hexdigest()
            cache_key = 'member_invite_token:{}, {}:{}'.format(workspace_id, email_hash, token)
            # 从Redis中删除对应的缓存条目
            redis_client.delete(cache_key)
        else:
            # 如果没有提供工作空间ID或电子邮件，则直接通过令牌 key 从Redis删除
            redis_client.delete(cls._get_invitation_token_key(token))

    @classmethod
    def get_invitation_if_token_valid(cls, workspace_id: str, email: str, token: str) -> Optional[dict[str, Any]]:
        """
        根据提供的令牌验证邀请信息的有效性，并返回相关的账户、邀请数据和租户信息。
        
        参数:
        - workspace_id: 工作空间的ID，字符串类型。
        - email: 邀请邮件地址，字符串类型。
        - token: 邀请令牌，用于验证邀请的合法性，字符串类型。
        
        返回值:
        - 如果邀请令牌有效且未过期，并且相关的账户和租户信息存在，则返回一个包含账户、邀请数据和租户信息的字典。
        - 如果邀请无效或已过期，或无法找到相关的账户和租户信息，则返回None。
        """
        # 通过令牌、工作空间ID和电子邮件查询邀请信息
        invitation_data = cls._get_invitation_by_token(token, workspace_id, email)
        if not invitation_data:
            return None

        # 查询租户信息，确保租户存在且状态正常
        tenant = db.session.query(Tenant).filter(
            Tenant.id == invitation_data['workspace_id'],
            Tenant.status == 'normal'
        ).first()

        if not tenant:
            return None

        # 查询账户及其在租户中的角色信息，确保账户存在且与邀请邮件地址匹配
        tenant_account = db.session.query(Account, TenantAccountJoin.role).join(
            TenantAccountJoin, Account.id == TenantAccountJoin.account_id
        ).filter(Account.email == invitation_data['email'], TenantAccountJoin.tenant_id == tenant.id).first()

        if not tenant_account:
            return None

        account = tenant_account[0]
        if not account:
            return None

        # 验证邀请的账户ID是否与查询到的账户ID匹配
        if invitation_data['account_id'] != str(account.id):
            return None

        # 返回验证通过的账户、邀请数据和租户信息
        return {
            'account': account,
            'data': invitation_data,
            'tenant': tenant,
        }

    @classmethod
    def _get_invitation_by_token(cls, token: str, workspace_id: str, email: str) -> Optional[dict[str, str]]:
        """
        根据邀请令牌获取邀请信息。
        
        参数:
        - token: 邀请令牌，字符串类型。
        - workspace_id: 工作空间ID，字符串类型。
        - email: 邀请邮箱，字符串类型。
        
        返回值:
        - 如果找到邀请信息，则返回一个字典，包含账户ID、邮箱和工作空间ID；
        - 如果未找到邀请信息或参数不完整，则返回None。
        """
        if workspace_id is not None and email is not None:
            # 通过邮箱生成哈希值，并构造缓存键
            email_hash = sha256(email.encode()).hexdigest()
            cache_key = f'member_invite_token:{workspace_id}, {email_hash}:{token}'
            account_id = redis_client.get(cache_key)

            if not account_id:
                return None

            # 返回邀请信息字典
            return {
                'account_id': account_id.decode('utf-8'),
                'email': email,
                'workspace_id': workspace_id,
            }
        else:
            # 通过邀请令牌直接从Redis获取邀请信息
            data = redis_client.get(cls._get_invitation_token_key(token))
            if not data:
                return None

            # 解析并返回邀请信息
            invitation = json.loads(data)
            return invitation
