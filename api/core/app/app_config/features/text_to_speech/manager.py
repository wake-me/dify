from core.app.app_config.entities import TextToSpeechEntity


class TextToSpeechConfigManager:
    @classmethod
    def convert(cls, config: dict):
        """
        将模型配置转换为语音合成配置。

        :param config: 模型配置参数
        :return: 返回是否启用了语音合成的布尔值
        """
        text_to_speech = None
        text_to_speech_dict = config.get('text_to_speech')
        # 如果语音合成字典存在且启用标志为真，则启用语音合成
        if text_to_speech_dict:
            if text_to_speech_dict.get('enabled'):
                text_to_speech = TextToSpeechEntity(
                    enabled=text_to_speech_dict.get('enabled'),
                    voice=text_to_speech_dict.get('voice'),
                    language=text_to_speech_dict.get('language'),
                )

        return text_to_speech

    @classmethod
    def validate_and_set_defaults(cls, config: dict) -> tuple[dict, list[str]]:
        """
        验证并为文本转语音功能设置默认值。

        :param config: 应用模型配置参数
        :return: 返回更新后的配置和需要更新的字段列表
        """
        # 如果配置中没有文本转语音部分，则设置默认值
        if not config.get("text_to_speech"):
            config["text_to_speech"] = {
                "enabled": False,
                "voice": "",
                "language": ""
            }

        # 如果文本转语音的配置不是字典类型，则抛出异常
        if not isinstance(config["text_to_speech"], dict):
            raise ValueError("text_to_speech must be of dict type")

        # 如果没有启用文本转语音或者启用标志为假，则设置默认值
        if "enabled" not in config["text_to_speech"] or not config["text_to_speech"]["enabled"]:
            config["text_to_speech"]["enabled"] = False
            config["text_to_speech"]["voice"] = ""
            config["text_to_speech"]["language"] = ""

        # 如果文本转语音的启用标志不是布尔类型，则抛出异常
        if not isinstance(config["text_to_speech"]["enabled"], bool):
            raise ValueError("enabled in text_to_speech must be of boolean type")

        return config, ["text_to_speech"]