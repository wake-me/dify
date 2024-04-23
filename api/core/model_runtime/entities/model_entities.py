from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel

from core.model_runtime.entities.common_entities import I18nObject


class ModelType(Enum):
    """
    模型类型的枚举类。
    """

    LLM = "llm"  # 代表大语言模型
    TEXT_EMBEDDING = "text-embedding"  # 代表文本嵌入模型
    RERANK = "rerank"  # 代表重排序模型
    SPEECH2TEXT = "speech2text"  # 代表语音转文本模型
    MODERATION = "moderation"  # 代表内容审核模型
    TTS = "tts"  # 代表文本转语音模型
    TEXT2IMG = "text2img"  # 代表文本生成图像模型

    @classmethod
    def value_of(cls, origin_model_type: str) -> "ModelType":
        """
        根据原始模型类型获取枚举模型类型。

        :param origin_model_type: 原始模型类型的字符串表示。
        :return: 对应的模型类型枚举实例。
        """
        # 根据传入的原始模型类型字符串，返回相应的枚举实例
        if origin_model_type == 'text-generation' or origin_model_type == cls.LLM.value:
            return cls.LLM
        elif origin_model_type == 'embeddings' or origin_model_type == cls.TEXT_EMBEDDING.value:
            return cls.TEXT_EMBEDDING
        elif origin_model_type == 'reranking' or origin_model_type == cls.RERANK.value:
            return cls.RERANK
        elif origin_model_type == 'speech2text' or origin_model_type == cls.SPEECH2TEXT.value:
            return cls.SPEECH2TEXT
        elif origin_model_type == 'tts' or origin_model_type == cls.TTS.value:
            return cls.TTS
        elif origin_model_type == 'text2img' or origin_model_type == cls.TEXT2IMG.value:
            return cls.TEXT2IMG
        elif origin_model_type == cls.MODERATION.value:
            return cls.MODERATION
        else:
            raise ValueError(f'invalid origin model type {origin_model_type}')

    def to_origin_model_type(self) -> str:
        """
        将枚举模型类型转换为原始模型类型字符串。

        :return: 对应的原始模型类型字符串。
        """
        # 根据枚举实例返回相应的原始模型类型字符串
        if self == self.LLM:
            return 'text-generation'
        elif self == self.TEXT_EMBEDDING:
            return 'embeddings'
        elif self == self.RERANK:
            return 'reranking'
        elif self == self.SPEECH2TEXT:
            return 'speech2text'
        elif self == self.TTS:
            return 'tts'
        elif self == self.MODERATION:
            return 'moderation'
        elif self == self.TEXT2IMG:
            return 'text2img'
        else:
            raise ValueError(f'invalid model type {self}')

class FetchFrom(Enum):
    """
    定义获取来源的枚举类。
    """

    PREDEFINED_MODEL = "predefined-model"  # 预定义模型
    CUSTOMIZABLE_MODEL = "customizable-model"  # 可定制模型


class ModelFeature(Enum):
    """
    定义模型功能的枚举类。
    """

    TOOL_CALL = "tool-call"  # 工具调用
    MULTI_TOOL_CALL = "multi-tool-call"  # 多工具调用
    AGENT_THOUGHT = "agent-thought"  # 代理思考
    VISION = "vision"  # 视觉
    STREAM_TOOL_CALL = "stream-tool-call"  # 流式工具调用


class DefaultParameterName(Enum):
    """
    定义参数模板变量的枚举类。
    """

    TEMPERATURE = "temperature"  # 温度
    TOP_P = "top_p"  # Top P
    PRESENCE_PENALTY = "presence_penalty"  # 存在惩罚
    FREQUENCY_PENALTY = "frequency_penalty"  # 频率惩罚
    MAX_TOKENS = "max_tokens"  # 最大令牌数
    RESPONSE_FORMAT = "response_format"  # 响应格式

    @classmethod
    def value_of(cls, value: Any) -> 'DefaultParameterName':
        """
        根据值获取参数名。

        :param value: 参数值
        :return: 参数名
        """
        for name in cls:
            if name.value == value:
                return name
        raise ValueError(f'无效的参数名 {value}')

