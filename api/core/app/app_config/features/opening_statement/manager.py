class OpeningStatementConfigManager:
    @classmethod
    def convert(cls, config: dict) -> tuple[str, list]:
        """
        将模型配置转换为模型配置

        :param config: 模型配置参数
        :return: 返回一个元组，包含opening_statement字符串和suggested_questions列表
        """
        # 初始化opening_statement和suggested_questions
        opening_statement = config.get('opening_statement')
        suggested_questions_list = config.get('suggested_questions')

        return opening_statement, suggested_questions_list

    @classmethod
    def validate_and_set_defaults(cls, config: dict) -> tuple[dict, list[str]]:
        """
        验证并为opening statement功能设置默认值

        :param config: 应用模型配置参数
        :return: 返回一个元组，包含经过验证和设置默认值的配置字典，以及包含"opening_statement"和"suggested_questions"的列表
        """
        # 验证并设置opening_statement的默认值
        if not config.get("opening_statement"):
            config["opening_statement"] = ""

        if not isinstance(config["opening_statement"], str):
            raise ValueError("opening_statement必须是字符串类型")

        # 验证并设置suggested_questions的默认值
        if not config.get("suggested_questions"):
            config["suggested_questions"] = []

        if not isinstance(config["suggested_questions"], list):
            raise ValueError("suggested_questions必须是列表类型")

        for question in config["suggested_questions"]:
            if not isinstance(question, str):
                raise ValueError("suggested_questions列表中的元素必须是字符串类型")

        return config, ["opening_statement", "suggested_questions"]