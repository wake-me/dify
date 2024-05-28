class RetrievalResourceConfigManager:
    @classmethod
    def convert(cls, config: dict) -> bool:
        """
        根据配置字典判断是否展示检索源。

        :param config: 包含检索资源配置的字典。
        :return: 布尔值，指示是否应该展示检索源。
        """
        show_retrieve_source = False  # 默认不展示检索源
        retriever_resource_dict = config.get('retriever_resource')
        if retriever_resource_dict:
            if retriever_resource_dict.get('enabled'):
                show_retrieve_source = True
        return show_retrieve_source

    @classmethod
    def validate_and_set_defaults(cls, config: dict) -> tuple[dict, list[str]]:
        """
        验证并设置检索资源特性的默认值。

        :param config: 应用模型配置参数。
        :return: 元组，包含更新后的配置字典和一个字符串列表，列出处理过程中的关键路径。
        :raises ValueError: 如果配置类型不正确，则抛出异常。
        """
        # 如果retriever_resource配置不存在，则默认为禁用
        if not config.get("retriever_resource"):
            config["retriever_resource"] = {
                "enabled": False
            }

        # 确保retriever_resource是字典类型
        if not isinstance(config["retriever_resource"], dict):
            raise ValueError("retriever_resource must be of dict type")

        # 如果未设置启用标志或启用标志为假，则默认禁用
        if "enabled" not in config["retriever_resource"] or not config["retriever_resource"]["enabled"]:
            config["retriever_resource"]["enabled"] = False

        # 确保启用标志是布尔类型
        if not isinstance(config["retriever_resource"]["enabled"], bool):
            raise ValueError("enabled in retriever_resource must be of boolean type")

        return config, ["retriever_resource"]