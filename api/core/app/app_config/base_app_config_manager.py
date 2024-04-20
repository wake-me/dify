from typing import Optional, Union

from core.app.app_config.entities import AppAdditionalFeatures, EasyUIBasedAppModelConfigFrom
from core.app.app_config.features.file_upload.manager import FileUploadConfigManager
from core.app.app_config.features.more_like_this.manager import MoreLikeThisConfigManager
from core.app.app_config.features.opening_statement.manager import OpeningStatementConfigManager
from core.app.app_config.features.retrieval_resource.manager import RetrievalResourceConfigManager
from core.app.app_config.features.speech_to_text.manager import SpeechToTextConfigManager
from core.app.app_config.features.suggested_questions_after_answer.manager import (
    SuggestedQuestionsAfterAnswerConfigManager,
)
from core.app.app_config.features.text_to_speech.manager import TextToSpeechConfigManager
from models.model import AppMode, AppModelConfig


class BaseAppConfigManager:

    @classmethod
    def convert_to_config_dict(cls, config_from: EasyUIBasedAppModelConfigFrom,
                                app_model_config: Union[AppModelConfig, dict],
                                config_dict: Optional[dict] = None) -> dict:
        """
        将应用模型配置转换为配置字典
        :param config_from: 应用模型配置的来源
        :param app_model_config: 应用模型配置，可以是AppModelConfig实例或其字典表示
        :param config_dict: 应用模型配置字典，如果提供，则将结果存储在此字典中
        :return: 转换后的配置字典
        """
        if config_from != EasyUIBasedAppModelConfigFrom.ARGS:
            # 当配置来源不是命令行参数时，将应用模型配置转换为字典并复制到config_dict中
            app_model_config_dict = app_model_config.to_dict() if isinstance(app_model_config, AppModelConfig) else app_model_config
            config_dict = app_model_config_dict.copy()

        return config_dict

    @classmethod
    def convert_features(cls, config_dict: dict, app_mode: AppMode) -> AppAdditionalFeatures:
        """
        将应用配置转换为应用模型配置

        :param config_dict: 应用配置字典
        :param app_mode: 应用模式
        :return: 返回应用附加功能对象，包含各种配置转换后的结果
        """
        # 复制配置字典，以避免原始配置被修改
        config_dict = config_dict.copy()

        # 初始化附加功能对象
        additional_features = AppAdditionalFeatures()
        # 转换检索资源配置
        additional_features.show_retrieve_source = RetrievalResourceConfigManager.convert(
            config=config_dict
        )

        # 根据应用模式，转换文件上传配置
        additional_features.file_upload = FileUploadConfigManager.convert(
            config=config_dict,
            is_vision=app_mode in [AppMode.CHAT, AppMode.COMPLETION, AppMode.AGENT_CHAT]
        )

        # 转换开场白配置
        additional_features.opening_statement, additional_features.suggested_questions = \
            OpeningStatementConfigManager.convert(
                config=config_dict
            )

        # 转换回答后的建议问题配置
        additional_features.suggested_questions_after_answer = SuggestedQuestionsAfterAnswerConfigManager.convert(
            config=config_dict
        )

        # 转换更多类似内容配置
        additional_features.more_like_this = MoreLikeThisConfigManager.convert(
            config=config_dict
        )

        # 转换语音转文本配置
        additional_features.speech_to_text = SpeechToTextConfigManager.convert(
            config=config_dict
        )

        # 转换文本转语音配置
        additional_features.text_to_speech = TextToSpeechConfigManager.convert(
            config=config_dict
        )

        return additional_features
