class SpeechToTextConfigManager:
    @classmethod
    def convert(cls, config: dict) -> bool:
        """
        将配置字典中的语音转文本配置项转换为布尔值，表示是否启用语音转文本功能。
        
        :param config: 包含语音转文本配置的字典。
        :return: 布尔值，表示是否启用了语音转文本功能。
        """
        speech_to_text = False  # 默认不启用语音转文本
        # 检查配置中是否存在语音转文本的配置，并尝试读取其启用状态
        speech_to_text_dict = config.get('speech_to_text')
        if speech_to_text_dict:
            if speech_to_text_dict.get('enabled'):
                speech_to_text = True

        return speech_to_text

    @classmethod
    def validate_and_set_defaults(cls, config: dict) -> tuple[dict, list[str]]:
        """
        验证并设置语音转文本功能的默认配置。
        
        :param config: 应用模型配置的字典。
        :return: 一个元组，包含更新后的配置字典和配置变更列表。
        """
        # 检查配置中是否包含语音转文本项，若无则设置为默认值（禁用）
        if not config.get("speech_to_text"):
            config["speech_to_text"] = {
                "enabled": False
            }

        # 确保语音转文本的配置是字典类型
        if not isinstance(config["speech_to_text"], dict):
            raise ValueError("speech_to_text must be of dict type")

        # 如果未设置启用状态或设置为非真值，则默认为禁用
        if "enabled" not in config["speech_to_text"] or not config["speech_to_text"]["enabled"]:
            config["speech_to_text"]["enabled"] = False

        # 确保启用状态是布尔值
        if not isinstance(config["speech_to_text"]["enabled"], bool):
            raise ValueError("enabled in speech_to_text must be of boolean type")

        return config, ["speech_to_text"]