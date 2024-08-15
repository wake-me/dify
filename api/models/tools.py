import json

from sqlalchemy import ForeignKey

from core.tools.entities.common_entities import I18nObject
from core.tools.entities.tool_bundle import ApiToolBundle
from core.tools.entities.tool_entities import ApiProviderSchemaType, WorkflowToolParameterConfiguration
from extensions.ext_database import db

from .model import Account, App, Tenant
from .types import StringUUID


class BuiltinToolProvider(db.Model):
    """
    为每个租户存储内置工具提供商信息的表。

    属性:
        id: 工具提供商的唯一标识符。
        tenant_id: 租户的唯一标识符。
        user_id: 创建此工具提供商的用户的唯一标识符。
        provider: 工具提供商的名称。
        encrypted_credentials: 工具提供商的加密凭证。
        created_at: 创建时间。
        updated_at: 更新时间。

    方法:
        credentials: 返回解密的凭证信息（字典格式）。
    """
    __tablename__ = 'tool_builtin_providers'  # 表名
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='tool_builtin_provider_pkey'),  # 主键约束
        # 确保一个租户只能有一个具有相同名称的工具提供商
        db.UniqueConstraint('tenant_id', 'provider', name='unique_builtin_tool_provider')
    )

    # id of the tool provider
    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    # id of the tenant
    tenant_id = db.Column(StringUUID, nullable=True)
    # who created this tool provider
    user_id = db.Column(StringUUID, nullable=False)
    # name of the tool provider
    provider = db.Column(db.String(40), nullable=False)
    # credential of the tool provider
    encrypted_credentials = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))

    @property
    def credentials(self) -> dict:
        """
        获取解密的工具提供商凭证信息。

        返回:
            dict: 包含工具提供商凭证信息的字典。
        """
        return json.loads(self.encrypted_credentials)  # 将加密凭证信息反序列化为字典

class PublishedAppTool(db.Model):
    """
    已发布的应用工具表，用于存储每个人发布的工具应用信息。
    """
    
    __tablename__ = 'tool_published_apps'
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='published_app_tool_pkey'),  # 主键约束
        db.UniqueConstraint('app_id', 'user_id', name='unique_published_app_tool')  # 唯一性约束，确保每个应用对每个人只能发布一次
    )

    # id of the tool provider
    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    # id of the app
    app_id = db.Column(StringUUID, ForeignKey('apps.id'), nullable=False)
    # who published this tool
    user_id = db.Column(StringUUID, nullable=False)
    # description of the tool, stored in i18n format, for human
    description = db.Column(db.Text, nullable=False)
    # 工具的llm描述，供LLM使用
    llm_description = db.Column(db.Text, nullable=False)
    # query description, query will be seem as a parameter of the tool, to describe this parameter to llm, we need this field
    query_description = db.Column(db.Text, nullable=False)
    # 查询名称，查询参数的名称
    query_name = db.Column(db.String(40), nullable=False)
    # 工具提供者的名称
    tool_name = db.Column(db.String(40), nullable=False)
    # 作者
    author = db.Column(db.String(40), nullable=False)
    # 创建时间
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    # 更新时间
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))

    @property
    def description_i18n(self) -> I18nObject:
        """
        获取工具的i18n描述。

        :return: 描述的I18nObject实例。
        """
        return I18nObject(**json.loads(self.description))
    
    @property
    def app(self) -> App:
        """
        获取与当前发布工具关联的应用。

        :return: 关联应用的App实例。
        """
        return db.session.query(App).filter(App.id == self.app_id).first()

