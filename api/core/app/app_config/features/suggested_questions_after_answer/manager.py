class SuggestedQuestionsAfterAnswerConfigManager:
    @classmethod
    def convert(cls, config: dict) -> bool:
        """
        将配置字典转换为布尔值，以确定是否启用回答后建议问题的功能。
        
        :param config: 模型配置字典，其中应包含'suggested_questions_after_answer'键。
        :return: 布尔值，表示是否启用了回答后建议问题的功能。
        """
        suggested_questions_after_answer = False  # 默认不启用
        suggested_questions_after_answer_dict = config.get('suggested_questions_after_answer')
        # 检查配置中是否明确启用了回答后建议问题的功能
        if suggested_questions_after_answer_dict:
            if 'enabled' in suggested_questions_after_answer_dict and suggested_questions_after_answer_dict['enabled']:
                suggested_questions_after_answer = True
        return suggested_questions_after_answer

    @classmethod
    def validate_and_set_defaults(cls, config: dict) -> tuple[dict, list[str]]:
        """
        验证配置，并为建议问题功能设置默认值。

        :param config: 应用模型配置字典，需要包含'suggested_questions_after_answer'键。
        :return: 一个元组，包含已验证和可能更新的配置字典，以及一个包含所有修改过的键的列表。
        :raises ValueError: 如果配置类型不正确或缺少必要字段，则抛出异常。
        """
        # 如果配置中没有'suggested_questions_after_answer'，则默认为不启用
        if not config.get("suggested_questions_after_answer"):
            config["suggested_questions_after_answer"] = {
                "enabled": False
            }

        # 确保'suggested_questions_after_answer'是字典类型
        if not isinstance(config["suggested_questions_after_answer"], dict):
            raise ValueError("suggested_questions_after_answer must be of dict type")

        # 设置'suggested_questions_after_answer'的默认值为不启用
        if "enabled" not in config["suggested_questions_after_answer"] or not \
        config["suggested_questions_after_answer"]["enabled"]:
            config["suggested_questions_after_answer"]["enabled"] = False

        # 确保'enabled'字段的类型为布尔值
        if not isinstance(config["suggested_questions_after_answer"]["enabled"], bool):
            raise ValueError("enabled in suggested_questions_after_answer must be of boolean type")

        return config, ["suggested_questions_after_answer"]