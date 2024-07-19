from typing import Optional

from core.app.app_config.base_app_config_manager import BaseAppConfigManager
from core.app.app_config.common.sensitive_word_avoidance.manager import SensitiveWordAvoidanceConfigManager
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
from models.model import App, AppMode, AppModelConfig, Conversation


class ChatAppConfig(EasyUIBasedAppConfig):
    """
    Chatbot App Config Entity.
    """
    pass


class ChatAppConfigManager(BaseAppConfigManager):
    @classmethod
    def get_app_config(cls, app_model: App,
                        app_model_config: AppModelConfig,
                        conversation: Optional[Conversation] = None,
                        override_config_dict: Optional[dict] = None) -> ChatAppConfig:
        """
        将应用模型配置转换为聊天应用配置
        :param app_model: 应用模型
        :param app_model_config: 应用模型配置
        :param conversation: 会话，可选
        :param override_config_dict: 重写的应用模型配置字典，可选
        :return: 聊天应用配置
        """
        # 确定配置来源
        if override_config_dict:
            config_from = EasyUIBasedAppModelConfigFrom.ARGS
        elif conversation:
            config_from = EasyUIBasedAppModelConfigFrom.CONVERSATION_SPECIFIC_CONFIG
        else:
            config_from = EasyUIBasedAppModelConfigFrom.APP_LATEST_CONFIG

        # 根据配置来源处理配置字典
        if config_from != EasyUIBasedAppModelConfigFrom.ARGS:
            app_model_config_dict = app_model_config.to_dict()
            config_dict = app_model_config_dict.copy()
        else:
            if not override_config_dict:
                raise Exception('override_config_dict is required when config_from is ARGS')

            config_dict = override_config_dict

        # 加载应用模式并构建应用配置
        app_mode = AppMode.value_of(app_model.mode)
        app_config = ChatAppConfig(
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
            additional_features=cls.convert_features(config_dict, app_mode)
        )

        # 转换变量配置和外部数据变量配置
        app_config.variables, app_config.external_data_variables = BasicVariablesConfigManager.convert(
            config=config_dict
        )

        return app_config

    @classmethod
    def config_validate(cls, tenant_id: str, config: dict) -> dict:
        """
        验证聊天应用模型配置

        :param tenant_id: 租户id
        :param config: 应用模型配置参数
        :return: 验证后的配置字典，仅包含相关的配置键值对
        """
        app_mode = AppMode.CHAT  # 设定应用模式为聊天模式

        related_config_keys = []  # 初始化相关配置键列表

        # 验证并设置模型配置默认值
        config, current_related_config_keys = ModelConfigManager.validate_and_set_defaults(tenant_id, config)
        related_config_keys.extend(current_related_config_keys)

        # 验证并设置用户输入表单配置默认值
        config, current_related_config_keys = BasicVariablesConfigManager.validate_and_set_defaults(tenant_id, config)
        related_config_keys.extend(current_related_config_keys)

        # 验证并设置文件上传配置默认值
        config, current_related_config_keys = FileUploadConfigManager.validate_and_set_defaults(config)
        related_config_keys.extend(current_related_config_keys)

        # 验证并设置提示模板配置默认值
        config, current_related_config_keys = PromptTemplateConfigManager.validate_and_set_defaults(app_mode, config)
        related_config_keys.extend(current_related_config_keys)

        # 验证并设置数据集查询变量配置默认值
        config, current_related_config_keys = DatasetConfigManager.validate_and_set_defaults(tenant_id, app_mode,
                                                                                             config)
        related_config_keys.extend(current_related_config_keys)

        # 验证并设置开场白配置默认值
        config, current_related_config_keys = OpeningStatementConfigManager.validate_and_set_defaults(config)
        related_config_keys.extend(current_related_config_keys)

        # 验证并设置回答后建议问题配置默认值
        config, current_related_config_keys = SuggestedQuestionsAfterAnswerConfigManager.validate_and_set_defaults(
            config)
        related_config_keys.extend(current_related_config_keys)

        # 验证并设置语音转文本配置默认值
        config, current_related_config_keys = SpeechToTextConfigManager.validate_and_set_defaults(config)
        related_config_keys.extend(current_related_config_keys)

        # 验证并设置文本转语音配置默认值
        config, current_related_config_keys = TextToSpeechConfigManager.validate_and_set_defaults(config)
        related_config_keys.extend(current_related_config_keys)

        # 返回检索资源配置默认值
        config, current_related_config_keys = RetrievalResourceConfigManager.validate_and_set_defaults(config)
        related_config_keys.extend(current_related_config_keys)

        # 验证并设置审核配置默认值
        config, current_related_config_keys = SensitiveWordAvoidanceConfigManager.validate_and_set_defaults(tenant_id,
                                                                                                            config)
        related_config_keys.extend(current_related_config_keys)

        related_config_keys = list(set(related_config_keys))  # 去除重复的配置键

        # 过滤出相关的配置参数
        filtered_config = {key: config.get(key) for key in related_config_keys}

        return filtered_config
