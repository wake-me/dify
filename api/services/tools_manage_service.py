import json
import logging

from httpx import get

from core.model_runtime.utils.encoders import jsonable_encoder
from core.tools.entities.common_entities import I18nObject
from core.tools.entities.tool_bundle import ApiBasedToolBundle
from core.tools.entities.tool_entities import (
    ApiProviderAuthType,
    ApiProviderSchemaType,
    ToolCredentialsOption,
    ToolProviderCredentials,
)
from core.tools.entities.user_entities import UserTool, UserToolProvider
from core.tools.errors import ToolNotFoundError, ToolProviderCredentialValidationError, ToolProviderNotFoundError
from core.tools.provider.api_tool_provider import ApiBasedToolProviderController
from core.tools.provider.builtin._positions import BuiltinToolProviderSort
from core.tools.provider.tool_provider import ToolProviderController
from core.tools.tool_manager import ToolManager
from core.tools.utils.configuration import ToolConfigurationManager
from core.tools.utils.parser import ApiBasedToolSchemaParser
from extensions.ext_database import db
from models.tools import ApiToolProvider, BuiltinToolProvider
from services.model_provider_service import ModelProviderService
from services.tools_transform_service import ToolTransformService

logger = logging.getLogger(__name__)


class ToolManageService:
    @staticmethod
    def list_tool_providers(user_id: str, tenant_id: str):
        """
        列出工具提供者

        :param user_id: 用户ID，类型为字符串
        :param tenant_id: 租户ID，类型为字符串
        :return: 工具提供者列表，返回类型为列表
        """
        providers = ToolManager.user_list_providers(
            user_id, tenant_id
        )

        # add icon
        for provider in providers:
            ToolTransformService.repack_provider(provider)

        result = [provider.to_dict() for provider in providers]

        return result
    
    @staticmethod
    def list_builtin_tool_provider_tools(
        user_id: str, tenant_id: str, provider: str
    ) -> list[UserTool]:
        """
        列出内置工具提供商的工具列表。

        参数:
        - user_id: 用户ID，字符串类型，用于标识请求的用户。
        - tenant_id: 租户ID，字符串类型，用于标识用户所属的租户。
        - provider: 工具提供商的标识符，字符串类型，用于指定要查询的工具提供商。

        返回值:
        - 返回一个序列化后的用户工具列表，每个用户工具包含作者、名称、标签、描述和参数信息。
        """

        # 获取指定提供商的工具控制器
        provider_controller: ToolProviderController = ToolManager.get_builtin_provider(provider)
        tools = provider_controller.get_tools()

        # 初始化工具配置管理器
        tool_provider_configurations = ToolConfigurationManager(tenant_id=tenant_id, provider_controller=provider_controller)
        
        # 检查用户是否已添加该提供商
        builtin_provider: BuiltinToolProvider = db.session.query(BuiltinToolProvider).filter(
            BuiltinToolProvider.tenant_id == tenant_id,
            BuiltinToolProvider.provider == provider,
        ).first()

        credentials = {}
        if builtin_provider is not None:
            # 解密工具的凭证信息
            credentials = builtin_provider.credentials
            credentials = tool_provider_configurations.decrypt_tool_credentials(credentials)

        result = []
        for tool in tools:
            result.append(ToolTransformService.tool_to_user_tool(
                tool=tool, credentials=credentials, tenant_id=tenant_id
            ))

        return result
    
    @staticmethod
    def list_builtin_provider_credentials_schema(
        provider_name
    ):
        """
            列出内置提供者凭证架构列表

            :param provider_name: 提供者名称
            :type provider_name: str
            :return: 工具提供者的凭证架构列表
            :rtype: list
        """
        # 获取指定名称的内置提供者
        provider = ToolManager.get_builtin_provider(provider_name)
        return jsonable_encoder([
            v for _, v in (provider.credentials_schema or {}).items()
        ])

    @staticmethod
    def parser_api_schema(schema: str) -> list[ApiBasedToolBundle]:
        """
        解析 API 架构到工具捆绑包

        参数:
        schema: str - 待解析的API架构字符串。

        返回值:
        list[ApiBasedToolBundle] - 解析后得到的工具捆绑包列表。
        """
        try:
            warnings = {}  # 用于收集解析过程中的警告信息

            # 尝试自动解析API架构到工具捆绑包和架构类型
            try:
                tool_bundles, schema_type = ApiBasedToolSchemaParser.auto_parse_to_tool_bundle(schema, warning=warnings)
            except Exception as e:
                # 如果解析失败，抛出无效架构的错误
                raise ValueError(f'invalid schema: {str(e)}')
            
            # 定义认证信息的架构，包括认证类型选择、API Key头部和API Key值
            credentials_schema = [
                ToolProviderCredentials(
                    name='auth_type',
                    type=ToolProviderCredentials.CredentialsType.SELECT,
                    required=True,
                    default='none',
                    options=[
                        ToolCredentialsOption(value='none', label=I18nObject(
                            en_US='None',
                            zh_Hans='无'
                        )),
                        ToolCredentialsOption(value='api_key', label=I18nObject(
                            en_US='Api Key',
                            zh_Hans='Api Key'
                        )),
                    ],
                    placeholder=I18nObject(
                        en_US='Select auth type',
                        zh_Hans='选择认证方式'
                    )
                ),
                ToolProviderCredentials(
                    name='api_key_header',
                    type=ToolProviderCredentials.CredentialsType.TEXT_INPUT,
                    required=False,
                    placeholder=I18nObject(
                        en_US='Enter api key header',
                        zh_Hans='输入 api key header，如：X-API-KEY'
                    ),
                    default='api_key',
                    help=I18nObject(
                        en_US='HTTP header name for api key',
                        zh_Hans='HTTP 头部字段名，用于传递 api key'
                    )
                ),
                ToolProviderCredentials(
                    name='api_key_value',
                    type=ToolProviderCredentials.CredentialsType.TEXT_INPUT,
                    required=False,
                    placeholder=I18nObject(
                        en_US='Enter api key',
                        zh_Hans='输入 api key'
                    ),
                    default=''
                ),
            ]

            return jsonable_encoder({
                'schema_type': schema_type,
                'parameters_schema': tool_bundles,
                'credentials_schema': credentials_schema,
                'warning': warnings
            })
        except Exception as e:
            # 任何其他异常都视为无效架构，并抛出错误
            raise ValueError(f'invalid schema: {str(e)}')

    @staticmethod
    def convert_schema_to_tool_bundles(schema: str, extra_info: dict = None) -> list[ApiBasedToolBundle]:
        """
        将架构转换为工具包列表

        :param schema: 待转换的架构字符串
        :param extra_info: 额外信息字典，可选参数，默认为None
        :return: 工具包列表，包含根据架构解析得到的ApiBasedToolBundle对象
        """
        try:
            # 自动解析架构字符串为工具包列表
            tool_bundles = ApiBasedToolSchemaParser.auto_parse_to_tool_bundle(schema, extra_info=extra_info)
            return tool_bundles
        except Exception as e:
            raise ValueError(f'invalid schema: {str(e)}')

    @staticmethod
    def create_api_tool_provider(
        user_id: str, tenant_id: str, provider_name: str, icon: dict, credentials: dict,
        schema_type: str, schema: str, privacy_policy: str
    ):
        """
        创建一个API工具提供者。

        参数:
        - user_id: 用户ID，字符串类型，标识创建此工具提供者的用户。
        - tenant_id: 租户ID，字符串类型，标识此工具提供者所属的租户。
        - provider_name: 提供者名称，字符串类型，唯一标识一个工具提供者。
        - icon: 图标信息，字典类型，包含图标的元数据。
        - credentials: 凭据信息，字典类型，用于认证和授权。
        - schema_type: 架构类型，字符串类型，定义了工具提供者的数据架构。
        - schema: 架构定义，字符串类型，详细描述了工具提供者的数据模型。
        - privacy_policy: 隐私政策，字符串类型，描述了提供者如何处理用户数据。

        返回值:
        - 字典类型，包含单一键值对{'result': 'success'}，表示操作成功。
        """

        # 校验架构类型是否有效
        if schema_type not in [member.value for member in ApiProviderSchemaType]:
            raise ValueError(f'invalid schema type {schema}')
        
        # 检查提供者是否已存在
        provider: ApiToolProvider = db.session.query(ApiToolProvider).filter(
            ApiToolProvider.tenant_id == tenant_id,
            ApiToolProvider.name == provider_name,
        ).first()

        if provider is not None:
            raise ValueError(f'provider {provider_name} already exists')

        # 解析OpenAPI到工具包
        extra_info = {}
        # 额外信息如描述将在这里设置
        tool_bundles, schema_type = ToolManageService.convert_schema_to_tool_bundles(schema, extra_info)
        
        if len(tool_bundles) > 100:
            raise ValueError('the number of apis should be less than 100')

        # 创建数据库提供者记录
        db_provider = ApiToolProvider(
            tenant_id=tenant_id,
            user_id=user_id,
            name=provider_name,
            icon=json.dumps(icon),
            schema=schema,
            description=extra_info.get('description', ''),
            schema_type_str=schema_type,
            tools_str=json.dumps(jsonable_encoder(tool_bundles)),
            credentials_str={},
            privacy_policy=privacy_policy
        )

        if 'auth_type' not in credentials:
            raise ValueError('auth_type is required')

        # 获取认证类型，无或API密钥
        auth_type = ApiProviderAuthType.value_of(credentials['auth_type'])

        # 创建提供者实体
        provider_controller = ApiBasedToolProviderController.from_db(db_provider, auth_type)
        # 将工具加载到提供者实体中
        provider_controller.load_bundled_tools(tool_bundles)

        # 加密凭据信息
        tool_configuration = ToolConfigurationManager(tenant_id=tenant_id, provider_controller=provider_controller)
        encrypted_credentials = tool_configuration.encrypt_tool_credentials(credentials)
        db_provider.credentials_str = json.dumps(encrypted_credentials)

        # 将提供者记录添加到数据库并提交事务
        db.session.add(db_provider)
        db.session.commit()

        return { 'result': 'success' }
    
    @staticmethod
    def get_api_tool_provider_remote_schema(
        user_id: str, tenant_id: str, url: str
    ):
        """
        获取 API 工具提供者的远程模式

        参数:
        - user_id: 用户ID，字符串类型，用于标识请求的用户
        - tenant_id: 租户ID，字符串类型，用于标识用户所属的租户
        - url: 远程模式的URL地址，字符串类型

        返回值:
        - 一个字典，包含远程模式的文本内容:
        {
            'schema': 模式文本
        }
        """

        # 设置HTTP请求头，伪装为浏览器访问以避免被识别为自动化请求
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
            "Accept": "*/*",
        }

        try:
            # 向指定URL发起GET请求
            response = get(url, headers=headers, timeout=10)
            # 如果响应状态码不是200，抛出异常
            if response.status_code != 200:
                raise ValueError(f'Got status code {response.status_code}')
            schema = response.text

            # 尝试解析模式文本，避免SSRF攻击
            ToolManageService.parser_api_schema(schema)
        except Exception as e:
            # 记录解析模式错误的日志
            logger.error(f"parse api schema error: {str(e)}")
            # 如果解析失败，抛出无效模式的异常
            raise ValueError('invalid schema, please check the url you provided')
        
        # 返回解析后的模式
        return {
            'schema': schema
        }

    @staticmethod
    def list_api_tool_provider_tools(
        user_id: str, tenant_id: str, provider: str
    ) -> list[UserTool]:
        """
        列出指定服务提供商的工具列表。

        参数:
        - user_id: 用户ID，字符串类型，用于标识请求的用户。
        - tenant_id: 租户ID，字符串类型，用于确定操作的租户范围。
        - provider: 服务提供商名称，字符串类型，指定要查询的工具提供商。

        返回值:
        - 返回一个JSON对象，包含指定服务提供商的所有工具信息。

        抛出:
        - ValueError: 如果指定的服务提供商不存在，则抛出此异常。
        """
        
        # 从数据库中查询指定租户ID和名称的服务提供商
        provider: ApiToolProvider = db.session.query(ApiToolProvider).filter(
            ApiToolProvider.tenant_id == tenant_id,
            ApiToolProvider.name == provider,
        ).first()

        if provider is None:
            # 如果查询不到指定的服务提供商，抛出异常
            raise ValueError(f'you have not added provider {provider}')
        
        return [
            ToolTransformService.tool_to_user_tool(tool_bundle) for tool_bundle in provider.tools
        ]

    @staticmethod
    def update_builtin_tool_provider(
        user_id: str, tenant_id: str, provider_name: str, credentials: dict
    ):
        """
        更新内置工具提供商的凭证信息。

        参数:
        - user_id: 用户ID，字符串类型，标识更新操作的用户。
        - tenant_id: 租户ID，字符串类型，标识提供商所属的租户。
        - provider_name: 提供商名称，字符串类型，标识要更新的工具提供商。
        - credentials: 凭证字典，包含更新后的提供商凭证信息。

        返回值:
        - 字典，包含结果信息，例如 {'result': 'success'} 表示更新成功。
        """
        # 检查提供商是否已存在
        provider: BuiltinToolProvider = db.session.query(BuiltinToolProvider).filter(
            BuiltinToolProvider.tenant_id == tenant_id,
            BuiltinToolProvider.provider == provider_name,
        ).first()

        try: 
            # 获取提供商控制器，并验证凭证是否必要
            provider_controller = ToolManager.get_builtin_provider(provider_name)
            if not provider_controller.need_credentials:
                raise ValueError(f'provider {provider_name} does not need credentials')
            tool_configuration = ToolConfigurationManager(tenant_id=tenant_id, provider_controller=provider_controller)
            # 如果存在原始凭证，则解密并比对新旧凭证
            if provider is not None:
                original_credentials = tool_configuration.decrypt_tool_credentials(provider.credentials)
                masked_credentials = tool_configuration.mask_tool_credentials(original_credentials)
                # 检查凭证是否有变化，如有则保存原始凭证
                for name, value in credentials.items():
                    if name in masked_credentials and value == masked_credentials[name]:
                        credentials[name] = original_credentials[name]
            # 验证更新后的凭证信息
            provider_controller.validate_credentials(credentials)
            # 加密更新后的凭证信息
            credentials = tool_configuration.encrypt_tool_credentials(credentials)
        except (ToolProviderNotFoundError, ToolNotFoundError, ToolProviderCredentialValidationError) as e:
            raise ValueError(str(e))

        if provider is None:
            # 如果提供商不存在，则创建新提供商并保存凭证
            provider = BuiltinToolProvider(
                tenant_id=tenant_id,
                user_id=user_id,
                provider=provider_name,
                encrypted_credentials=json.dumps(credentials),
            )

            db.session.add(provider)
            db.session.commit()

        else:
            # 如果提供商已存在，则更新凭证信息并提交
            provider.encrypted_credentials = json.dumps(credentials)
            db.session.add(provider)
            db.session.commit()

            # 删除凭证缓存
            tool_configuration.delete_tool_credentials_cache()

        return { 'result': 'success' }
    
    @staticmethod
    def get_builtin_tool_provider_credentials(
        user_id: str, tenant_id: str, provider: str
    ):
        """
            get builtin tool provider credentials
        """
        provider: BuiltinToolProvider = db.session.query(BuiltinToolProvider).filter(
            BuiltinToolProvider.tenant_id == tenant_id,
            BuiltinToolProvider.provider == provider,
        ).first()

        if provider is None:
            return {}
        
        provider_controller = ToolManager.get_builtin_provider(provider.provider)
        tool_configuration = ToolConfigurationManager(tenant_id=tenant_id, provider_controller=provider_controller)
        credentials = tool_configuration.decrypt_tool_credentials(provider.credentials)
        credentials = tool_configuration.mask_tool_credentials(credentials)
        return credentials

    @staticmethod
    def update_api_tool_provider(
        user_id: str, tenant_id: str, provider_name: str, original_provider: str, icon: dict, credentials: dict, 
        schema_type: str, schema: str, privacy_policy: str
    ):
        """
        更新 API 工具提供者的信息。

        参数:
        - user_id: 用户ID，字符串类型。
        - tenant_id: 租户ID，字符串类型。
        - provider_name: 新的工具提供者名称，字符串类型。
        - original_provider: 原始工具提供者名称，字符串类型。
        - icon: 提供者图标信息，字典类型。
        - credentials: 认证信息，字典类型。
        - schema_type: 架构类型，字符串类型。
        - schema: 架构定义，字符串类型。
        - privacy_policy: 隐私政策，字符串类型。

        返回值:
        - 字典类型，包含结果信息。
        """
        # 校验架构类型是否有效
        if schema_type not in [member.value for member in ApiProviderSchemaType]:
            raise ValueError(f'invalid schema type {schema}')
        
        # 检查提供者是否存在
        provider: ApiToolProvider = db.session.query(ApiToolProvider).filter(
            ApiToolProvider.tenant_id == tenant_id,
            ApiToolProvider.name == original_provider,
        ).first()

        if provider is None:
            raise ValueError(f'api provider {provider_name} does not exists')

        # 将OpenAPI解析为工具包
        extra_info = {}
        # 在此处设置额外信息，如描述
        tool_bundles, schema_type = ToolManageService.convert_schema_to_tool_bundles(schema, extra_info)
        
        # 更新数据库中的提供者信息
        provider.name = provider_name
        provider.icon = json.dumps(icon)
        provider.schema = schema
        provider.description = extra_info.get('description', '')
        provider.schema_type_str = ApiProviderSchemaType.OPENAPI.value
        provider.tools_str = json.dumps(jsonable_encoder(tool_bundles))
        provider.privacy_policy = privacy_policy

        if 'auth_type' not in credentials:
            raise ValueError('auth_type is required')

        # 获取认证类型，无或API密钥
        auth_type = ApiProviderAuthType.value_of(credentials['auth_type'])

        # 创建提供者实体
        provider_controller = ApiBasedToolProviderController.from_db(provider, auth_type)
        # 将工具加载到提供者实体中
        provider_controller.load_bundled_tools(tool_bundles)

        # 获取原始认证信息，如果存在
        tool_configuration = ToolConfigurationManager(tenant_id=tenant_id, provider_controller=provider_controller)

        original_credentials = tool_configuration.decrypt_tool_credentials(provider.credentials)
        masked_credentials = tool_configuration.mask_tool_credentials(original_credentials)
        # 检查认证信息是否更改，保存原始认证信息
        for name, value in credentials.items():
            if name in masked_credentials and value == masked_credentials[name]:
                credentials[name] = original_credentials[name]

        credentials = tool_configuration.encrypt_tool_credentials(credentials)
        provider.credentials_str = json.dumps(credentials)

        db.session.add(provider)
        db.session.commit()

        # 删除缓存
        tool_configuration.delete_tool_credentials_cache()

        return { 'result': 'success' }
    
    @staticmethod
    def delete_builtin_tool_provider(
        user_id: str, tenant_id: str, provider_name: str
    ):
        """
        删除内置工具提供商

        参数:
        user_id (str): 用户ID，用于标识请求的用户。
        tenant_id (str): 租户ID，用于限定操作的范围。
        provider_name (str): 提供商名称，指定要删除的工具提供商。

        返回值:
        dict: 包含操作结果信息的字典，例如 {'result': 'success'}。
        """
        # 从数据库中查询指定的工具提供商
        provider: BuiltinToolProvider = db.session.query(BuiltinToolProvider).filter(
            BuiltinToolProvider.tenant_id == tenant_id,
            BuiltinToolProvider.provider == provider_name,
        ).first()

        # 如果指定的工具提供商不存在，则抛出异常
        if provider is None:
            raise ValueError(f'you have not added provider {provider_name}')
        
        # 从数据库中删除工具提供商，并提交事务
        db.session.delete(provider)
        db.session.commit()

        # 删除工具提供商的缓存数据
        provider_controller = ToolManager.get_builtin_provider(provider_name)
        tool_configuration = ToolConfigurationManager(tenant_id=tenant_id, provider_controller=provider_controller)
        tool_configuration.delete_tool_credentials_cache()

        return { 'result': 'success' }
    
    @staticmethod
    def get_builtin_tool_provider_icon(
        provider: str
    ):
        """
        获取内置工具提供商的图标及其MIME类型。

        参数:
        provider (str): 工具提供商的名称。

        返回:
        tuple: 包含图标数据的字节串和MIME类型的元组。
        """
        # 从ToolManager获取指定提供商的图标路径和MIME类型
        icon_path, mime_type = ToolManager.get_builtin_provider_icon(provider)
        # 读取图标文件内容为字节串
        with open(icon_path, 'rb') as f:
            icon_bytes = f.read()

        return icon_bytes, mime_type
    
    @staticmethod
    def get_model_tool_provider_icon(
        provider: str
    ):
        """
        获取模型工具提供者的图标及其MIME类型
        
        参数:
        provider: str - 模型工具提供者的标识符

        返回值:
        icon_bytes: bytes - 图标的字节串
        mime_type: str - 图标的MIME类型
        """
        
        # 获取模型提供者服务实例
        service = ModelProviderService()
        # 根据提供者标识符获取小图标及其MIME类型
        icon_bytes, mime_type = service.get_model_provider_icon(provider=provider, icon_type='icon_small', lang='en_US')

        # 如果未获取到图标，抛出异常
        if icon_bytes is None:
            raise ValueError(f'provider {provider} does not exists')

        return icon_bytes, mime_type
    
    @staticmethod
    def list_model_tool_provider_tools(
        user_id: str, tenant_id: str, provider: str
    ) -> list[UserTool]:
        """
        列出指定模型工具提供者的工具列表。

        参数:
        - user_id: 用户ID，字符串类型，用于授权和访问控制。
        - tenant_id: 租户ID，字符串类型，用于确定工具所属的租户范围。
        - provider: 工具提供者名称，字符串类型，指定要查询的模型工具提供者。

        返回值:
        - 返回一个JSON解析后的对象，包含所请求的工具列表，每个工具包含作者、名称、标签、描述和参数信息。
        """
        # 获取指定租户和提供者的工具提供者控制器
        provider_controller = ToolManager.get_model_provider(tenant_id=tenant_id, provider_name=provider)
        # 从提供者控制器获取用户有权访问的工具列表
        tools = provider_controller.get_tools(user_id=user_id, tenant_id=tenant_id)

        # 将获取的工具信息转换为UserTool对象列表，准备返回
        result = [
            UserTool(
                author=tool.identity.author,
                name=tool.identity.name,
                label=tool.identity.label,
                description=tool.description.human,
                parameters=tool.parameters or []
            ) for tool in tools
        ]

        return jsonable_encoder(result)
    
    @staticmethod
    def delete_api_tool_provider(
        user_id: str, tenant_id: str, provider_name: str
    ):
        """
        删除工具提供者

        参数:
        user_id (str): 用户ID，用于标识请求的用户。
        tenant_id (str): 租户ID，用于确定操作的范围。
        provider_name (str): 提供者名称，指定要删除的工具提供者。

        返回值:
        dict: 包含操作结果信息的字典，{'result': 'success'} 表示成功。
        """
        # 从数据库中查询指定的工具提供者
        provider: ApiToolProvider = db.session.query(ApiToolProvider).filter(
            ApiToolProvider.tenant_id == tenant_id,
            ApiToolProvider.name == provider_name,
        ).first()

        # 如果提供者不存在，则抛出错误
        if provider is None:
            raise ValueError(f'you have not added provider {provider_name}')
        
        # 从数据库中删除提供者并提交更改
        db.session.delete(provider)
        db.session.commit()

        # 返回操作成功的结果
        return { 'result': 'success' }
    
    @staticmethod
    def get_api_tool_provider(
        user_id: str, tenant_id: str, provider: str
    ):
        """
        获取指定用户的API工具提供者。

        参数:
        - user_id: 用户的唯一标识符，类型为字符串。
        - tenant_id: 租户的唯一标识符，类型为字符串。用于确定用户所属的租户。
        - provider: 工具提供者的唯一标识符，类型为字符串。用于指定要获取的API工具提供者。

        返回值:
        - 返回调用ToolManager.user_get_api_provider方法的结果，该方法用于获取指定提供者的API工具信息。
        """
        return ToolManager.user_get_api_provider(provider=provider, tenant_id=tenant_id)
        
    @staticmethod
    def test_api_tool_preview(
        tenant_id: str, 
        provider_name: str,
        tool_name: str, 
        credentials: dict, 
        parameters: dict, 
        schema_type: str, 
        schema: str
    ):
        """
            在添加API工具提供者之前测试API工具。

        参数:
        - tenant_id: 字符串，租户ID。
        - provider_name: 字符串，提供者名称。
        - tool_name: 字符串，工具名称。
        - credentials: 字典，认证信息。
        - parameters: 字典，参数。
        - schema_type: 字符串，模式类型。
        - schema: 字符串，模式定义。

        返回值:
        - 字典，包含测试结果或错误信息。
        """

        # 校验模式类型是否有效
        if schema_type not in [member.value for member in ApiProviderSchemaType]:
            raise ValueError(f'invalid schema type {schema_type}')
        
        try:
            # 自动解析模式到工具包
            tool_bundles, _ = ApiBasedToolSchemaParser.auto_parse_to_tool_bundle(schema)
        except Exception as e:
            raise ValueError('invalid schema')
        
        # 获取对应操作ID的工具包
        tool_bundle = next(filter(lambda tb: tb.operation_id == tool_name, tool_bundles), None)
        if tool_bundle is None:
            raise ValueError(f'invalid tool name {tool_name}')
        
        # 从数据库查询API工具提供者
        db_provider: ApiToolProvider = db.session.query(ApiToolProvider).filter(
            ApiToolProvider.tenant_id == tenant_id,
            ApiToolProvider.name == provider_name,
        ).first()

        if not db_provider:
            # 如果提供者不存在，则创建一个虚拟的数据库提供者
            db_provider = ApiToolProvider(
                tenant_id='', user_id='', name='', icon='',
                schema=schema,
                description='',
                schema_type_str=ApiProviderSchemaType.OPENAPI.value,
                tools_str=json.dumps(jsonable_encoder(tool_bundles)),
                credentials_str=json.dumps(credentials),
            )

        if 'auth_type' not in credentials:
            # 验证认证类型是否提供
            raise ValueError('auth_type is required')

        # 获取认证类型，无或API密钥
        auth_type = ApiProviderAuthType.value_of(credentials['auth_type'])

        # 创建提供者实体
        provider_controller = ApiBasedToolProviderController.from_db(db_provider, auth_type)
        # 将工具包加载到提供者实体中
        provider_controller.load_bundled_tools(tool_bundles)

        # 如果存在数据库ID，则解密认证信息
        if db_provider.id:
            tool_configuration = ToolConfigurationManager(
                tenant_id=tenant_id, 
                provider_controller=provider_controller
            )
            decrypted_credentials = tool_configuration.decrypt_tool_credentials(credentials)
            # 检查凭证是否已更改，保存原始凭证
            masked_credentials = tool_configuration.mask_tool_credentials(decrypted_credentials)
            for name, value in credentials.items():
                if name in masked_credentials and value == masked_credentials[name]:
                    credentials[name] = decrypted_credentials[name]

        try:
            # 验证认证信息格式
            provider_controller.validate_credentials_format(credentials)
            # 获取工具
            tool = provider_controller.get_tool(tool_name)
            tool = tool.fork_tool_runtime(meta={
                'credentials': credentials,
                'tenant_id': tenant_id,
            })
            # 验证认证信息和参数
            result = tool.validate_credentials(credentials, parameters)
        except Exception as e:
            # 如果过程中发生异常，返回错误信息
            return { 'error': str(e) }
        
        # 返回测试结果或空响应
        return { 'result': result or 'empty response' }
    
    @staticmethod
    def list_builtin_tools(
        user_id: str, tenant_id: str
    ) -> list[UserToolProvider]:
        """
            list builtin tools
        """
        # get all builtin providers
        provider_controllers = ToolManager.list_builtin_providers()

        # get all user added providers
        db_providers: list[BuiltinToolProvider] = db.session.query(BuiltinToolProvider).filter(
            BuiltinToolProvider.tenant_id == tenant_id
        ).all() or []

        # find provider
        find_provider = lambda provider: next(filter(lambda db_provider: db_provider.provider == provider, db_providers), None)

        result: list[UserToolProvider] = []

        for provider_controller in provider_controllers:
            # convert provider controller to user provider
            user_builtin_provider = ToolTransformService.builtin_provider_to_user_provider(
                provider_controller=provider_controller,
                db_provider=find_provider(provider_controller.identity.name),
                decrypt_credentials=True
            )

            # add icon
            ToolTransformService.repack_provider(user_builtin_provider)

            tools = provider_controller.get_tools()
            for tool in tools:
                user_builtin_provider.tools.append(ToolTransformService.tool_to_user_tool(
                    tenant_id=tenant_id,
                    tool=tool, 
                    credentials=user_builtin_provider.original_credentials, 
                ))

            result.append(user_builtin_provider)

        return BuiltinToolProviderSort.sort(result)
    
    @staticmethod
    def list_api_tools(
        user_id: str, tenant_id: str
    ) -> list[UserToolProvider]:
        """
            list api tools
        """
        # get all api providers
        db_providers: list[ApiToolProvider] = db.session.query(ApiToolProvider).filter(
            ApiToolProvider.tenant_id == tenant_id
        ).all() or []

        result: list[UserToolProvider] = []

        for provider in db_providers:
            # convert provider controller to user provider
            provider_controller = ToolTransformService.api_provider_to_controller(db_provider=provider)
            user_provider = ToolTransformService.api_provider_to_user_provider(
                provider_controller,
                db_provider=provider,
                decrypt_credentials=True
            )

            # add icon
            ToolTransformService.repack_provider(user_provider)

            tools = provider_controller.get_tools(
                user_id=user_id, tenant_id=tenant_id
            )

            for tool in tools:
                user_provider.tools.append(ToolTransformService.tool_to_user_tool(
                    tenant_id=tenant_id,
                    tool=tool, 
                    credentials=user_provider.original_credentials, 
                ))

            result.append(user_provider)

        return result
