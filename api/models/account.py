# 导入枚举模块和必要的库
import enum
import json

# 导入Flask-Login的用户混合类和PostgreSQL的UUID类型
from flask_login import UserMixin

# 导入数据库扩展
from extensions.ext_database import db
from models import StringUUID


#
class AccountStatus(str, enum.Enum):
    """
    账户状态枚举类，定义了账户可能的状态。

    参数:
    - str: 继承自字符串类型，使每个枚举值都是一个字符串。
    - enum.Enum: 继承自枚举类型，使AccountStatus成为一个枚举类。

    返回值:
    - 无

    成员:
    - PENDING: 待处理状态
    - UNINITIALIZED: 未初始化状态
    - ACTIVE: 活跃状态
    - BANNED: 禁止状态
    - CLOSED: 关闭状态
    """
    PENDING = 'pending'    # 账户待处理状态
    UNINITIALIZED = 'uninitialized'    # 账户未初始化状态
    ACTIVE = 'active'      # 账户活跃状态
    BANNED = 'banned'      # 账户被禁止状态
    CLOSED = 'closed'      # 账户关闭状态
    
class Account(UserMixin, db.Model):
    """
    账户模型类，用于表示数据库中的账户信息，继承自Flask-Login的UserMixin以及SQLAlchemy的Model，以支持用户认证及数据库操作。

    属性:
    - id: 账户的唯一标识符。
    - name: 账户名称，不可为空。
    - email: 账户邮箱，不可为空且唯一。
    - password: 账户密码，可为空。
    - password_salt: 密码盐值，可为空。
    - avatar: 账户头像地址。
    - interface_language: 用户界面语言。
    - interface_theme: 用户界面主题。
    - timezone: 账户时区。
    - last_login_at: 上次登录时间。
    - last_login_ip: 上次登录IP。
    - last_active_at: 最后活动时间，不可为空。
    - status: 账户状态，默认为'active'。
    - initialized_at: 账户初始化时间。
    - created_at: 账户创建时间，不可为空。
    - updated_at: 账户信息更新时间，不可为空。

    方法:
    - is_password_set: 判断密码是否已设置。
    - current_tenant: 获取/设置当前关联的租户对象及当前租户的角色。
    - current_tenant_id: 获取/设置当前租户的ID。
    - get_status: 获取账户状态。
    - get_by_openid: 根据开放平台提供商和ID获取账户。
    - get_integrates: 获取账户的所有集成信息。
    - is_admin_or_owner: 判断当前用户是否为管理员或所有者。
    """

    __tablename__ = 'accounts'
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='account_pkey'),
        db.Index('account_email_idx', 'email')
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    password = db.Column(db.String(255), nullable=True)
    password_salt = db.Column(db.String(255), nullable=True)
    avatar = db.Column(db.String(255))
    interface_language = db.Column(db.String(255))
    interface_theme = db.Column(db.String(255))
    timezone = db.Column(db.String(255))
    last_login_at = db.Column(db.DateTime)
    last_login_ip = db.Column(db.String(255))
    last_active_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    status = db.Column(db.String(16), nullable=False, server_default=db.text("'active'::character varying"))
    initialized_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))

    @property
    def is_password_set(self):
        """
        判断密码是否已设置。

        返回值:
        - bool: 如果密码已设置则返回True，否则返回False。
        """
        return self.password is not None

    @property
    def current_tenant(self):
        """
        获取/设置当前关联的租户对象及当前租户的角色。

        返回值:
        - Tenant: 当前关联的租户对象。

        设置时，根据传入的租户对象更新其当前角色。
        """
        return self._current_tenant

    @current_tenant.setter
    def current_tenant(self, value: "Tenant"):
        tenant = value
        ta = TenantAccountJoin.query.filter_by(tenant_id=tenant.id, account_id=self.id).first()
        if ta:
            tenant.current_role = ta.role
        else:
            tenant = None
        self._current_tenant = tenant

    @property
    def current_tenant_id(self):
        """
        获取/设置当前租户的ID。

        返回值:
        - int: 当前租户的ID。

        设置时，根据提供的租户ID查找并设置当前租户及其角色。
        """
        return self._current_tenant.id

    @current_tenant_id.setter
    def current_tenant_id(self, value: str):
        try:
            tenant_account_join = db.session.query(Tenant, TenantAccountJoin) \
                .filter(Tenant.id == value) \
                .filter(TenantAccountJoin.tenant_id == Tenant.id) \
                .filter(TenantAccountJoin.account_id == self.id) \
                .one_or_none()

            if tenant_account_join:
                tenant, ta = tenant_account_join
                tenant.current_role = ta.role
            else:
                tenant = None
        except:
            tenant = None

        self._current_tenant = tenant

    @property
    def current_role(self):
        return self._current_tenant.current_role

    def get_status(self) -> AccountStatus:
        """
        获取账户状态。

        返回值:
        - AccountStatus: 账户状态枚举对象。
        """
        status_str = self.status
        return AccountStatus(status_str)

    @classmethod
    def get_by_openid(cls, provider: str, open_id: str) -> db.Model:
        """
        根据开放平台提供商和ID获取账户。

        参数:
        - provider: 提供商名称。
        - open_id: 开放平台账户的ID。

        返回值:
        - db.Model: 匹配的账户模型对象，如果没有找到则返回None。
        """
        account_integrate = db.session.query(AccountIntegrate). \
            filter(AccountIntegrate.provider == provider, AccountIntegrate.open_id == open_id). \
            one_or_none()
        if account_integrate:
            return db.session.query(Account). \
                filter(Account.id == account_integrate.account_id). \
                one_or_none()
        return None

    def get_integrates(self) -> list[db.Model]:
        """
        获取账户的所有集成信息。

        返回值:
        - list[db.Model]: 账户集成信息的模型对象列表。
        """
        ai = db.Model
        return db.session.query(ai).filter(
            ai.account_id == self.id
        ).all()

    # check current_user.current_tenant.current_role in ['admin', 'owner']
    @property
    def is_admin_or_owner(self):
        return TenantAccountRole.is_privileged_role(self._current_tenant.current_role)

    @property
    def is_editor(self):
        return TenantAccountRole.is_editing_role(self._current_tenant.current_role)

    @property
    def is_dataset_editor(self):
        return TenantAccountRole.is_dataset_edit_role(self._current_tenant.current_role)

    @property
    def is_dataset_operator(self):
        return self._current_tenant.current_role == TenantAccountRole.DATASET_OPERATOR

