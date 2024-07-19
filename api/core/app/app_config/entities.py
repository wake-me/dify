from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel

from core.model_runtime.entities.message_entities import PromptMessageRole
from models.model import AppMode


class ModelConfigEntity(BaseModel):
    """
    模型配置实体类。
    
    该类用于定义一个模型配置的结构，包括模型的提供者、具体的模型名称、运行模式、参数和停止条件。
    
    参数:
    - provider: 模型的提供者，类型为字符串。
    - model: 模型的名称，类型为字符串。
    - mode: 模型的运行模式，可选参数，默认为None。如果指定，应该是一个字符串。
    - parameters: 用于模型的参数，是一个字典类型，键值对为参数名和参数值。
    - stop: 模型停止条件的列表，列表中的字符串表示不同的停止条件。
    """
    provider: str
    model: str
    mode: Optional[str] = None
    parameters: dict[str, Any] = {}
    stop: list[str] = []

    # 该类继承自BaseModel，用于构建和验证模型配置的数据结构。

class AdvancedChatMessageEntity(BaseModel):
    """
    高级聊天消息实体类。
    
    该类代表一个聊天消息实体，包含消息文本和消息角色。
    
    属性:
        text (str): 消息文本。
        role (PromptMessageRole): 消息角色，定义了消息的特定类型或用途。
    """
    text: str
    role: PromptMessageRole

class AdvancedChatPromptTemplateEntity(BaseModel):
    """
    高级聊天提示模板实体类。
    
    该类代表了一个高级聊天提示模板，它包含了一组消息实体（AdvancedChatMessageEntity）。
    """

    messages: list[AdvancedChatMessageEntity]  # 存储高级聊天消息实体的列表

class AdvancedCompletionPromptTemplateEntity(BaseModel):
    """
    高级完成提示模板实体类。
    
    该类代表了一个高级完成提示模板，包含了一个提示字符串和角色前缀信息（可选）。
    """

    class RolePrefixEntity(BaseModel):
        """
        角色前缀实体类。
        
        该内部类定义了用户和助手的角色前缀。
        """
        user: str  # 用户角色的前缀
        assistant: str  # 助手角色的前缀

    prompt: str  # 提示字符串
    role_prefix: Optional[RolePrefixEntity] = None  # 角色前缀信息，可选


class PromptTemplateEntity(BaseModel):
    """
    Prompt模板实体类，用于定义不同类型的提示模板。
    """

    class PromptType(Enum):
        """
        提示类型枚举，定义了简单的和高级的两种提示类型。
        """
        SIMPLE = 'simple'  # 简单提示类型
        ADVANCED = 'advanced'  # 高级提示类型

        @classmethod
        def value_of(cls, value: str) -> 'PromptType':
            """
            根据字符串值获取对应的提示类型枚举实例。

            :param value: 提示类型的字符串值。
            :return: 对应的PromptType枚举实例。
            """
            for mode in cls:
                if mode.value == value:
                    return mode
            # 如果传入的值无效，则抛出异常
            raise ValueError(f'invalid prompt type value {value}')

    prompt_type: PromptType  # 提示类型的枚举实例
    simple_prompt_template: Optional[str] = None  # 简单提示模板，可为空
    advanced_chat_prompt_template: Optional[AdvancedChatPromptTemplateEntity] = None  # 高级聊天提示模板，可为空
    advanced_completion_prompt_template: Optional[AdvancedCompletionPromptTemplateEntity] = None  # 高级完成提示模板，可为空

class VariableEntity(BaseModel):
    """
    变量实体类，用于定义一种变量的结构，包括变量的基本信息和约束条件。
    """
    class Type(Enum):
        """
        变量类型枚举，定义了变量可能的输入类型。
        """
        TEXT_INPUT = 'text-input'  # 文本输入
        SELECT = 'select'  # 下拉选择
        PARAGRAPH = 'paragraph'  # 段落输入
        NUMBER = 'number'  # 数字输入

        @classmethod
        def value_of(cls, value: str) -> 'VariableEntity.Type':
            """
            根据字符串值获取对应的变量类型枚举实例。

            :param value: 字符串类型的变量值。
            :return: 对应的变量类型枚举实例。
            """
            for mode in cls:
                if mode.value == value:
                    return mode
            raise ValueError(f'invalid variable type value {value}')  # 若找不到匹配的类型，则抛出异常

    variable: str
    label: str
    description: Optional[str] = None
    type: Type
    required: bool = False
    max_length: Optional[int] = None
    options: Optional[list[str]] = None
    default: Optional[str] = None
    hint: Optional[str] = None

    @property
    def name(self) -> str:
        return self.variable


class ExternalDataVariableEntity(BaseModel):
    """
    外部数据变量实体类。
    
    该类用于定义一个外部数据变量的实体，它包含以下属性：
    - variable: 变量名称，类型为str。
    - type: 变量类型，类型为str。
    - config: 变量的配置信息，是一个字典类型，键值对为str到Any类型的映射，默认为空字典。
    """
    variable: str
    type: str
    config: dict[str, Any] = {}


class DatasetRetrieveConfigEntity(BaseModel):
    """
    数据集检索配置实体类。
    """

    class RetrieveStrategy(Enum):
        """
        数据集检索策略枚举类。
        支持'single'或'multiple'两种策略。
        """
        SINGLE = 'single'  # 单个检索策略
        MULTIPLE = 'multiple'  # 多个检索策略

        @classmethod
        def value_of(cls, value: str) -> 'RetrieveStrategy':
            """
            根据给定值获取检索策略枚举实例。

            :param value: 检索策略的字符串表示
            :return: 对应的检索策略枚举实例
            """
            for mode in cls:
                if mode.value == value:
                    return mode
            raise ValueError(f'invalid retrieve strategy value {value}')

    query_variable: Optional[str] = None  # 仅当应用模式为补全时有效

    retrieve_strategy: RetrieveStrategy  # 检索策略
    top_k: Optional[int] = None  # 返回结果的最大数量
    score_threshold: Optional[float] = None  # 分数阈值，用于过滤结果
    reranking_model: Optional[dict] = None  # 用于重新排序的模型配置