class ApiToolProvider(db.Model):
    """
    该类用于表示并操作存储在`tool_api_providers`表中的API提供者信息。

    属性:
    - `id`: 主键，由UUID生成，自动设置默认值
    - `name`: API提供者的名称，类型为字符串，长度不超过40个字符，不能为空
    - `icon`: API提供者的图标链接，类型为字符串，长度不超过255个字符，不能为空
    - `schema`: API原始模式，以文本形式存储，不能为空
    - `schema_type_str`: API模式类型的字符串表示，例如"OAuth2"等，类型为字符串，长度不超过40个字符，不能为空
    - `user_id`: 创建此工具的用户ID，类型为UUID，不能为空
    - `tenant_id`: 所属租户ID，类型为UUID，不能为空
    - `description`: API提供者的描述，以文本形式存储，不能为空
    - `tools_str`: 工具信息，以JSON格式字符串存储，不能为空
    - `credentials_str`: 凭据信息，以JSON格式字符串存储，不能为空
    - `privacy_policy`: 隐私政策链接，类型为字符串，长度不超过255个字符，可为空
    - `created_at`: 记录创建时间，类型为DateTime，自动设置当前时间戳
    - `updated_at`: 记录更新时间，类型为DateTime，自动设置当前时间戳

    方法:
    - `schema_type`: 获取API提供者的模式类型（枚举类型：ApiProviderSchemaType）
    - `tools`: 解析并返回工具信息，类型为ApiBasedToolBundle对象组成的列表
    - `credentials`: 解析并返回凭据信息，类型为字典
    - `is_taned`: 判断是否已分配给特定租户，返回布尔值
    - `user`: 获取创建此工具的用户信息，类型为Account对象
    - `tenant`: 获取与此提供者关联的租户信息，类型为Tenant对象
    """

    __tablename__ = 'tool_api_providers'
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='tool_api_provider_pkey'),
        db.UniqueConstraint('name', 'tenant_id', name='unique_api_tool_provider')
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    # name of the api provider
    name = db.Column(db.String(40), nullable=False)
    icon = db.Column(db.String(255), nullable=False)
    schema = db.Column(db.Text, nullable=False)
    schema_type_str = db.Column(db.String(40), nullable=False)
    # who created this tool
    user_id = db.Column(StringUUID, nullable=False)
    # tenant id
    tenant_id = db.Column(StringUUID, nullable=False)
    # description of the provider
    description = db.Column(db.Text, nullable=False)
    tools_str = db.Column(db.Text, nullable=False)
    credentials_str = db.Column(db.Text, nullable=False)
    privacy_policy = db.Column(db.String(255), nullable=True)
    # custom_disclaimer
    custom_disclaimer = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))

    @property
    def schema_type(self) -> ApiProviderSchemaType:
        """
        获取API提供者的模式类型（枚举类型：ApiProviderSchemaType）
        return: ApiProviderSchemaType
        """
        return ApiProviderSchemaType.value_of(self.schema_type_str)
    
    @property
    def tools(self) -> list[ApiToolBundle]:
        return [ApiToolBundle(**tool) for tool in json.loads(self.tools_str)]
    
    @property
    def credentials(self) -> dict:
        """
        解析并返回凭据信息，类型为字典
        return: dict
        """
        return json.loads(self.credentials_str)
    
    @property
    def user(self) -> Account:
        """
        获取创建此工具的用户信息，类型为Account对象
        return: Account
        """
        return db.session.query(Account).filter(Account.id == self.user_id).first()

    @property
    def tenant(self) -> Tenant:
        """
        获取与此提供者关联的租户信息，类型为Tenant对象
        return: Tenant
        """
        return db.session.query(Tenant).filter(Tenant.id == self.tenant_id).first()

class ToolLabelBinding(db.Model):
    """
    The table stores the labels for tools.
    """
    __tablename__ = 'tool_label_bindings'
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='tool_label_bind_pkey'),
        db.UniqueConstraint('tool_id', 'label_name', name='unique_tool_label_bind'),
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    # tool id
    tool_id = db.Column(db.String(64), nullable=False)
    # tool type
    tool_type = db.Column(db.String(40), nullable=False)
    # label name
    label_name = db.Column(db.String(40), nullable=False)

class WorkflowToolProvider(db.Model):
    """
    The table stores the workflow providers.
    """
    __tablename__ = 'tool_workflow_providers'
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='tool_workflow_provider_pkey'),
        db.UniqueConstraint('name', 'tenant_id', name='unique_workflow_tool_provider'),
        db.UniqueConstraint('tenant_id', 'app_id', name='unique_workflow_tool_provider_app_id'),
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    # name of the workflow provider
    name = db.Column(db.String(40), nullable=False)
    # label of the workflow provider
    label = db.Column(db.String(255), nullable=False, server_default='')
    # icon
    icon = db.Column(db.String(255), nullable=False)
    # app id of the workflow provider
    app_id = db.Column(StringUUID, nullable=False)
    # version of the workflow provider
    version = db.Column(db.String(255), nullable=False, server_default='')
    # who created this tool
    user_id = db.Column(StringUUID, nullable=False)
    # tenant id
    tenant_id = db.Column(StringUUID, nullable=False)
    # description of the provider
    description = db.Column(db.Text, nullable=False)
    # parameter configuration
    parameter_configuration = db.Column(db.Text, nullable=False, server_default='[]')
    # privacy policy
    privacy_policy = db.Column(db.String(255), nullable=True, server_default='')

    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))

    @property
    def schema_type(self) -> ApiProviderSchemaType:
        return ApiProviderSchemaType.value_of(self.schema_type_str)
    
    @property
    def user(self) -> Account:
        return db.session.query(Account).filter(Account.id == self.user_id).first()

    @property
    def tenant(self) -> Tenant:
        return db.session.query(Tenant).filter(Tenant.id == self.tenant_id).first()
    
    @property
    def parameter_configurations(self) -> list[WorkflowToolParameterConfiguration]:
        return [
            WorkflowToolParameterConfiguration(**config)
            for config in json.loads(self.parameter_configuration)
        ]
    
    @property
    def app(self) -> App:
        return db.session.query(App).filter(App.id == self.app_id).first()

