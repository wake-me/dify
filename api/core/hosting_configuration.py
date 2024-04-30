from typing import Optional

from flask import Config, Flask
from pydantic import BaseModel

from core.entities.provider_entities import QuotaUnit, RestrictModel
from core.model_runtime.entities.model_entities import ModelType
from models.provider import ProviderQuotaType


"""
HostingQuota 和其子类定义了不同类型的宿主配额信息。
BaseModel 是一个基类，提供模型的基本结构。
ProviderQuotaType 是一个枚举类型，定义了配额的类型，例如免费、试用、付费。
RestrictModel 是一个约束模型的类，用于定义配额的限制条件。
QuotaUnit 可能是一个定义配额单位的类，例如“件”、“小时”等。
HostingProvider 定义了一个宿主提供商的信息，包括是否启用、凭证信息、配额单位和配额列表。
HostedModerationConfig 定义了托管审核的配置，包括是否启用和使用的提供商列表。
"""

class HostingQuota(BaseModel):
    """
    宿主配额的基类，包含配额类型和模型限制列表。
    """
    quota_type: ProviderQuotaType
    restrict_models: list[RestrictModel] = []

class TrialHostingQuota(HostingQuota):
    """
    试用宿主配额类，定义了试用配额的限制和类型。
    
    Attributes:
        quota_limit: 配额限制。-1 表示无限。
    """
    quota_type: ProviderQuotaType = ProviderQuotaType.TRIAL
    quota_limit: int = 0

class PaidHostingQuota(HostingQuota):
    """
    付费宿主配额类，定义了付费配额的类型。
    """
    quota_type: ProviderQuotaType = ProviderQuotaType.PAID

class FreeHostingQuota(HostingQuota):
    """
    免费宿主配额类，定义了免费配额的类型。
    """
    quota_type: ProviderQuotaType = ProviderQuotaType.FREE

class HostingProvider(BaseModel):
    """
    宿主提供商类，定义了提供商的启用状态、凭证、配额单位和配额列表。
    
    Attributes:
        enabled: 是否启用该提供商。
        credentials: 提供商的凭证信息，可能为空。
        quota_unit: 配额的单位，可能为空。
        quotas: 该提供商的配额列表。
    """
    enabled: bool = False
    credentials: Optional[dict] = None
    quota_unit: Optional[QuotaUnit] = None
    quotas: list[HostingQuota] = []

class HostedModerationConfig(BaseModel):
    """
    托管审核配置类，定义了是否启用托管审核以及使用的提供商列表。
    
    Attributes:
        enabled: 是否启用托管审核。
        providers: 使用的提供商列表。
    """
    enabled: bool = False
    providers: list[str] = []