class TenantStatus(str, enum.Enum):
    NORMAL = 'normal'
    ARCHIVE = 'archive'


class TenantAccountRole(str, enum.Enum):
    OWNER = 'owner'
    ADMIN = 'admin'
    EDITOR = 'editor'
    NORMAL = 'normal'
    DATASET_OPERATOR = 'dataset_operator'

    @staticmethod
    def is_valid_role(role: str) -> bool:
        return role and role in {TenantAccountRole.OWNER, TenantAccountRole.ADMIN, TenantAccountRole.EDITOR,
                                 TenantAccountRole.NORMAL, TenantAccountRole.DATASET_OPERATOR}

    @staticmethod
    def is_privileged_role(role: str) -> bool:
        return role and role in {TenantAccountRole.OWNER, TenantAccountRole.ADMIN}
    
    @staticmethod
    def is_non_owner_role(role: str) -> bool:
        return role and role in {TenantAccountRole.ADMIN, TenantAccountRole.EDITOR, TenantAccountRole.NORMAL,
                                 TenantAccountRole.DATASET_OPERATOR}
    
    @staticmethod
    def is_editing_role(role: str) -> bool:
        return role and role in {TenantAccountRole.OWNER, TenantAccountRole.ADMIN, TenantAccountRole.EDITOR}

    @staticmethod
    def is_dataset_edit_role(role: str) -> bool:
        return role and role in {TenantAccountRole.OWNER, TenantAccountRole.ADMIN, TenantAccountRole.EDITOR,
                                 TenantAccountRole.DATASET_OPERATOR}

class Tenant(db.Model):
    """
    租户模型，用于表示一个租户信息
    
    属性:
    - id: 租户唯一标识符，使用UUID生成
    - name: 租户名称，不可为空
    - encrypt_public_key: 加密公钥，可为空
    - plan: 租户订阅计划，不可为空，默认值为'basic'
    - status: 租户状态，不可为空，默认值为'normal'
    - custom_config: 租户自定义配置，以文本形式存储，可为空
    - created_at: 创建时间，不可为空，默认为当前时间
    - updated_at: 更新时间，不可为空，默认为当前时间
    """
    __tablename__ = 'tenants'
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='tenant_pkey'),
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    name = db.Column(db.String(255), nullable=False)
    encrypt_public_key = db.Column(db.Text)
    plan = db.Column(db.String(255), nullable=False, server_default=db.text("'basic'::character varying"))
    status = db.Column(db.String(255), nullable=False, server_default=db.text("'normal'::character varying"))
    custom_config = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))

    def get_accounts(self) -> list[Account]:
        return db.session.query(Account).filter(
            Account.id == TenantAccountJoin.account_id,
            TenantAccountJoin.tenant_id == self.id
        ).all()

    @property
    def custom_config_dict(self) -> dict:
        """
        custom_config属性的字典形式 getter
        
        返回值:
        - custom_config的字典解析结果，如果为空则返回空字典
        """
        return json.loads(self.custom_config) if self.custom_config else {}

    @custom_config_dict.setter
    def custom_config_dict(self, value: dict):
        """
        custom_config属性的字典形式 setter
        
        参数:
        - value: 要设置的字典值
        """
        self.custom_config = json.dumps(value)