class ToolModelInvoke(db.Model):
    """
    用于存储工具调用的执行日志。
    
    属性:
    id: 唯一标识符，使用UUID生成。
    user_id: 调用工具的用户ID，不可为空。
    tenant_id: 租户ID，不可为空。
    provider: 提供者信息，不可为空。
    tool_type: 工具类型，不可为空。
    tool_name: 工具名称，不可为空。
    model_parameters: 调用参数，以文本形式存储，不可为空。
    prompt_messages: 提示信息，以文本形式存储，不可为空。
    model_response: 调用响应，以文本形式存储，不可为空。
    prompt_tokens: 提示令牌数量，不可为空，默认值为0。
    answer_tokens: 答案令牌数量，不可为空，默认值为0。
    answer_unit_price: 答案单价，精确到小数点后4位，不可为空。
    answer_price_unit: 答案价格单位，精确到小数点后7位，默认值为0.001。
    provider_response_latency: 提供者响应延迟，以浮点数表示，不可为空，默认值为0。
    total_price: 总价格，精确到小数点后7位。
    currency: 货币单位，不可为空。
    created_at: 创建时间，不可为空，默认为当前时间。
    updated_at: 更新时间，不可为空，默认为当前时间。
    """
    
    __tablename__ = "tool_model_invokes"
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='tool_model_invoke_pkey'),
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    # who invoke this tool
    user_id = db.Column(StringUUID, nullable=False)
    # tenant id
    tenant_id = db.Column(StringUUID, nullable=False)
    # provider
    provider = db.Column(db.String(40), nullable=False)
    tool_type = db.Column(db.String(40), nullable=False)
    tool_name = db.Column(db.String(40), nullable=False)
    model_parameters = db.Column(db.Text, nullable=False)
    prompt_messages = db.Column(db.Text, nullable=False)
    model_response = db.Column(db.Text, nullable=False)

    prompt_tokens = db.Column(db.Integer, nullable=False, server_default=db.text('0'))
    answer_tokens = db.Column(db.Integer, nullable=False, server_default=db.text('0'))
    answer_unit_price = db.Column(db.Numeric(10, 4), nullable=False)
    answer_price_unit = db.Column(db.Numeric(10, 7), nullable=False, server_default=db.text('0.001'))
    provider_response_latency = db.Column(db.Float, nullable=False, server_default=db.text('0'))
    total_price = db.Column(db.Numeric(10, 7))
    currency = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))

class ToolConversationVariables(db.Model):
    """
    用于存储工具调用过程中产生的会话变量的模型类。
    
    属性：
    - id：记录的唯一标识符，由系统自动生成UUID
    - user_id：参与会话用户的唯一标识符，不可为空
    - tenant_id：所属租户的唯一标识符，不可为空
    - conversation_id：会话的唯一标识符，不可为空
    - variables_str：以文本格式存储的会话变量池，不可为空
    - created_at：记录创建的时间戳，默认为当前时间
    - updated_at：记录最后一次更新的时间戳，默认为当前时间
    
    方法：
    - variables：读取方法，将存储的变量字符串反序列化为字典形式并返回
    """

    __tablename__ = "tool_conversation_variables"  # 数据库表名
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='tool_conversation_variables_pkey'),  # 主键约束
        db.Index('user_id_idx', 'user_id'),  # 用户ID索引
        db.Index('conversation_id_idx', 'conversation_id'),  # 会话ID索引
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    # conversation user id
    user_id = db.Column(StringUUID, nullable=False)
    # tenant id
    tenant_id = db.Column(StringUUID, nullable=False)
    # conversation id
    conversation_id = db.Column(StringUUID, nullable=False)
    # variables pool
    variables_str = db.Column(db.Text, nullable=False)

    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))

    @property
    def variables(self) -> dict:
        """
        获取并解析存储在variables_str中的会话变量。

        返回值：
        - dict类型：包含会话变量的字典对象
        """
        return json.loads(self.variables_str)
    
class ToolFile(db.Model):
    """
    ToolFile 类用于存储代理创建的文件信息。
    
    属性:
    - id: 文件的唯一标识符，使用UUID生成。
    - user_id: 对话用户的ID，不可为空。
    - tenant_id: 租户的ID，不可为空。
    - conversation_id: 对话的ID，不可为空。
    - file_key: 文件的键，不可为空。
    - mimetype: 文件的MIME类型，不可为空。
    - original_url: 文件的原始URL，可以为空。
    
    使用 SQLAlchemy 模型来映射数据库表，表名为 "tool_files"。
    主键约束由 'id' 字段组成，命名为 'tool_file_pkey'。
    为 'conversation_id' 字段添加了索引，以优化查询性能。
    """
    __tablename__ = "tool_files"
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='tool_file_pkey'),
        # 为 conversation_id 字段添加索引以提升查询效率
        db.Index('tool_file_conversation_id_idx', 'conversation_id'),
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    # conversation user id
    user_id = db.Column(StringUUID, nullable=False)
    # tenant id
    tenant_id = db.Column(StringUUID, nullable=False)
    # conversation id
    conversation_id = db.Column(StringUUID, nullable=True)
    # file key
    file_key = db.Column(db.String(255), nullable=False)
    # mime type
    mimetype = db.Column(db.String(255), nullable=False)
    # original url
    original_url = db.Column(db.String(2048), nullable=True)