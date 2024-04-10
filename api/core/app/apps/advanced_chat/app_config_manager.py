
from core.app.app_config.base_app_config_manager import BaseAppConfigManager
from core.app.app_config.common.sensitive_word_avoidance.manager import SensitiveWordAvoidanceConfigManager
from core.app.app_config.entities import WorkflowUIBasedAppConfig
from core.app.app_config.features.file_upload.manager import FileUploadConfigManager
from core.app.app_config.features.opening_statement.manager import OpeningStatementConfigManager
from core.app.app_config.features.retrieval_resource.manager import RetrievalResourceConfigManager
from core.app.app_config.features.speech_to_text.manager import SpeechToTextConfigManager
from core.app.app_config.features.suggested_questions_after_answer.manager import (
    SuggestedQuestionsAfterAnswerConfigManager,
)
from core.app.app_config.features.text_to_speech.manager import TextToSpeechConfigManager
from core.app.app_config.workflow_ui_based_app.variables.manager import WorkflowVariablesConfigManager
from models.model import App, AppMode
from models.workflow import Workflow


class AdvancedChatAppConfig(WorkflowUIBasedAppConfig):
    """
    Advanced Chatbot App Config Entity.
    """
    pass


class AdvancedChatAppConfigManager(BaseAppConfigManager):
    @classmethod
    def get_app_config(cls, app_model: App,
                       workflow: Workflow) -> AdvancedChatAppConfig:
        """
        获取高级聊天应用的配置

        :param app_model: 应用模型，包含应用的基本信息
        :param workflow: 工作流，包含应用的工作流配置
        :return: 高级聊天应用配置对象
        """
        features_dict = workflow.features_dict

        # 根据应用模型获取应用模式
        app_mode = AppMode.value_of(app_model.mode)
        # 构建高级聊天应用配置对象
        app_config = AdvancedChatAppConfig(
            tenant_id=app_model.tenant_id,
            app_id=app_model.id,
            app_mode=app_mode,
            workflow_id=workflow.id,
            sensitive_word_avoidance=SensitiveWordAvoidanceConfigManager.convert(
                config=features_dict
            ),
            variables=WorkflowVariablesConfigManager.convert(
                workflow=workflow
            ),
            additional_features=cls.convert_features(features_dict, app_mode)
        )

        return app_config

    @classmethod
    def config_validate(cls, tenant_id: str, config: dict, only_structure_validate: bool = False) -> dict:
        """
        验证高级聊天应用配置的合法性

        :param tenant_id: 租户ID
        :param config: 应用配置字典
        :param only_structure_validate: 是否只进行结构验证，默认为False，即同时进行结构和内容的验证
        :return: 验证后的配置字典
        """
        related_config_keys = []

        # 进行文件上传配置的验证和设置默认值
        config, current_related_config_keys = FileUploadConfigManager.validate_and_set_defaults(
            config=config,
            is_vision=False
        )
        related_config_keys.extend(current_related_config_keys)

        # 进行开场白配置的验证和设置默认值
        config, current_related_config_keys = OpeningStatementConfigManager.validate_and_set_defaults(config)
        related_config_keys.extend(current_related_config_keys)

        # 进行回答后建议问题配置的验证和设置默认值
        config, current_related_config_keys = SuggestedQuestionsAfterAnswerConfigManager.validate_and_set_defaults(
            config)
        related_config_keys.extend(current_related_config_keys)

        # 进行语音识别配置的验证和设置默认值
        config, current_related_config_keys = SpeechToTextConfigManager.validate_and_set_defaults(config)
        related_config_keys.extend(current_related_config_keys)

        # 进行文本转语音配置的验证和设置默认值
        config, current_related_config_keys = TextToSpeechConfigManager.validate_and_set_defaults(config)
        related_config_keys.extend(current_related_config_keys)

        # 进行检索资源配置的验证和设置默认值
        config, current_related_config_keys = RetrievalResourceConfigManager.validate_and_set_defaults(config)
        related_config_keys.extend(current_related_config_keys)

        # 进行敏感词规避配置的验证和设置默认值
        config, current_related_config_keys = SensitiveWordAvoidanceConfigManager.validate_and_set_defaults(
            tenant_id=tenant_id,
            config=config,
            only_structure_validate=only_structure_validate
        )
        related_config_keys.extend(current_related_config_keys)

        # 去除重复的配置键
        related_config_keys = list(set(related_config_keys))

        # 过滤出相关的配置项
        filtered_config = {key: config.get(key) for key in related_config_keys}

        return filtered_config

