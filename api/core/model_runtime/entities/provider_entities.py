from enum import Enum
from typing import Optional

from pydantic import BaseModel

from core.model_runtime.entities.common_entities import I18nObject
from core.model_runtime.entities.model_entities import AIModelEntity, ModelType, ProviderModel


class ConfigurateMethod(Enum):
    """
    配置方法的枚举类，用于指定提供者模型的配置方式。
    """

    PREDEFINED_MODEL = "predefined-model"  # 预定义模型配置方式
    CUSTOMIZABLE_MODEL = "customizable-model"  # 可定制模型配置方式


class FormType(Enum):
    """
    表单类型的枚举类。
    """

    TEXT_INPUT = "text-input"  # 文本输入框
    SECRET_INPUT = "secret-input"  # 密码输入框
    SELECT = "select"  # 下拉选择框
    RADIO = "radio"  # 单选按钮
    SWITCH = "switch"  # 开关控件


class FormShowOnObject(BaseModel):
    """
    表单展示条件的模型类，用于指定表单在何种情况下展示。
    """
    variable: str  # 变量名
    value: str  # 对应的值


class FormOption(BaseModel):
    """
    表单选项的模型类，用于定义表单的可选项及其相关属性。
    """
    label: I18nObject  # 选项标签，支持多语言
    value: str  # 选项的值
    show_on: list[FormShowOnObject] = []  # 该选项展示的条件列表

    def __init__(self, **data):
        """
        初始化表单选项实例。
        
        :param **data: 关键字参数，用于初始化表单选项的属性值。
        """
        super().__init__(**data)
        # 如果未指定标签，则默认使用选项的值作为英文标签
        if not self.label:
            self.label = I18nObject(
                en_US=self.value
            )

class CredentialFormSchema(BaseModel):
    """
    凭证表单模式的模型类。
    属性:
        variable (str): 表单变量名称。
        label (I18nObject): 表单标签，支持多语言。
        type (FormType): 表单类型。
        required (bool): 是否必填，默认为 True。
        default (Optional[str]): 默认值，默认为 None。
        options (Optional[list[FormOption]]): 可选项列表，默认为 None。
        placeholder (Optional[I18nObject]): 占位符，默认为 None。
        max_length (int): 最大长度，默认为 0。
        show_on (list[FormShowOnObject]): 条件显示规则列表，默认为空列表。
    """

    variable: str
    label: I18nObject
    type: FormType
    required: bool = True
    default: Optional[str] = None
    options: Optional[list[FormOption]] = None
    placeholder: Optional[I18nObject] = None
    max_length: int = 0
    show_on: list[FormShowOnObject] = []

class ProviderCredentialSchema(BaseModel):
    """
    提供者凭证模式的模型类。
    属性:
        credential_form_schemas (list[CredentialFormSchema]): 凭证表单模式列表。
    """
    credential_form_schemas: list[CredentialFormSchema]

class FieldModelSchema(BaseModel):
    """
    字段模型模式的模型类。
    属性:
        label (I18nObject): 标签，支持多语言。
        placeholder (Optional[I18nObject]): 占位符，默认为 None。
    """
    label: I18nObject
    placeholder: Optional[I18nObject] = None

class ModelCredentialSchema(BaseModel):
    """
    模型凭证模式的模型类。
    属性:
        model (FieldModelSchema): 字段模型。
        credential_form_schemas (list[CredentialFormSchema]): 凭证表单模式列表。
    """
    model: FieldModelSchema
    credential_form_schemas: list[CredentialFormSchema]

class SimpleProviderEntity(BaseModel):
    """
    供应商的简单模型类。
    
    参数:
    - provider: 供应商名称，类型为str。
    - label: 供应商标签，国际化对象，用于显示供应商的名称或描述。
    - icon_small: 小图标，可选的国际化对象。默认为None，表示没有小图标。
    - icon_large: 大图标，可选的国际化对象。默认为None，表示没有大图标。
    - supported_model_types: 支持的模型类型列表，类型为ModelType的list。
    - models: 该供应商提供的模型实体列表，类型为AIModelEntity的list。默认为空列表。
    """
    provider: str
    label: I18nObject
    icon_small: Optional[I18nObject] = None
    icon_large: Optional[I18nObject] = None
    supported_model_types: list[ModelType]
    models: list[AIModelEntity] = []

class ProviderHelpEntity(BaseModel):
    """
    供应商帮助信息的模型类。
    
    参数:
    - title: 帮助信息的标题，国际化对象。
    - url: 帮助信息的链接，国际化对象。
    """
    title: I18nObject
    url: I18nObject


class ProviderEntity(BaseModel):
    """
    供应商实体模型类。
    用于定义供应商的基本信息和功能。
    """

    provider: str  # 供应商名称
    label: I18nObject  # 供应商标签，支持多语言
    description: Optional[I18nObject] = None  # 供应商描述，支持多语言，可选
    icon_small: Optional[I18nObject] = None  # 小图标，支持多语言，可选
    icon_large: Optional[I18nObject] = None  # 大图标，支持多语言，可选
    background: Optional[str] = None  # 背景颜色或图片链接，可选
    help: Optional[ProviderHelpEntity] = None  # 帮助信息，可选
    supported_model_types: list[ModelType]  # 支持的模型类型列表
    configurate_methods: list[ConfigurateMethod]  # 配置方法列表
    models: list[ProviderModel] = []  # 供应商提供的模型列表
    provider_credential_schema: Optional[ProviderCredentialSchema] = None  # 供应商凭证模式，可选
    model_credential_schema: Optional[ModelCredentialSchema] = None  # 模型凭证模式，可选

    class Config:
        protected_namespaces = ()  # 保护的命名空间，防止外部修改

    def to_simple_provider(self) -> SimpleProviderEntity:
        """
        转换为简单的供应商实体。

        :return: 简化的供应商实体对象，只包含基本和必要的信息。
        """
        return SimpleProviderEntity(
            provider=self.provider,
            label=self.label,
            icon_small=self.icon_small,
            icon_large=self.icon_large,
            supported_model_types=self.supported_model_types,
            models=self.models
        )

class ProviderConfig(BaseModel):
    """
    供应商配置模型类。
    用于定义供应商的配置信息，如认证信息等。
    """

    provider: str  # 供应商名称
    credentials: dict  # 认证凭证，以键值对形式存储