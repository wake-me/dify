from collections.abc import Mapping
from typing import Any

from core.app.app_config.entities import AppAdditionalFeatures
from core.app.app_config.features.file_upload.manager import FileUploadConfigManager
from core.app.app_config.features.more_like_this.manager import MoreLikeThisConfigManager
from core.app.app_config.features.opening_statement.manager import OpeningStatementConfigManager
from core.app.app_config.features.retrieval_resource.manager import RetrievalResourceConfigManager
from core.app.app_config.features.speech_to_text.manager import SpeechToTextConfigManager
from core.app.app_config.features.suggested_questions_after_answer.manager import (
    SuggestedQuestionsAfterAnswerConfigManager,
)
from core.app.app_config.features.text_to_speech.manager import TextToSpeechConfigManager
from models.model import AppMode


class BaseAppConfigManager:
    @classmethod
    def convert_features(cls, config_dict: Mapping[str, Any], app_mode: AppMode) -> AppAdditionalFeatures:
        """
        将应用配置转换为应用模型配置

        :param config_dict: 应用配置字典
        :param app_mode: 应用模式
        :return: 返回应用附加功能对象，包含各种配置转换后的结果
        """
        config_dict = dict(config_dict.items())

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
