import uuid
from typing import Optional

from core.agent.entities import AgentEntity
from core.app.app_config.base_app_config_manager import BaseAppConfigManager
from core.app.app_config.common.sensitive_word_avoidance.manager import SensitiveWordAvoidanceConfigManager
from core.app.app_config.easy_ui_based_app.agent.manager import AgentConfigManager
from core.app.app_config.easy_ui_based_app.dataset.manager import DatasetConfigManager
from core.app.app_config.easy_ui_based_app.model_config.manager import ModelConfigManager
from core.app.app_config.easy_ui_based_app.prompt_template.manager import PromptTemplateConfigManager
from core.app.app_config.easy_ui_based_app.variables.manager import BasicVariablesConfigManager
from core.app.app_config.entities import EasyUIBasedAppConfig, EasyUIBasedAppModelConfigFrom
from core.app.app_config.features.file_upload.manager import FileUploadConfigManager
from core.app.app_config.features.opening_statement.manager import OpeningStatementConfigManager
from core.app.app_config.features.retrieval_resource.manager import RetrievalResourceConfigManager
from core.app.app_config.features.speech_to_text.manager import SpeechToTextConfigManager
from core.app.app_config.features.suggested_questions_after_answer.manager import (
    SuggestedQuestionsAfterAnswerConfigManager,
)
from core.app.app_config.features.text_to_speech.manager import TextToSpeechConfigManager
from core.entities.agent_entities import PlanningStrategy
from models.model import App, AppMode, AppModelConfig, Conversation
# 定义一个旧工具列表
OLD_TOOLS = ["dataset", "google_search", "web_reader", "wikipedia", "current_datetime"]

class AgentChatAppConfig(EasyUIBasedAppConfig):
    """
    Agent Chatbot App配置实体类。
    
    该类用于定义Agent Chatbot应用程序的配置实体。
    属性:
        agent (Optional[AgentEntity]): 一个可选的AgentEntity对象，表示与之关联的代理实体。
    """
    agent: Optional[AgentEntity] = None


