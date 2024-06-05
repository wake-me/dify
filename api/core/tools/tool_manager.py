import json
import logging
import mimetypes
from collections.abc import Generator
from os import listdir, path
from threading import Lock
from typing import Any, Union

from flask import current_app

from core.agent.entities import AgentToolEntity
from core.app.entities.app_invoke_entities import InvokeFrom
from core.helper.module_import_helper import load_single_subclass_from_source
from core.model_runtime.utils.encoders import jsonable_encoder
from core.tools.entities.api_entities import UserToolProvider, UserToolProviderTypeLiteral
from core.tools.entities.common_entities import I18nObject
from core.tools.entities.tool_entities import (
    ApiProviderAuthType,
    ToolInvokeFrom,
    ToolParameter,
)
from core.tools.errors import ToolProviderNotFoundError
from core.tools.provider.api_tool_provider import ApiToolProviderController
from core.tools.provider.builtin._positions import BuiltinToolProviderSort
from core.tools.provider.builtin_tool_provider import BuiltinToolProviderController
from core.tools.tool.api_tool import ApiTool
from core.tools.tool.builtin_tool import BuiltinTool
from core.tools.tool.tool import Tool
from core.tools.tool_label_manager import ToolLabelManager
from core.tools.utils.configuration import (
    ToolConfigurationManager,
    ToolParameterConfigurationManager,
)
from core.tools.utils.tool_parameter_converter import ToolParameterConverter
from core.workflow.nodes.tool.entities import ToolEntity
from extensions.ext_database import db
from models.tools import ApiToolProvider, BuiltinToolProvider, WorkflowToolProvider
from services.tools.tools_transform_service import ToolTransformService

logger = logging.getLogger(__name__)