class TenantAccountJoinRole(enum.Enum):
    """
    租户账户关联角色枚举
    """
    OWNER = 'owner'
    ADMIN = 'admin'
    NORMAL = 'normal'
    DATASET_OPERATOR = 'dataset_operator'


class TenantAccountJoin(db.Model):
    """
    租户账户关联模型，用于表示租户与账户之间的关联关系
    
    属性:
    - id: 关联唯一标识符，使用UUID生成
    - tenant_id: 关联的租户ID，不可为空
    - account_id: 关联的账户ID，不可为空
    - current: 是否为当前关联，不可为空，默认为false
    - role: 账户在租户中的角色，不可为空，默认为'normal'
    - invited_by: 邀请者的ID，可为空
    - created_at: 创建时间，不可为空，默认为当前时间
    - updated_at: 更新时间，不可为空，默认为当前时间
    """
    __tablename__ = 'tenant_account_joins'
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='tenant_account_join_pkey'),
        db.Index('tenant_account_join_account_id_idx', 'account_id'),
        db.Index('tenant_account_join_tenant_id_idx', 'tenant_id'),
        db.UniqueConstraint('tenant_id', 'account_id', name='unique_tenant_account_join')
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    tenant_id = db.Column(StringUUID, nullable=False)
    account_id = db.Column(StringUUID, nullable=False)
    current = db.Column(db.Boolean, nullable=False, server_default=db.text('false'))
    role = db.Column(db.String(16), nullable=False, server_default='normal')
    invited_by = db.Column(StringUUID, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))


class AccountIntegrate(db.Model):
    """
    账户集成信息模型类，用于表示用户与第三方服务的集成信息。
    
    属性:
    - id: 唯一标识符，使用UUID作为主键。
    - account_id: 关联的账户ID，使用UUID。
    - provider: 提供者名称，例如GitHub、Google等，以字符串形式存储。
    - open_id: 在提供者处的唯一标识符。
    - encrypted_token: 加密的访问令牌。
    - created_at: 记录创建时间。
    - updated_at: 记录更新时间。
    
    表结构:
    - 使用UUID作为主键。
    - 确保每个账户与每个提供者的组合是唯一的。
    - 确保每个提供者和开放ID的组合是唯一的。
    """
    __tablename__ = 'account_integrates'  # 指定数据库表名为account_integrates
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='account_integrate_pkey'),  # 定义主键约束
        db.UniqueConstraint('account_id', 'provider', name='unique_account_provider'),  # 确保账户ID和提供者组合唯一
        db.UniqueConstraint('provider', 'open_id', name='unique_provider_open_id')  # 确保提供者和开放ID组合唯一
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    account_id = db.Column(StringUUID, nullable=False)
    provider = db.Column(db.String(16), nullable=False)
    open_id = db.Column(db.String(255), nullable=False)
    encrypted_token = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))


class InvitationCode(db.Model):
    """
    邀请码模型，用于表示网站或服务的邀请码信息。
    
    属性:
    - id: 邀请码的唯一标识符，整数类型。
    - batch: 邀请码所属的批次，字符串类型。
    - code: 邀请码的代码，字符串类型。
    - status: 邀请码的状态，如未使用、已使用等，字符串类型，默认为'unused'。
    - used_at: 邀请码被使用的时间，日期时间类型。
    - used_by_tenant_id: 使用邀请码的租户ID，UUID类型。
    - used_by_account_id: 使用邀请码的账户ID，UUID类型。
    - deprecated_at: 邀请码废弃的时间，日期时间类型。
    - created_at: 邀请码创建的时间，日期时间类型，不可为空，默认为当前时间。
    """
    
    __tablename__ = 'invitation_codes'  # 指定数据库表名为invitation_codes
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='invitation_code_pkey'),  # 指定id为表的主要键
        db.Index('invitation_codes_batch_idx', 'batch'),  # 为batch创建索引，提升查询效率
        db.Index('invitation_codes_code_idx', 'code', 'status')  # 为code和status创建复合索引
    )

    id = db.Column(db.Integer, nullable=False)
    batch = db.Column(db.String(255), nullable=False)
    code = db.Column(db.String(32), nullable=False)
    status = db.Column(db.String(16), nullable=False, server_default=db.text("'unused'::character varying"))
    used_at = db.Column(db.DateTime)
    used_by_tenant_id = db.Column(StringUUID)
    used_by_account_id = db.Column(StringUUID)
    deprecated_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
