class MoreLikeThisConfigManager:
    @classmethod
    def convert(cls, config: dict) -> bool:
        """
        将模型配置转换为特定的模型配置格式。

        :param config: 模型配置参数字典。
        :return: 布尔值，表示是否启用了"more_like_this"特性。
        """
        more_like_this = False  # 默认不启用"more_like_this"特性
        # 尝试从配置中获取"more_like_this"字典
        more_like_this_dict = config.get('more_like_this')
        if more_like_this_dict:
            # 如果"more_like_this"字典中包含"enabled"且其值为真，则启用"more_like_this"特性
            if 'enabled' in more_like_this_dict and more_like_this_dict['enabled']:
                more_like_this = True
        return more_like_this

    @classmethod
    def validate_and_set_defaults(cls, config: dict) -> tuple[dict, list[str]]:
        """
        验证并为"more_like_this"特性设置默认值。

        :param config: 应用模型配置参数字典。
        :return: 一个元组，包含校验后的配置字典和被修改的字段列表。
        :raises ValueError: 如果"more_like_this"配置项不是字典类型或"enabled"项不是布尔类型。
        """
        # 如果配置中没有"more_like_this"项，则默认设置为不启用
        if not config.get("more_like_this"):
            config["more_like_this"] = {
                "enabled": False
            }

        # 如果"more_like_this"不是字典类型，则抛出异常
        if not isinstance(config["more_like_this"], dict):
            raise ValueError("more_like_this must be of dict type")

        # 如果"more_like_this"未启用或者"enabled"字段不存在，则默认设置为不启用
        if "enabled" not in config["more_like_this"] or not config["more_like_this"]["enabled"]:
            config["more_like_this"]["enabled"] = False

        # 如果"enabled"字段不是布尔类型，则抛出异常
        if not isinstance(config["more_like_this"]["enabled"], bool):
            raise ValueError("enabled in more_like_this must be of boolean type")

        return config, ["more_like_this"]