class HostingConfiguration:
    # 类 HostingConfiguration 用于配置和初始化各种托管提供商及其配额和审核设置。

    provider_map: dict[str, HostingProvider] = {}
    # provider_map 存储已初始化的托管提供商，键为提供商名称，值为对应的 HostingProvider 实例。

    moderation_config: HostedModerationConfig = None
    # moderation_config 用于存储审核配置信息。

    def init_app(self, app: Flask) -> None:
        """
        初始化应用程序，根据配置加载和初始化托管提供商。

        :param app: Flask 应用实例，用于获取配置信息。
        """

        config = app.config

        # 检查是否为云版本，如果不是则不进行后续初始化。
        if config.get('EDITION') != 'CLOUD':
            return

        # 初始化并注册不同的托管提供商。
        self.provider_map["azure_openai"] = self.init_azure_openai(config)
        self.provider_map["openai"] = self.init_openai(config)
        self.provider_map["anthropic"] = self.init_anthropic(config)
        self.provider_map["minimax"] = self.init_minimax(config)
        self.provider_map["spark"] = self.init_spark(config)
        self.provider_map["zhipuai"] = self.init_zhipuai(config)

        # 初始化审核配置。
        self.moderation_config = self.init_moderation_config(config)

    def init_azure_openai(self, app_config: Config) -> HostingProvider:
        """
        初始化并配置 Azure OpenAI 托管提供商。

        :param app_config: 应用配置，用于获取 Azure OpenAI 的配置信息。
        :return: 配置好的 HostingProvider 实例。
        """

        # 默认配额单位为次数。
        quota_unit = QuotaUnit.TIMES

        # 检查是否启用了 Azure OpenAI 托管服务。
        if app_config.get("HOSTED_AZURE_OPENAI_ENABLED"):
            # 配置信息。
            credentials = {
                "openai_api_key": app_config.get("HOSTED_AZURE_OPENAI_API_KEY"),
                "openai_api_base": app_config.get("HOSTED_AZURE_OPENAI_API_BASE"),
                "base_model_name": "gpt-35-turbo"
            }

            # 初始化配额。
            quotas = []
            hosted_quota_limit = int(app_config.get("HOSTED_AZURE_OPENAI_QUOTA_LIMIT", "1000"))
            trial_quota = TrialHostingQuota(
                quota_limit=hosted_quota_limit,
                restrict_models=[
                    # 限制可用模型列表。
                    RestrictModel(model="gpt-4", base_model_name="gpt-4", model_type=ModelType.LLM),
                    RestrictModel(model="gpt-4-32k", base_model_name="gpt-4-32k", model_type=ModelType.LLM),
                    RestrictModel(model="gpt-4-1106-preview", base_model_name="gpt-4-1106-preview", model_type=ModelType.LLM),
                    RestrictModel(model="gpt-4-vision-preview", base_model_name="gpt-4-vision-preview", model_type=ModelType.LLM),
                    RestrictModel(model="gpt-35-turbo", base_model_name="gpt-35-turbo", model_type=ModelType.LLM),
                    RestrictModel(model="gpt-35-turbo-1106", base_model_name="gpt-35-turbo-1106", model_type=ModelType.LLM),
                    RestrictModel(model="gpt-35-turbo-instruct", base_model_name="gpt-35-turbo-instruct", model_type=ModelType.LLM),
                    RestrictModel(model="gpt-35-turbo-16k", base_model_name="gpt-35-turbo-16k", model_type=ModelType.LLM),
                    RestrictModel(model="text-davinci-003", base_model_name="text-davinci-003", model_type=ModelType.LLM),
                    RestrictModel(model="text-embedding-ada-002", base_model_name="text-embedding-ada-002", model_type=ModelType.TEXT_EMBEDDING),
                    RestrictModel(model="text-embedding-3-small", base_model_name="text-embedding-3-small", model_type=ModelType.TEXT_EMBEDDING),
                    RestrictModel(model="text-embedding-3-large", base_model_name="text-embedding-3-large", model_type=ModelType.TEXT_EMBEDDING),
                ]
            )
            quotas.append(trial_quota)

            # 返回配置好的 Azure OpenAI HostingProvider 实例。
            return HostingProvider(
                enabled=True,
                credentials=credentials,
                quota_unit=quota_unit,
                quotas=quotas
            )

        # 如果未启用 Azure OpenAI 托管服务，则返回一个未启用状态的 HostingProvider 实例。
        return HostingProvider(
            enabled=False,
            quota_unit=quota_unit,
        )

    def init_openai(self, app_config: Config) -> HostingProvider:
        """
        初始化与OpenAI的连接配置。

        根据应用配置决定是否启用OpenAI的试用和付费配额，并配置相应的限制和凭证。

        参数:
        app_config: Config - 包含应用配置信息的对象。

        返回值:
        HostingProvider - 描述OpenAI托管设置的对象，包括是否启用、凭证信息、配额单位和配额详情。
        """
        quota_unit = QuotaUnit.CREDITS  # 配额单位为信用点
        quotas = []  # 初始化配额列表

        # 配置试用配额，如果试用功能被启用
        if app_config.get("HOSTED_OPENAI_TRIAL_ENABLED"):
            hosted_quota_limit = int(app_config.get("HOSTED_OPENAI_QUOTA_LIMIT", "200"))  # 试用配额限制，默认200
            trial_models = self.parse_restrict_models_from_env(app_config, "HOSTED_OPENAI_TRIAL_MODELS")  # 解析试用模型限制
            trial_quota = TrialHostingQuota(
                quota_limit=hosted_quota_limit,
                restrict_models=trial_models
            )
            quotas.append(trial_quota)  # 添加试用配额到列表

        # 配置付费配额，如果付费功能被启用
        if app_config.get("HOSTED_OPENAI_PAID_ENABLED"):
            paid_models = self.parse_restrict_models_from_env(app_config, "HOSTED_OPENAI_PAID_MODELS")  # 解析付费模型限制
            paid_quota = PaidHostingQuota(
                restrict_models=paid_models
            )
            quotas.append(paid_quota)  # 添加付费配额到列表

        # 如果存在配额设置，则生成并返回HostingProvider对象
        if len(quotas) > 0:
            credentials = {  # 配置凭证信息
                "openai_api_key": app_config.get("HOSTED_OPENAI_API_KEY"),
            }

            # 可选的API基础地址和组织配置
            if app_config.get("HOSTED_OPENAI_API_BASE"):
                credentials["openai_api_base"] = app_config.get("HOSTED_OPENAI_API_BASE")

            if app_config.get("HOSTED_OPENAI_API_ORGANIZATION"):
                credentials["openai_organization"] = app_config.get("HOSTED_OPENAI_API_ORGANIZATION")

            return HostingProvider(
                enabled=True,
                credentials=credentials,
                quota_unit=quota_unit,
                quotas=quotas
            )

        # 如果没有启用任何配额，返回一个禁用状态的HostingProvider对象
        return HostingProvider(
            enabled=False,
            quota_unit=quota_unit,
        )

    def init_anthropic(self, app_config: Config) -> HostingProvider:
        """
        初始化Anthropic托管设置。

        根据应用程序配置决定是否启用Anthropic的试用和付费配额，并配置相应的API凭证和配额限制。

        参数:
        - app_config: Config 类型，包含应用程序的配置信息。

        返回值:
        - HostingProvider 实例，配置了Anthropic的托管设置，包括是否启用、凭证信息、配额单位和具体的配额限制。
        """

        # 初始化配额单位和空的配额列表
        quota_unit = QuotaUnit.TOKENS
        quotas = []

        # 如果启用了Anthropic的试用版，就添加试用配额
        if app_config.get("HOSTED_ANTHROPIC_TRIAL_ENABLED"):
            hosted_quota_limit = int(app_config.get("HOSTED_ANTHROPIC_QUOTA_LIMIT", "0"))
            trial_quota = TrialHostingQuota(
                quota_limit=hosted_quota_limit
            )
            quotas.append(trial_quota)

        # 如果启用了Anthropic的付费版，就添加付费配额
        if app_config.get("HOSTED_ANTHROPIC_PAID_ENABLED"):
            paid_quota = PaidHostingQuota()
            quotas.append(paid_quota)

        # 如果存在配额设置，则准备并返回HostingProvider实例
        if len(quotas) > 0:
            credentials = {
                "anthropic_api_key": app_config.get("HOSTED_ANTHROPIC_API_KEY"),
            }

            # 如果配置了API的基础URL，则添加到凭证中
            if app_config.get("HOSTED_ANTHROPIC_API_BASE"):
                credentials["anthropic_api_url"] = app_config.get("HOSTED_ANTHROPIC_API_BASE")

            return HostingProvider(
                enabled=True,
                credentials=credentials,
                quota_unit=quota_unit,
                quotas=quotas
            )

        # 如果没有配额设置，则返回一个禁用的HostingProvider实例
        return HostingProvider(
            enabled=False,
            quota_unit=quota_unit,
        )

    def init_minimax(self, app_config: Config) -> HostingProvider:
        """
        初始化最小最大服务。

        参数:
        app_config (Config): 应用配置对象，用于获取配置信息。

        返回值:
        HostingProvider: 返回一个 HostingProvider 实例，配置了最小最大服务的状况。
        """
        quota_unit = QuotaUnit.TOKENS  # 定义配额单位为TOKENS

        # 检查是否启用了托管的最小最大服务
        if app_config.get("HOSTED_MINIMAX_ENABLED"):
            # 如果启用，则创建并返回一个配置了免费配额的 HostingProvider 实例
            quotas = [FreeHostingQuota()]

            return HostingProvider(
                enabled=True,
                credentials=None,  # 使用服务提供的凭证
                quota_unit=quota_unit,
                quotas=quotas
            )

        # 如果未启用，则返回一个配置为禁用状态的 HostingProvider 实例
        return HostingProvider(
            enabled=False,
            quota_unit=quota_unit,
        )

    def init_spark(self, app_config: Config) -> HostingProvider:
        """
        初始化Spark服务。
        
        根据应用配置决定是否启用托管的Spark服务。如果启用了托管服务，则会创建一个包含免费配额的HostingProvider实例；
        如果未启用，则返回一个禁用状态的HostingProvider实例。

        参数:
        app_config: Config - 包含应用配置信息的对象，用于检查是否启用了托管Spark服务。

        返回值:
        HostingProvider - 根据是否启用托管服务，返回相应状态的HostingProvider实例。
        """
        quota_unit = QuotaUnit.TOKENS  # 定义配额单位为TOKENS

        if app_config.get("HOSTED_SPARK_ENABLED"):
            # 如果启用了托管Spark服务，创建并返回一个启用状态的HostingProvider实例，包含免费配额
            quotas = [FreeHostingQuota()]

            return HostingProvider(
                enabled=True,
                credentials=None,  # 使用服务提供的凭证
                quota_unit=quota_unit,
                quotas=quotas
            )

        # 如果未启用托管Spark服务，返回一个禁用状态的HostingProvider实例
        return HostingProvider(
            enabled=False,
            quota_unit=quota_unit,
        )

    def init_zhipuai(self, app_config: Config) -> HostingProvider:
        """
        初始化智谱服务。

        根据应用配置决定是否启用智谱服务，并配置相应的配额。

        参数:
        - app_config: Config 类型，应用的配置信息。

        返回值:
        - HostingProvider 类型，包含智谱服务的配置信息，如是否启用、配额单位和具体配额。
        """
        quota_unit = QuotaUnit.TOKENS  # 配额单位为TOKENS

        # 检查是否启用了托管的智谱服务
        if app_config.get("HOSTED_ZHIPUAI_ENABLED"):
            quotas = [FreeHostingQuota()]  # 使用免费托管配额

            # 返回启用状态，并配置配额信息
            return HostingProvider(
                enabled=True,
                credentials=None,  # 使用服务提供的凭证
                quota_unit=quota_unit,
                quotas=quotas
            )

        # 如果未启用托管的智谱服务，则返回禁用状态，不配置具体配额
        return HostingProvider(
            enabled=False,
            quota_unit=quota_unit,
        )

    def init_moderation_config(self, app_config: Config) -> HostedModerationConfig:
        """
        初始化托管审核配置。
        
        根据应用配置决定是否启用托管审核，并配置相应的提供者。
        
        参数:
        app_config: Config - 应用的配置对象，包含是否启用托管审核以及审核提供者的信息。
        
        返回值:
        HostedModerationConfig - 托管审核的配置对象，包含是否启用以及提供者列表。
        """
        # 检查是否启用了托管审核并且提供了审核提供者列表
        if app_config.get("HOSTED_MODERATION_ENABLED") \
                and app_config.get("HOSTED_MODERATION_PROVIDERS"):
            # 如果启用，返回配置为启用状态和提供的审核提供者列表
            return HostedModerationConfig(
                enabled=True,
                providers=app_config.get("HOSTED_MODERATION_PROVIDERS").split(',')
            )

        # 如果未启用托管审核，返回配置为禁用状态
        return HostedModerationConfig(
            enabled=False
        )

    @staticmethod
    def parse_restrict_models_from_env(app_config: Config, env_var: str) -> list[RestrictModel]:
        """
        从环境变量中解析受限模型列表。
        
        参数:
        app_config: Config - 应用配置对象，用于获取环境变量的值。
        env_var: str - 指定的环境变量名，其值为模型名称的逗号分隔列表。
        
        返回值:
        list[RestrictModel] - 一个包含解析出的受限模型的列表，每个模型都是RestrictModel类型，模型类型被硬编码为LLM。
        """
        # 从应用配置中获取环境变量的值
        models_str = app_config.get(env_var)
        # 如果值存在，则按逗号分割；否则，返回空列表
        models_list = models_str.split(",") if models_str else []
        # 过滤并转换模型名称列表，排除空字符串，并创建RestrictModel实例列表
        return [RestrictModel(model=model_name.strip(), model_type=ModelType.LLM) for model_name in models_list if
                model_name.strip()]