class ToolManager:
    # 用于同步访问共享资源的类级别锁
    _builtin_provider_lock = Lock()
    # 存储已加载内置工具提供者的字典
    _builtin_providers = {}
    # 标记内置提供程序是否已加载的标志
    _builtin_providers_loaded = False
    # 用于快速访问内置工具标签的字典
    _builtin_tools_labels = {}

    @classmethod
    def get_builtin_provider(cls, provider: str) -> BuiltinToolProviderController:
        """
        获取指定的内置工具提供者。

        :param provider: 要获取的内置工具提供者的名称。
        :return: 请求的 BuiltinToolProviderController 实例。
        """
        # 如果内置提供程序尚未加载，则进行初始化
        if len(cls._builtin_providers) == 0:
            cls.load_builtin_providers_cache()

        # 如果请求的提供程序未找到，则抛出异常
        if provider not in cls._builtin_providers:
            raise ToolProviderNotFoundError(f'未找到内置提供程序 {provider}')

        # 返回请求的提供程序
        return cls._builtin_providers[provider]

    @classmethod
    def get_builtin_tool(cls, provider: str, tool_name: str) -> BuiltinTool:
        """
        获取内置工具

        :param provider: 提供者的名称
        :param tool_name: 工具的名称

        :return: 返回指定的提供者和工具
        """
        # 获取指定名称的内置提供者控制器
        provider_controller = cls.get_builtin_provider(provider)
        # 通过提供者控制器获取指定名称的工具
        tool = provider_controller.get_tool(tool_name)

        return tool

    @classmethod
    def get_tool(cls, provider_type: str, provider_id: str, tool_name: str, tenant_id: str = None) \
            -> Union[BuiltinTool, ApiTool]:
        """
            根据提供的提供商类型、提供商ID、工具名称获取相应的工具实例。

            :param provider_type: 提供商的类型，例如 'builtin', 'api' 或 'app'。
            :param provider_id: 提供商的唯一标识符。
            :param tool_name: 需要获取的工具的名称。
            :param tenant_id: 租户的唯一标识符，仅在 provider_type 为 'api' 时必需。
            
            :return: 返回一个工具实例，可能是内置工具（BuiltinTool）或API工具（ApiTool）。
            :raises ValueError: 当 provider_type 为 'api' 且未提供 tenant_id 时抛出。
            :raises NotImplementedError: 当 provider_type 为 'app' 时，表示该功能尚未实现。
            :raises ToolProviderNotFoundError: 当未找到指定类型的提供商时抛出。
        """
        # 根据提供商类型选择不同的逻辑分支
        if provider_type == 'builtin':
            # 对于内置提供商，直接通过提供商ID和工具名称获取工具
            return cls.get_builtin_tool(provider_id, tool_name)
        elif provider_type == 'api':
            # 对于API提供商，首先需要获取API提供者控制器，然后通过控制器获取工具
            if tenant_id is None:
                raise ValueError('tenant id is required for api provider')
            api_provider, _ = cls.get_api_provider_controller(tenant_id, provider_id)
            return api_provider.get_tool(tool_name)
        elif provider_type == 'app':
            # 如果是APP提供商，目前尚未实现，抛出异常
            raise NotImplementedError('app provider not implemented')
        else:
            # 如果无法识别提供商类型，抛出未找到提供商的异常
            raise ToolProviderNotFoundError(f'provider type {provider_type} not found')

    @classmethod
    def get_tool_runtime(cls, provider_type: str,
                         provider_id: str,
                         tool_name: str,
                         tenant_id: str,
                         invoke_from: InvokeFrom = InvokeFrom.DEBUGGER,
                         tool_invoke_from: ToolInvokeFrom = ToolInvokeFrom.AGENT) \
        -> Union[BuiltinTool, ApiTool]:
        """
            获取工具运行时

            :param provider_type: 提供者的类型
            :param provider_name: 提供者的名字
            :param tool_name: 工具的名字
            :param tenant_id: 租户的ID

            :return: 返回工具实例，具体类型取决于提供者类型

            根据提供的提供者类型、提供者名称、工具名称以及租户ID来获取相应的工具运行时实例。
            支持的提供者类型包括内置（builtin）、API、模型（model）和应用（app），其中应用提供者类型暂未实现。
            对于不同的提供者类型，需要进行不同的处理逻辑来获取工具运行时实例，这个过程可能涉及到凭证的解密和工具配置的处理。
        """
        if provider_type == 'builtin':
            builtin_tool = cls.get_builtin_tool(provider_id, tool_name)

            # check if the builtin tool need credentials
            provider_controller = cls.get_builtin_provider(provider_id)
            if not provider_controller.need_credentials:
                return builtin_tool.fork_tool_runtime(runtime={
                    'tenant_id': tenant_id,
                    'credentials': {},
                    'invoke_from': invoke_from,
                    'tool_invoke_from': tool_invoke_from,
                })

            # 处理需要凭证的情况，从数据库获取并解密凭证
            builtin_provider: BuiltinToolProvider = db.session.query(BuiltinToolProvider).filter(
                BuiltinToolProvider.tenant_id == tenant_id,
                BuiltinToolProvider.provider == provider_id,
            ).first()

            if builtin_provider is None:
                raise ToolProviderNotFoundError(f'builtin provider {provider_id} not found')

            credentials = builtin_provider.credentials
            controller = cls.get_builtin_provider(provider_id)
            tool_configuration = ToolConfigurationManager(tenant_id=tenant_id, provider_controller=controller)

            decrypted_credentials = tool_configuration.decrypt_tool_credentials(credentials)

            return builtin_tool.fork_tool_runtime(runtime={
                'tenant_id': tenant_id,
                'credentials': decrypted_credentials,
                'runtime_parameters': {},
                'invoke_from': invoke_from,
                'tool_invoke_from': tool_invoke_from,
            })
        
        elif provider_type == 'api':
            # 处理API提供者的情况，获取并解密凭证
            if tenant_id is None:
                raise ValueError('tenant id is required for api provider')

            api_provider, credentials = cls.get_api_provider_controller(tenant_id, provider_id)

            tool_configuration = ToolConfigurationManager(tenant_id=tenant_id, provider_controller=api_provider)
            decrypted_credentials = tool_configuration.decrypt_tool_credentials(credentials)

            return api_provider.get_tool(tool_name).fork_tool_runtime(runtime={
                'tenant_id': tenant_id,
                'credentials': decrypted_credentials,
                'invoke_from': invoke_from,
                'tool_invoke_from': tool_invoke_from,
            })
        elif provider_type == 'workflow':
            workflow_provider = db.session.query(WorkflowToolProvider).filter(
                WorkflowToolProvider.tenant_id == tenant_id,
                WorkflowToolProvider.id == provider_id
            ).first()

            if workflow_provider is None:
                raise ToolProviderNotFoundError(f'workflow provider {provider_id} not found')

            controller = ToolTransformService.workflow_provider_to_controller(
                db_provider=workflow_provider
            )

            return controller.get_tools(user_id=None, tenant_id=workflow_provider.tenant_id)[0].fork_tool_runtime(runtime={
                'tenant_id': tenant_id,
                'credentials': {},
                'invoke_from': invoke_from,
                'tool_invoke_from': tool_invoke_from,
            })
        elif provider_type == 'app':
            # app提供者暂未实现
            raise NotImplementedError('app provider not implemented')
        else:
            # 提供者类型不存在
            raise ToolProviderNotFoundError(f'provider type {provider_type} not found')

    @classmethod
    def _init_runtime_parameter(cls, parameter_rule: ToolParameter, parameters: dict) -> Union[str, int, float, bool]:
        """
        初始化运行时参数。

        根据提供的参数规则和参数字典，初始化并返回运行时参数的值。此函数会验证参数的存在性、类型和取值范围，
        并将参数值转换为预期的类型（整数、浮点数、布尔值或字符串）。

        参数:
        - parameter_rule: ToolParameter, 表示参数规则的对象，包含参数名、类型、默认值和选项等信息。
        - parameters: dict, 包含运行时参数的字典，键为参数名，值为参数值。

        返回值:
        - 返回初始化后的参数值，类型为字符串、整数、浮点数或布尔值。

        抛出异常:
        - 如果必需的参数未在参数字典中找到，则抛出 ValueError。
        - 如果参数值不在允许的选项范围内，则抛出 ValueError。
        - 如果参数值的类型不正确，则抛出 ValueError。
        """

        # 尝试从参数字典中获取参数值，如果未找到，则使用默认值
        parameter_value = parameters.get(parameter_rule.name)
        if not parameter_value:
            parameter_value = parameter_rule.default
            if not parameter_value and parameter_rule.required:
                raise ValueError(f"tool parameter {parameter_rule.name} not found in tool config")

        # 对于选择类型参数，检查参数值是否在选项列表中
        if parameter_rule.type == ToolParameter.ToolParameterType.SELECT:
            options = list(map(lambda x: x.value, parameter_rule.options))
            if parameter_value not in options:
                raise ValueError(
                    f"tool parameter {parameter_rule.name} value {parameter_value} not in options {options}")

        return ToolParameterConverter.cast_parameter_by_type(parameter_value, parameter_rule.type)

    @classmethod
    def get_agent_tool_runtime(cls, tenant_id: str, app_id: str, agent_tool: AgentToolEntity, invoke_from: InvokeFrom = InvokeFrom.DEBUGGER) -> Tool:
        """
        获取代理工具的运行时信息。

        参数:
        - cls: 类的引用
        - tenant_id: 租户ID，字符串类型，用于标识租户
        - app_id: 应用ID，字符串类型，标识调用此功能的应用
        - agent_tool: AgentToolEntity实体，包含代理工具的详细信息

        返回值:
        - Tool: 返回一个工具实体，包含运行时配置信息
        """
        # 获取工具的运行时实体
        tool_entity = cls.get_tool_runtime(
            provider_type=agent_tool.provider_type,
            provider_id=agent_tool.provider_id,
            tool_name=agent_tool.tool_name,
            tenant_id=tenant_id,
            invoke_from=invoke_from,
            tool_invoke_from=ToolInvokeFrom.AGENT
        )
        runtime_parameters = {}
        
        # 遍历并收集所有运行时参数
        parameters = tool_entity.get_all_runtime_parameters()
        for parameter in parameters:
            # check file types
            if parameter.type == ToolParameter.ToolParameterType.FILE:
                raise ValueError(f"file type parameter {parameter.name} not supported in agent")

            if parameter.form == ToolParameter.ToolParameterForm.FORM:
                # 初始化并保存运行时参数到内存
                value = cls._init_runtime_parameter(parameter, agent_tool.tool_parameters)
                runtime_parameters[parameter.name] = value

        # 对运行时参数进行解密
        encryption_manager = ToolParameterConfigurationManager(
            tenant_id=tenant_id,
            tool_runtime=tool_entity,
            provider_name=agent_tool.provider_id,
            provider_type=agent_tool.provider_type,
            identity_id=f'AGENT.{app_id}'
        )
        runtime_parameters = encryption_manager.decrypt_tool_parameters(runtime_parameters)

        # 更新工具实体的运行时参数
        tool_entity.runtime.runtime_parameters.update(runtime_parameters)
        return tool_entity

    @classmethod
    def get_workflow_tool_runtime(cls, tenant_id: str, app_id: str, node_id: str, workflow_tool: ToolEntity, invoke_from: InvokeFrom = InvokeFrom.DEBUGGER) -> Tool:
        """
        获取工作流工具的运行时信息。

        参数:
        - cls: 类的引用
        - tenant_id: 租户ID，字符串类型，用于标识租户
        - app_id: 应用ID，字符串类型，用于标识应用
        - node_id: 节点ID，字符串类型，用于标识工作流中的节点
        - workflow_tool: ToolEntity实体，包含工作流工具的配置信息

        返回值:
        - 返回一个ToolEntity实体，该实体包含了工作流工具的运行时参数配置
        """
        # 获取工具的运行时配置
        tool_entity = cls.get_tool_runtime(
            provider_type=workflow_tool.provider_type,
            provider_id=workflow_tool.provider_id,
            tool_name=workflow_tool.tool_name,
            tenant_id=tenant_id,
            invoke_from=invoke_from,
            tool_invoke_from=ToolInvokeFrom.WORKFLOW
        )
        runtime_parameters = {}
        parameters = tool_entity.get_all_runtime_parameters()

        # 遍历所有运行时参数，初始化并保存到runtime_parameters字典中
        for parameter in parameters:
            if parameter.form == ToolParameter.ToolParameterForm.FORM:
                value = cls._init_runtime_parameter(parameter, workflow_tool.tool_configurations)
                runtime_parameters[parameter.name] = value

        # 对运行时参数进行解密
        encryption_manager = ToolParameterConfigurationManager(
            tenant_id=tenant_id,
            tool_runtime=tool_entity,
            provider_name=workflow_tool.provider_id,
            provider_type=workflow_tool.provider_type,
            identity_id=f'WORKFLOW.{app_id}.{node_id}'
        )

        if runtime_parameters:
            runtime_parameters = encryption_manager.decrypt_tool_parameters(runtime_parameters)

        # 更新工具实体的运行时参数
        tool_entity.runtime.runtime_parameters.update(runtime_parameters)
        return tool_entity

    @classmethod
    def get_builtin_provider_icon(cls, provider: str) -> tuple[str, str]:
        """
            获取内置提供者图标的绝对路径

            :param provider: 提供者的名称
            :type provider: str

            :return: 图标的绝对路径和MIME类型
            :rtype: tuple[str, str]
        """
        # 获取提供者控制器
        provider_controller = cls.get_builtin_provider(provider)

        # 构建图标的绝对路径
        absolute_path = path.join(path.dirname(path.realpath(__file__)), 'provider', 'builtin', provider, '_assets',
                                provider_controller.identity.icon)
        # 检查图标是否存在
        if not path.exists(absolute_path):
            raise ToolProviderNotFoundError(f'builtin provider {provider} icon not found')

        # 获取图标的MIME类型
        mime_type, _ = mimetypes.guess_type(absolute_path)
        mime_type = mime_type or 'application/octet-stream'

        return absolute_path, mime_type

    @classmethod
    def list_builtin_providers(cls) -> Generator[BuiltinToolProviderController, None, None]:
        """
        列出内建工具提供者控制器的生成器方法。
        
        此方法用于生成并返回系统中所有内建工具提供者的控制器实例。首先尝试从缓存中获取，
        如果缓存已加载，则直接从缓存中返回所有提供者。如果缓存未加载，则加锁以防止并发加载，
        加载完成后，将结果返回。
        
        参数:
        - cls: 类的引用，用于访问类变量和方法。
        
        返回值:
        - Generator[BuiltinToolProviderController, None, None]: 一个生成器，逐个yield出BuiltinToolProviderController实例。
        """
        
        # 尝试从缓存中获取已加载的提供者
        if cls._builtin_providers_loaded:
            yield from list(cls._builtin_providers.values())
            return
            
        # 如果缓存未加载，则加锁以防止并发加载
        with cls._builtin_provider_lock:
            # 再次检查提供者是否已被加载
            if cls._builtin_providers_loaded:
                yield from list(cls._builtin_providers.values())
                return
                
            # 在加锁保护下，加载内建工具提供者
            yield from cls._list_builtin_providers()
    
    @classmethod
    def _list_builtin_providers(cls) -> Generator[BuiltinToolProviderController, None, None]:
        """
            列出所有内置的提供者

            :param cls: 类的引用，用于访问和更新类变量
            :return: 生成器，逐个返回加载的内置工具提供者实例
        """
        # 遍历当前模块目录下'provider/builtin'子目录中的所有条目
        for provider in listdir(path.join(path.dirname(path.realpath(__file__)), 'provider', 'builtin')):
            # 忽略以'__'开头的目录或文件
            if provider.startswith('__'):
                continue

            # 检查提供者是否为目录且不以'__'开头
            if path.isdir(path.join(path.dirname(path.realpath(__file__)), 'provider', 'builtin', provider)):
                if provider.startswith('__'):
                    continue

                # 尝试从源文件初始化提供者
                try:
                    # 动态加载提供者类
                    provider_class = load_single_subclass_from_source(
                        module_name=f'core.tools.provider.builtin.{provider}.{provider}',
                        script_path=path.join(path.dirname(path.realpath(__file__)),
                                            'provider', 'builtin', provider, f'{provider}.py'),
                        parent_type=BuiltinToolProviderController)
                    # 实例化提供者
                    provider: BuiltinToolProviderController = provider_class()
                    # 将提供者实例添加到类变量中
                    cls._builtin_providers[provider.identity.name] = provider
                    # 为每个工具注册标签
                    for tool in provider.get_tools():
                        cls._builtin_tools_labels[tool.identity.name] = tool.identity.label
                    yield provider  # 返回提供者实例

                except Exception as e:
                    # 加载提供者失败时记录错误信息
                    logger.error(f'load builtin provider {provider} error: {e}')
                    continue
        # 标记内置提供者加载完成
        cls._builtin_providers_loaded = True

    @classmethod
    def load_builtin_providers_cache(cls):
        """
        加载内置提供者缓存。
        
        该方法遍历所有内置提供者，目前没有进行任何操作，但为后续可能的扩展保留。
        
        参数:
        - cls: 类的引用，用于访问类级别的方法和属性。
        
        返回值:
        - 无
        """
        for _ in cls.list_builtin_providers():
            # 遍历所有内置提供者
            pass

    @classmethod
    def clear_builtin_providers_cache(cls):
        """
        清除内置提供者缓存的方法。

        该方法为类方法，用于重置类级别的内置提供者缓存。
        它不仅清空了内置提供者的数据字典，还标记为未加载状态，以便下一次加载。

        参数:
        - cls: 类的引用，用于访问和修改类级别的变量。

        返回值:
        - 无
        """
        cls._builtin_providers = {}  # 重置内置提供者的缓存为一个空字典
        cls._builtin_providers_loaded = False  # 标记内置提供者缓存为未加载状态

    @classmethod
    def get_tool_label(cls, tool_name: str) -> Union[I18nObject, None]:
        """
            获取工具标签

            :param tool_name: 工具的名称
            :type tool_name: str

            :return: 工具的标签，如果工具未找到则返回None
            :rtype: Union[I18nObject, None]
        """
        if len(cls._builtin_tools_labels) == 0:
            # 初始化内置工具提供者缓存
            cls.load_builtin_providers_cache()

        if tool_name not in cls._builtin_tools_labels:
            return None

        # 返回指定工具的标签
        return cls._builtin_tools_labels[tool_name]

    @classmethod
    def user_list_providers(cls, user_id: str, tenant_id: str, typ: UserToolProviderTypeLiteral) -> list[UserToolProvider]:
        result_providers: dict[str, UserToolProvider] = {}

        filters = []
        if not typ:
            filters.extend(['builtin', 'api', 'workflow'])
        else:
            filters.append(typ)

        if 'builtin' in filters:

            # get builtin providers
            builtin_providers = cls.list_builtin_providers()

            # get db builtin providers
            db_builtin_providers: list[BuiltinToolProvider] = db.session.query(BuiltinToolProvider). \
                filter(BuiltinToolProvider.tenant_id == tenant_id).all()

            find_db_builtin_provider = lambda provider: next(
                (x for x in db_builtin_providers if x.provider == provider),
                None
            )

            # append builtin providers
            for provider in builtin_providers:
                user_provider = ToolTransformService.builtin_provider_to_user_provider(
                    provider_controller=provider,
                    db_provider=find_db_builtin_provider(provider.identity.name),
                    decrypt_credentials=False
                )

                result_providers[provider.identity.name] = user_provider

        # get db api providers

        if 'api' in filters:
            db_api_providers: list[ApiToolProvider] = db.session.query(ApiToolProvider). \
                filter(ApiToolProvider.tenant_id == tenant_id).all()

            api_provider_controllers = [{
                'provider': provider,
                'controller': ToolTransformService.api_provider_to_controller(provider)
            } for provider in db_api_providers]

            # get labels
            labels = ToolLabelManager.get_tools_labels([x['controller'] for x in api_provider_controllers])

            for api_provider_controller in api_provider_controllers:
                user_provider = ToolTransformService.api_provider_to_user_provider(
                    provider_controller=api_provider_controller['controller'],
                    db_provider=api_provider_controller['provider'],
                    decrypt_credentials=False,
                    labels=labels.get(api_provider_controller['controller'].provider_id, [])
                )
                result_providers[f'api_provider.{user_provider.name}'] = user_provider

        if 'workflow' in filters:
            # get workflow providers
            workflow_providers: list[WorkflowToolProvider] = db.session.query(WorkflowToolProvider). \
                filter(WorkflowToolProvider.tenant_id == tenant_id).all()

            workflow_provider_controllers = []
            for provider in workflow_providers:
                try:
                    workflow_provider_controllers.append(
                        ToolTransformService.workflow_provider_to_controller(db_provider=provider)
                    )
                except Exception as e:
                    # app has been deleted
                    pass

            labels = ToolLabelManager.get_tools_labels(workflow_provider_controllers)

            for provider_controller in workflow_provider_controllers:
                user_provider = ToolTransformService.workflow_provider_to_user_provider(
                    provider_controller=provider_controller,
                    labels=labels.get(provider_controller.provider_id, []),
                )
                result_providers[f'workflow_provider.{user_provider.name}'] = user_provider

        # 对结果中的工具提供者进行排序后返回
        return BuiltinToolProviderSort.sort(list(result_providers.values()))

    @classmethod
    def get_api_provider_controller(cls, tenant_id: str, provider_id: str) -> tuple[
        ApiToolProviderController, dict[str, Any]]:
        """
        获取API提供者控制器

        :param tenant_id: 租户ID，字符串类型，用于查询特定租户的API工具提供者
        :param provider_id: 提供者ID，字符串类型，用于查询特定的API工具提供者
        :return: 返回一个元组，包含API基础工具提供者控制器和提供者的凭证信息字典。
        
        若指定的API工具提供者不存在，则抛出ToolProviderNotFoundError异常。
        """

        # 从数据库查询指定ID和租户ID的API工具提供者
        provider: ApiToolProvider = db.session.query(ApiToolProvider).filter(
            ApiToolProvider.id == provider_id,
            ApiToolProvider.tenant_id == tenant_id,
        ).first()

        # 如果查询结果为空，则抛出提供者未找到的异常
        if provider is None:
            raise ToolProviderNotFoundError(f'api provider {provider_id} not found')

        controller = ApiToolProviderController.from_db(
            provider,
            ApiProviderAuthType.API_KEY if provider.credentials['auth_type'] == 'api_key' else 
            ApiProviderAuthType.NONE
        )
        controller.load_bundled_tools(provider.tools)

        # 返回控制器和提供者凭证
        return controller, provider.credentials

    @classmethod
    def user_get_api_provider(cls, provider: str, tenant_id: str) -> dict:
        """
        获取指定提供者的 API 信息。

        参数:
        - provider: str, 提供者的名字。
        - tenant_id: str, 租户的ID。

        返回值:
        - dict, 包含提供者详细信息的字典，如schema_type, schema, tools等。

        抛出:
        - ValueError, 如果指定的提供者未被添加。
        """

        # 从数据库查询指定的API工具提供者
        provider: ApiToolProvider = db.session.query(ApiToolProvider).filter(
            ApiToolProvider.tenant_id == tenant_id,
            ApiToolProvider.name == provider,
        ).first()

        # 如果查询结果为空，则抛出未添加提供者异常
        if provider is None:
            raise ValueError(f'you have not added provider {provider}')

        try:
            # 尝试解析提供者的认证信息
            credentials = json.loads(provider.credentials_str) or {}
        except:
            credentials = {}

        # package tool provider controller
        controller = ApiToolProviderController.from_db(
            provider, ApiProviderAuthType.API_KEY if credentials['auth_type'] == 'api_key' else ApiProviderAuthType.NONE
        )
        tool_configuration = ToolConfigurationManager(tenant_id=tenant_id, provider_controller=controller)

        # 解密和遮蔽工具的认证信息
        decrypted_credentials = tool_configuration.decrypt_tool_credentials(credentials)
        masked_credentials = tool_configuration.mask_tool_credentials(decrypted_credentials)

        try:
            # 尝试解析提供者的图标信息
            icon = json.loads(provider.icon)
        except:
            # 如果解析失败，则设置默认图标
            icon = {
                "background": "#252525",
                "content": "\ud83d\ude01"
            }

        # add tool labels
        labels = ToolLabelManager.get_tool_labels(controller)

        return jsonable_encoder({
            'schema_type': provider.schema_type,
            'schema': provider.schema,
            'tools': provider.tools,
            'icon': icon,
            'description': provider.description,
            'credentials': masked_credentials,
            'privacy_policy': provider.privacy_policy,
            'custom_disclaimer': provider.custom_disclaimer,
            'labels': labels,
        })

    @classmethod
    def get_tool_icon(cls, tenant_id: str, provider_type: str, provider_id: str) -> Union[str, dict]:
        """
        获取工具图标。

        :param tenant_id: 租户的ID，类型为字符串。
        :param provider_type: 提供者的类型，类型为字符串，可选值为'builtin'或'api'。
        :param provider_id: 提供者的ID，类型为字符串。
        :return: 返回图标的URL字符串或包含图标背景和内容的字典。
        """
        # 根据提供者类型分别处理
        provider_type = provider_type
        provider_id = provider_id
        if provider_type == 'builtin':
            # 返回内建提供者的图标URL
            return (current_app.config.get("CONSOLE_API_URL")
                    + "/console/api/workspaces/current/tool-provider/builtin/"
                    + provider_id
                    + "/icon")
        elif provider_type == 'api':
            try:
                # 从数据库查询API工具提供者，并返回其图标数据
                provider: ApiToolProvider = db.session.query(ApiToolProvider).filter(
                    ApiToolProvider.tenant_id == tenant_id,
                    ApiToolProvider.id == provider_id
                )
                return json.loads(provider.icon)
            except:
                # 如果查询失败，则返回默认图标
                return {
                    "background": "#252525",
                    "content": "\ud83d\ude01"
                }
        elif provider_type == 'workflow':
            provider: WorkflowToolProvider = db.session.query(WorkflowToolProvider).filter(
                WorkflowToolProvider.tenant_id == tenant_id,
                WorkflowToolProvider.id == provider_id
            ).first()
            if provider is None:
                raise ToolProviderNotFoundError(f'workflow provider {provider_id} not found')

            return json.loads(provider.icon)
        else:
            # 如果提供者类型不识别，则抛出异常
            raise ValueError(f"provider type {provider_type} not found")

ToolManager.load_builtin_providers_cache()