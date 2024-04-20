from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel

from core.app.app_config.entities import AppConfig, EasyUIBasedAppConfig, WorkflowUIBasedAppConfig
from core.entities.provider_configuration import ProviderModelBundle
from core.file.file_obj import FileVar
from core.model_runtime.entities.model_entities import AIModelEntity


class InvokeFrom(Enum):
    """
    定义调用来源的枚举类。

    枚举成员包括：
    - SERVICE_API：服务API调用
    - WEB_APP：Web应用调用
    - EXPLORE：探索调用
    - DEBUGGER：调试器调用
    """

    SERVICE_API = 'service-api'
    WEB_APP = 'web-app'
    EXPLORE = 'explore'
    DEBUGGER = 'debugger'

    @classmethod
    def value_of(cls, value: str) -> 'InvokeFrom':
        """
        根据字符串值获取对应的调用来源枚举成员。

        :param value: 调用来源的字符串表示
        :return: 对应的调用来源枚举成员
        :raises ValueError: 如果传入的值无效，则抛出异常
        """
        for mode in cls:
            if mode.value == value:
                return mode
        raise ValueError(f'invalid invoke from value {value}')

    def to_source(self) -> str:
        """
        将调用来源转换为相应的源字符串。

        :return: 调用来源对应的源字符串
        """
        # 根据不同的调用来源，返回相应的源字符串
        if self == InvokeFrom.WEB_APP:
            return 'web_app'
        elif self == InvokeFrom.DEBUGGER:
            return 'dev'
        elif self == InvokeFrom.EXPLORE:
            return 'explore_app'
        elif self == InvokeFrom.SERVICE_API:
            return 'api'

        return 'dev'


class ModelConfigWithCredentialsEntity(BaseModel):
    """
    模型配置及凭证实体类。
    
    该类用于封装模型的配置信息以及访问模型所需的凭证信息。
    
    属性:
    - provider: 模型提供者名称。
    - model: 模型的标识或名称。
    - model_schema: AIModelEntity类型，模型的架构信息。
    - mode: 模型的运行模式。
    - provider_model_bundle: ProviderModelBundle类型，包含模型提供商提供的模型包信息。
    - credentials: 字典类型，存储访问模型所需的凭证信息。
    - parameters: 字典类型，用于存储模型的参数配置。
    - stop: 字典类型，包含停止操作的关键词列表。
    """
    provider: str
    model: str
    model_schema: AIModelEntity
    mode: str
    provider_model_bundle: ProviderModelBundle
    credentials: dict[str, Any] = {}
    parameters: dict[str, Any] = {}
    stop: list[str] = []

class AppGenerateEntity(BaseModel):
    """
    App Generate Entity 类。

    用于定义应用程序生成实体的属性和配置。

    属性:
        task_id (str): 任务ID，唯一标识一个任务。
        app_config (AppConfig): 应用配置，包含应用相关的配置信息。
        inputs (dict[str, str]): 输入参数，键值对形式存储。
        files (list[FileVar]): 文件列表，用于存储文件变量信息。
        user_id (str): 用户ID，标识请求的用户。
        stream (bool): 是否为流式任务。
        invoke_from (InvokeFrom): 调用来源，标识任务的调用方。
        extras (dict[str, Any]): 额外参数，用于存储额外的配置或信息。
    """
    task_id: str

    # app config
    app_config: AppConfig

    inputs: dict[str, str]
    files: list[FileVar] = []
    user_id: str

    # extras
    stream: bool
    invoke_from: InvokeFrom

    # extra parameters, like: auto_generate_conversation_name
    extras: dict[str, Any] = {}


class EasyUIBasedAppGenerateEntity(AppGenerateEntity):
    """
    基于EasyUI的应用生成实体类。
    """
    # 应用配置
    app_config: EasyUIBasedAppConfig
    model_config: ModelConfigWithCredentialsEntity  # 模型配置，包含认证信息

    query: Optional[str] = None  # 查询字符串，可能为空


class ChatAppGenerateEntity(EasyUIBasedAppGenerateEntity):
    """
    聊天应用生成实体类。
    """
    conversation_id: Optional[str] = None  # 对话ID，可能为空


class CompletionAppGenerateEntity(EasyUIBasedAppGenerateEntity):
    """
    完成应用生成实体类。
    """
    pass  # 该类可能用于后续扩展


class AgentChatAppGenerateEntity(EasyUIBasedAppGenerateEntity):
    """
    代理聊天应用生成实体类。
    """
    conversation_id: Optional[str] = None  # 对话ID，可能为空


class AdvancedChatAppGenerateEntity(AppGenerateEntity):
    """
    高级聊天应用生成实体类。
    """
    # 应用配置
    app_config: WorkflowUIBasedAppConfig

    conversation_id: Optional[str] = None  # 对话ID，可能为空
    query: Optional[str] = None  # 查询字符串，可能为空


class WorkflowAppGenerateEntity(AppGenerateEntity):
    """
    工作流应用生成实体类。
    """
    # 应用配置
    app_config: WorkflowUIBasedAppConfig