class AgentChatAppConfigManager(BaseAppConfigManager):
    @classmethod
    def get_app_config(cls, app_model: App,
                        app_model_config: AppModelConfig,
                        conversation: Optional[Conversation] = None,
                        override_config_dict: Optional[dict] = None) -> AgentChatAppConfig:
            """
            将应用模型配置转换为代理聊天应用配置。
            :param app_model: 应用模型，包含应用的基本信息如模式、租户ID和应用ID。
            :param app_model_config: 应用模型配置，具体应用的配置细节。
            :param conversation: 对话信息，可选，如果提供，则配置可能会根据对话上下文进行调整。
            :param override_config_dict: 覆盖配置字典，可选，提供时将使用此字典覆盖应用模型配置。
            :return: 返回一个AgentChatAppConfig对象，包含应用的配置信息，如模型配置、提示模板等。
            """
            # 确定配置来源
            if override_config_dict:
                config_from = EasyUIBasedAppModelConfigFrom.ARGS
            elif conversation:
                config_from = EasyUIBasedAppModelConfigFrom.CONVERSATION_SPECIFIC_CONFIG
            else:
                config_from = EasyUIBasedAppModelConfigFrom.APP_LATEST_CONFIG

            # 根据配置来源决定使用哪个配置字典
            if config_from != EasyUIBasedAppModelConfigFrom.ARGS:
                app_model_config_dict = app_model_config.to_dict()
                config_dict = app_model_config_dict.copy()
            else:
                config_dict = override_config_dict

            # 获取应用模式并根据配置创建AgentChatAppConfig实例
            app_mode = AppMode.value_of(app_model.mode)
            app_config = AgentChatAppConfig(
                tenant_id=app_model.tenant_id,
                app_id=app_model.id,
                app_mode=app_mode,
                app_model_config_from=config_from,
                app_model_config_id=app_model_config.id,
                app_model_config_dict=config_dict,
                model=ModelConfigManager.convert(
                    config=config_dict
                ),
                prompt_template=PromptTemplateConfigManager.convert(
                    config=config_dict
                ),
                sensitive_word_avoidance=SensitiveWordAvoidanceConfigManager.convert(
                    config=config_dict
                ),
                dataset=DatasetConfigManager.convert(
                    config=config_dict
                ),
                agent=AgentConfigManager.convert(
                    config=config_dict
                ),
                additional_features=cls.convert_features(config_dict, app_mode)
            )

            # 转换并设置变量及外部数据变量配置
            app_config.variables, app_config.external_data_variables = BasicVariablesConfigManager.convert(
                config=config_dict
            )

            return app_config

    @classmethod
    def config_validate(cls, tenant_id: str, config: dict) -> dict:
        """
        验证代理聊天应用模型配置的合法性

        :param tenant_id: 租户id
        :param config: 应用模型配置参数
        :return: 验证后符合条件的配置参数字典
        """
        # 初始化应用模式为代理聊天模式
        app_mode = AppMode.AGENT_CHAT

        related_config_keys = []

        # 验证并设置模型配置的默认值
        config, current_related_config_keys = ModelConfigManager.validate_and_set_defaults(tenant_id, config)
        related_config_keys.extend(current_related_config_keys)

        # 验证并设置用户输入表单配置的默认值
        config, current_related_config_keys = BasicVariablesConfigManager.validate_and_set_defaults(tenant_id, config)
        related_config_keys.extend(current_related_config_keys)

        # 验证并设置文件上传配置的默认值
        config, current_related_config_keys = FileUploadConfigManager.validate_and_set_defaults(config)
        related_config_keys.extend(current_related_config_keys)

        # 验证并设置提示模板配置的默认值
        config, current_related_config_keys = PromptTemplateConfigManager.validate_and_set_defaults(app_mode, config)
        related_config_keys.extend(current_related_config_keys)

        # 验证并设置代理模式配置的默认值
        config, current_related_config_keys = cls.validate_agent_mode_and_set_defaults(tenant_id, config)
        related_config_keys.extend(current_related_config_keys)

        # 验证并设置开场白配置的默认值
        config, current_related_config_keys = OpeningStatementConfigManager.validate_and_set_defaults(config)
        related_config_keys.extend(current_related_config_keys)

        # 验证并设置回答后建议问题配置的默认值
        config, current_related_config_keys = SuggestedQuestionsAfterAnswerConfigManager.validate_and_set_defaults(
            config)
        related_config_keys.extend(current_related_config_keys)

        # 验证并设置语音转文本配置的默认值
        config, current_related_config_keys = SpeechToTextConfigManager.validate_and_set_defaults(config)
        related_config_keys.extend(current_related_config_keys)

        # 验证并设置文本转语音配置的默认值
        config, current_related_config_keys = TextToSpeechConfigManager.validate_and_set_defaults(config)
        related_config_keys.extend(current_related_config_keys)

        # 验证并设置检索资源配置的默认值
        config, current_related_config_keys = RetrievalResourceConfigManager.validate_and_set_defaults(config)
        related_config_keys.extend(current_related_config_keys)

        # 验证并设置数据集配置的默认值
        config, current_related_config_keys = DatasetConfigManager.validate_and_set_defaults(tenant_id, app_mode,
                                                                                            config)
        related_config_keys.extend(current_related_config_keys)

        # 验证并设置审核配置的默认值
        config, current_related_config_keys = SensitiveWordAvoidanceConfigManager.validate_and_set_defaults(tenant_id,
                                                                                                           config)
        related_config_keys.extend(current_related_config_keys)

        # 去除重复的配置键
        related_config_keys = list(set(related_config_keys))

        # 过滤出相关的配置参数
        filtered_config = {key: config.get(key) for key in related_config_keys}

        return filtered_config

    @classmethod
    def validate_agent_mode_and_set_defaults(cls, tenant_id: str, config: dict) -> tuple[dict, list[str]]:
        """
        验证 agent_mode 并为代理功能设置默认值

        :param tenant_id: 租户ID
        :param config: 应用模型配置参数
        :return: 一个元组，包含校验并可能修改后的config字典和一个字符串列表，列出所有修改过的字段名
        """

        # 如果agent_mode未设置，则初始化为禁用状态
        if not config.get("agent_mode"):
            config["agent_mode"] = {
                "enabled": False,
                "tools": []
            }

        # 确保agent_mode是字典类型
        if not isinstance(config["agent_mode"], dict):
            raise ValueError("agent_mode must be of object type")

        # 设置agent_mode为禁用状态，如果未明确启用
        if "enabled" not in config["agent_mode"] or not config["agent_mode"]["enabled"]:
            config["agent_mode"]["enabled"] = False

        # 确保enabled值为布尔类型
        if not isinstance(config["agent_mode"]["enabled"], bool):
            raise ValueError("enabled in agent_mode must be of boolean type")

        # 如果未设置策略，默认使用ROUTER
        if not config["agent_mode"].get("strategy"):
            config["agent_mode"]["strategy"] = PlanningStrategy.ROUTER.value

        # 确保策略值在可接受的范围内
        if config["agent_mode"]["strategy"] not in [member.value for member in
                                                    list(PlanningStrategy.__members__.values())]:
            raise ValueError("strategy in agent_mode must be in the specified strategy list")

        # 如果未设置工具列表，默认为空列表
        if not config["agent_mode"].get("tools"):
            config["agent_mode"]["tools"] = []

        # 确保工具列表是对象列表类型
        if not isinstance(config["agent_mode"]["tools"], list):
            raise ValueError("tools in agent_mode must be a list of objects")

        # 遍历工具列表，进行逐个校验和设置默认值
        for tool in config["agent_mode"]["tools"]:
            key = list(tool.keys())[0]
            if key in OLD_TOOLS:
                # 处理旧版工具配置
                tool_item = tool[key]

                # 设置默认禁用状态
                if "enabled" not in tool_item or not tool_item["enabled"]:
                    tool_item["enabled"] = False

                # 确保启用状态值为布尔类型
                if not isinstance(tool_item["enabled"], bool):
                    raise ValueError("enabled in agent_mode.tools must be of boolean type")

                # 对于数据集工具，额外的校验
                if key == "dataset":
                    if 'id' not in tool_item:
                        raise ValueError("id is required in dataset")

                    # 确保数据集ID为UUID格式
                    try:
                        uuid.UUID(tool_item["id"])
                    except ValueError:
                        raise ValueError("id in dataset must be of UUID type")

                    # 检查数据集是否存在
                    if not DatasetConfigManager.is_dataset_exists(tenant_id, tool_item["id"]):
                        raise ValueError("Dataset ID does not exist, please check your permission.")
            else:
                # 处理新版工具配置
                # 设置默认禁用状态和检查必需字段
                if "enabled" not in tool or not tool["enabled"]:
                    tool["enabled"] = False
                if "provider_type" not in tool:
                    raise ValueError("provider_type is required in agent_mode.tools")
                if "provider_id" not in tool:
                    raise ValueError("provider_id is required in agent_mode.tools")
                if "tool_name" not in tool:
                    raise ValueError("tool_name is required in agent_mode.tools")
                if "tool_parameters" not in tool:
                    raise ValueError("tool_parameters is required in agent_mode.tools")

        return config, ["agent_mode"]