class ParameterType(Enum):
    """
    参数类型的枚举类。
    """
    FLOAT = "float"  # 浮点型
    INT = "int"  # 整型
    STRING = "string"  # 字符串型
    BOOLEAN = "boolean"  # 布尔型


class ModelPropertyKey(Enum):
    """
    模型属性键的枚举类。
    """
    MODE = "mode"  # 模式
    CONTEXT_SIZE = "context_size"  # 上下文大小
    MAX_CHUNKS = "max_chunks"  # 最大块数
    FILE_UPLOAD_LIMIT = "file_upload_limit"  # 文件上传限制
    SUPPORTED_FILE_EXTENSIONS = "supported_file_extensions"  # 支持的文件扩展名
    MAX_CHARACTERS_PER_CHUNK = "max_characters_per_chunk"  # 每块最大字符数
    DEFAULT_VOICE = "default_voice"  # 默认声音
    VOICES = "voices"  # 可用声音列表
    WORD_LIMIT = "word_limit"  # 字数限制
    AUDIO_TYPE = "audio_type"  # 音频类型
    MAX_WORKERS = "max_workers"  # 最大工作线程数


class ProviderModel(BaseModel):
    """
    供应商模型的模型类。
    """
    model: str  # 模型标识符
    label: I18nObject  # 模型的国际化标签
    model_type: ModelType  # 模型类型
    features: Optional[list[ModelFeature]] = None  # 模型特性列表
    fetch_from: FetchFrom  # 数据获取方式
    model_properties: dict[ModelPropertyKey, Any]  # 模型的附加属性，键为ModelPropertyKey枚举成员
    deprecated: bool = False  # 模型是否已弃用

    class Config:
        protected_namespaces = ()  # 保护的命名空间列表，用于配置验证时忽略特定字段

class ParameterRule(BaseModel):
    """
    参数规则模型类。
    属性:
        name (str): 参数名称。
        use_template (Optional[str]): 是否使用模板，默认为None。
        label (I18nObject): 参数标签，支持多语言。
        type (ParameterType): 参数类型。
        help (Optional[I18nObject]): 参数帮助信息，默认为None。
        required (bool): 参数是否必填，默认为False。
        default (Optional[Any]): 参数默认值，默认为None。
        min (Optional[float]): 参数最小值，默认为None。
        max (Optional[float]): 参数最大值，默认为None。
        precision (Optional[int]): 参数精度，默认为None。
        options (list[str]): 参数可选值列表，默认为空列表。
    """
    name: str
    use_template: Optional[str] = None
    label: I18nObject
    type: ParameterType
    help: Optional[I18nObject] = None
    required: bool = False
    default: Optional[Any] = None
    min: Optional[float] = None
    max: Optional[float] = None
    precision: Optional[int] = None
    options: list[str] = []


class PriceConfig(BaseModel):
    """
    价格配置模型类。
    属性:
        input (Decimal): 输入值。
        output (Optional[Decimal]): 输出值，默认为None。
        unit (Decimal): 单位价格。
        currency (str): 货币单位。
    """
    input: Decimal
    output: Optional[Decimal] = None
    unit: Decimal
    currency: str


class AIModelEntity(ProviderModel):
    """
    人工智能模型实体模型类。
    属性:
        parameter_rules (list[ParameterRule]): 参数规则列表。
        pricing (Optional[PriceConfig]): 价格配置信息，默认为None。
    """
    parameter_rules: list[ParameterRule] = []
    pricing: Optional[PriceConfig] = None


class ModelUsage(BaseModel):
    pass


class PriceType(Enum):
    """
    价格类型枚举类。
    值:
        INPUT: 输入类型。
        OUTPUT: 输出类型。
    """
    INPUT = "input"
    OUTPUT = "output"


class PriceInfo(BaseModel):
    """
    价格信息模型类。
    属性:
        unit_price (Decimal): 单位价格。
        unit (Decimal): 单位。
        total_amount (Decimal): 总金额。
        currency (str): 货币单位。
    """
    unit_price: Decimal
    unit: Decimal
    total_amount: Decimal
    currency: str