class DatasetEntity(BaseModel):
    """
    数据集配置实体类。
    
    参数:
    - dataset_ids: 数据集ID列表，类型为list[str]。
    - retrieve_config: 数据集检索配置实体，类型为DatasetRetrieveConfigEntity。
    """
    dataset_ids: list[str]
    retrieve_config: DatasetRetrieveConfigEntity


class SensitiveWordAvoidanceEntity(BaseModel):
    """
    敏感词规避实体类。
    该类用于定义敏感词规避的相关配置实体。
    
    属性:
    - type: 字符串，表示敏感词规避的类型。
    - config: 字典，存储敏感词规避的详细配置信息，键值对形式。
    """

    type: str
    config: dict[str, Any] = {}


class TextToSpeechEntity(BaseModel):
    """
    文本转语音实体类。
    该类用于定义文本转语音的配置实体。
    
    属性:
    - enabled: 布尔值，表示文本转语音功能是否启用。
    - voice: 可选的字符串，指定语音的类型（如声音的性别或口音）。
    - language: 可选的字符串，指定语音的语种。
    """

    enabled: bool
    voice: Optional[str] = None
    language: Optional[str] = None


class TracingConfigEntity(BaseModel):
    """
    Tracing Config Entity.
    """
    enabled: bool
    tracing_provider: str


class FileExtraConfig(BaseModel):
    """
    文件上传额外配置实体类。
    该类用于定义文件上传时的额外配置信息。
    
    属性:
    - image_config: 可选的字典，存储关于图片上传的额外配置信息，键值对形式。
    """

    image_config: Optional[dict[str, Any]] = None

class AppAdditionalFeatures(BaseModel):
    """
    应用额外功能模型，用于定义应用程序中可选的功能配置。

    属性:
        file_upload (Optional[FileExtraConfig]): 文件上传配置，可为FileExtraConfig类型或None。
        opening_statement (Optional[str]): 开场白，应用程序启动时可显示的一段文字，可为字符串或None。
        suggested_questions (list[str]): 建议的问题列表，应用程序可以向用户提出的建议问题。
        suggested_questions_after_answer (bool): 是否在用户回答后显示建议的问题，默认为False。
        show_retrieve_source (bool): 是否显示获取来源的选项，默认为False。
        more_like_this (bool): 是否启用“更多类似内容”功能，默认为False。
        speech_to_text (bool): 是否启用语音转文本功能，默认为False。
        text_to_speech (Optional[TextToSpeechEntity]): 文本转语音配置，可为TextToSpeechEntity类型或None。
    """
    file_upload: Optional[FileExtraConfig] = None
    opening_statement: Optional[str] = None
    suggested_questions: list[str] = []
    suggested_questions_after_answer: bool = False
    show_retrieve_source: bool = False
    more_like_this: bool = False
    speech_to_text: bool = False
    text_to_speech: Optional[TextToSpeechEntity] = None
    trace_config: Optional[TracingConfigEntity] = None

class AppConfig(BaseModel):
    """
    Application Config Entity.
    """
    tenant_id: str
    app_id: str
    app_mode: AppMode
    additional_features: AppAdditionalFeatures
    variables: list[VariableEntity] = []
    sensitive_word_avoidance: Optional[SensitiveWordAvoidanceEntity] = None


class EasyUIBasedAppModelConfigFrom(Enum):
    """
    应用模型配置来源枚举类。

    该枚举定义了应用模型配置的不同来源，用于指示配置信息的获取途径。

    属性:
    - ARGS: 命令行参数作为配置来源。
    - APP_LATEST_CONFIG: 应用的最新配置，通常从一个预定义的位置或服务中获取。
    - CONVERSATION_SPECIFIC_CONFIG: 会话特定的配置，针对特定的会话上下文进行配置。
    """
    ARGS = 'args'  # 命令行参数
    APP_LATEST_CONFIG = 'app-latest-config'  # 应用的最新配置
    CONVERSATION_SPECIFIC_CONFIG = 'conversation-specific-config'  # 会话特定的配置

class EasyUIBasedAppConfig(AppConfig):
    """
    基于EasyUI的应用配置实体类。
    
    属性:
    - app_model_config_from: 应用模型配置来源实体。
    - app_model_config_id: 应用模型配置的唯一标识符。
    - app_model_config_dict: 应用模型配置的字典形式。
    - model: 模型配置实体。
    - prompt_template: 提示模板实体。
    - dataset: 可选，数据集实体，默认为None。
    - external_data_variables: 外部数据变量实体列表。
    """
    app_model_config_from: EasyUIBasedAppModelConfigFrom
    app_model_config_id: str
    app_model_config_dict: dict
    model: ModelConfigEntity
    prompt_template: PromptTemplateEntity
    dataset: Optional[DatasetEntity] = None
    external_data_variables: list[ExternalDataVariableEntity] = []

class WorkflowUIBasedAppConfig(AppConfig):
    """
    基于Workflow UI的应用配置实体类。
    
    属性:
        workflow_id: 字符串类型，表示工作流的唯一标识符。
    """
    workflow_id: str