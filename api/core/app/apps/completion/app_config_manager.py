from typing import Optional

from core.app.app_config.base_app_config_manager import BaseAppConfigManager
from core.app.app_config.common.sensitive_word_avoidance.manager import SensitiveWordAvoidanceConfigManager
from core.app.app_config.easy_ui_based_app.dataset.manager import DatasetConfigManager
from core.app.app_config.easy_ui_based_app.model_config.manager import ModelConfigManager
from core.app.app_config.easy_ui_based_app.prompt_template.manager import PromptTemplateConfigManager
from core.app.app_config.easy_ui_based_app.variables.manager import BasicVariablesConfigManager
from core.app.app_config.entities import EasyUIBasedAppConfig, EasyUIBasedAppModelConfigFrom
from core.app.app_config.features.file_upload.manager import FileUploadConfigManager
from core.app.app_config.features.more_like_this.manager import MoreLikeThisConfigManager
from core.app.app_config.features.text_to_speech.manager import TextToSpeechConfigManager
from models.model import App, AppMode, AppModelConfig


class CompletionAppConfig(EasyUIBasedAppConfig):
    """
    Completion App Config Entity.
    """
    pass


class CompletionAppConfigManager(BaseAppConfigManager):
    @classmethod
    def get_app_config(cls, app_model: App,
                        app_model_config: AppModelConfig,
                        override_config_dict: Optional[dict] = None) -> CompletionAppConfig:
        """
        将应用模型配置转换为完成应用配置。
        :param app_model: 应用模型，包含应用的基本信息。
        :param app_model_config: 应用模型配置，具体定义了应用的配置细节。
        :param override_config_dict: 覆盖应用模型配置的字典，可选。
        :return: 返回一个CompletionAppConfig实例，包含了转换后的应用配置。
        """
        # 根据是否提供了覆盖配置来决定配置来源
        if override_config_dict:
            config_from = EasyUIBasedAppModelConfigFrom.ARGS
        else:
            config_from = EasyUIBasedAppModelConfigFrom.APP_LATEST_CONFIG

        # 根据配置来源获取配置字典
        if config_from != EasyUIBasedAppModelConfigFrom.ARGS:
            app_model_config_dict = app_model_config.to_dict()
            config_dict = app_model_config_dict.copy()
        else:
            config_dict = override_config_dict

        # 将应用模式转换为枚举类型，并初始化CompletionAppConfig实例
        app_mode = AppMode.value_of(app_model.mode)
        app_config = CompletionAppConfig(
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

        # 转换基础变量配置和外部数据变量配置
        app_config.variables, app_config.external_data_variables = BasicVariablesConfigManager.convert(
            config=config_dict
        )

        return app_config

    @classmethod
    def config_validate(cls, tenant_id: str, config: dict) -> dict:
        """
        验证完成应用模型配置的完整性

        :param tenant_id: 租户id
        :param config: 应用模型配置参数
        :return: 验证后包含所有相关配置键的字典
        """
        # 初始化应用模式为完成模式
        app_mode = AppMode.COMPLETION

        related_config_keys = []

        # 验证并设置模型配置的默认值
        config, current_related_config_keys = ModelConfigManager.validate_and_set_defaults(tenant_id, config)
        related_config_keys.extend(current_related_config_keys)

        # 验证并设置用户输入表单的默认值
        config, current_related_config_keys = BasicVariablesConfigManager.validate_and_set_defaults(tenant_id, config)
        related_config_keys.extend(current_related_config_keys)

        # 验证并设置文件上传配置的默认值
        config, current_related_config_keys = FileUploadConfigManager.validate_and_set_defaults(config)
        related_config_keys.extend(current_related_config_keys)

        # 验证并设置提示模板配置的默认值
        config, current_related_config_keys = PromptTemplateConfigManager.validate_and_set_defaults(app_mode, config)
        related_config_keys.extend(current_related_config_keys)

        # 验证并设置数据集查询变量配置的默认值
        config, current_related_config_keys = DatasetConfigManager.validate_and_set_defaults(tenant_id, app_mode,
                                                                                            config)
        related_config_keys.extend(current_related_config_keys)

        # 验证并设置文本转语音配置的默认值
        config, current_related_config_keys = TextToSpeechConfigManager.validate_and_set_defaults(config)
        related_config_keys.extend(current_related_config_keys)

        # 验证并设置"更多类似"配置的默认值
        config, current_related_config_keys = MoreLikeThisConfigManager.validate_and_set_defaults(config)
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
