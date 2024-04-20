from core.app.app_config.base_app_config_manager import BaseAppConfigManager
from core.app.app_config.common.sensitive_word_avoidance.manager import SensitiveWordAvoidanceConfigManager
from core.app.app_config.entities import WorkflowUIBasedAppConfig
from core.app.app_config.features.file_upload.manager import FileUploadConfigManager
from core.app.app_config.features.text_to_speech.manager import TextToSpeechConfigManager
from core.app.app_config.workflow_ui_based_app.variables.manager import WorkflowVariablesConfigManager
from models.model import App, AppMode
from models.workflow import Workflow


class WorkflowAppConfig(WorkflowUIBasedAppConfig):
    """
    Workflow App Config Entity.
    """
    pass


class WorkflowAppConfigManager(BaseAppConfigManager):
    @classmethod
    def get_app_config(cls, app_model: App, workflow: Workflow) -> WorkflowAppConfig:
        """
        获取应用程序的配置信息，基于给定的应用模型和工作流模型生成工作流应用配置。

        :param cls: 用于调用的类，通常为当前类。
        :param app_model: 应用模型，包含应用的基本信息如租户ID、应用ID和运行模式。
        :param workflow: 工作流模型，包含工作流的基本信息和配置如特征字典。
        :return: 返回一个WorkflowAppConfig实例，包含应用程序在指定工作流中的配置。
        """
        # 从工作流模型中获取特征字典
        features_dict = workflow.features_dict

        # 将应用模型的运行模式转换为AppMode枚举类型
        app_mode = AppMode.value_of(app_model.mode)
        # 创建工作流应用配置实例
        app_config = WorkflowAppConfig(
            tenant_id=app_model.tenant_id,
            app_id=app_model.id,
            app_mode=app_mode,
            workflow_id=workflow.id,
            sensitive_word_avoidance=SensitiveWordAvoidanceConfigManager.convert(
                config=features_dict
            ),  # 将特征字典转换为敏感词规避配置
            variables=WorkflowVariablesConfigManager.convert(
                workflow=workflow
            ),  # 将工作流模型转换为变量配置
            additional_features=cls.convert_features(features_dict, app_mode)  # 转换并获取额外的特征配置
        )

        return app_config

    @classmethod
    def config_validate(cls, tenant_id: str, config: dict, only_structure_validate: bool = False) -> dict:
        """
        验证工作流应用程序模型的配置

        :param tenant_id: 租户id
        :param config: 应用模型配置参数
        :param only_structure_validate: 仅验证配置的结构
        :return: 验证后的配置字典
        """
        related_config_keys = []

        # 文件上传验证
        config, current_related_config_keys = FileUploadConfigManager.validate_and_set_defaults(
            config=config,
            is_vision=False
        )
        related_config_keys.extend(current_related_config_keys)

        # 文本转语音验证
        config, current_related_config_keys = TextToSpeechConfigManager.validate_and_set_defaults(config)
        related_config_keys.extend(current_related_config_keys)

        # 中介审核验证
        config, current_related_config_keys = SensitiveWordAvoidanceConfigManager.validate_and_set_defaults(
            tenant_id=tenant_id,
            config=config,
            only_structure_validate=only_structure_validate
        )
        related_config_keys.extend(current_related_config_keys)

        # 去除重复的配置键
        related_config_keys = list(set(related_config_keys))

        # 过滤掉额外的参数
        filtered_config = {key: config.get(key) for key in related_config_keys}

        return filtered_config
