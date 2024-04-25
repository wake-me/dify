from core.moderation.base import Moderation, ModerationAction, ModerationInputsResult, ModerationOutputsResult


class KeywordsModeration(Moderation):
    name: str = "keywords"

    @classmethod
    def validate_config(cls, tenant_id: str, config: dict) -> None:
        """
        验证传入的表单配置数据。

        :param tenant_id: 工作空间的id
        :param config: 表单的配置数据
        :return: 无返回值，但会抛出异常指出配置错误
        """
        # 校验输入与输出配置是否合法
        cls._validate_inputs_and_outputs_config(config, True)

        # 确保关键词列表不为空
        if not config.get("keywords"):
            raise ValueError("keywords is required")

        # 确保关键词数量不超过1000个
        if len(config.get("keywords")) > 1000:
            raise ValueError("keywords length must be less than 1000")

    def moderation_for_inputs(self, inputs: dict, query: str = "") -> ModerationInputsResult:
        """
        对输入内容进行审核。

        :param inputs: 待审核的输入字典
        :param query: 查询字符串，可选
        :return: 返回审核结果，包括是否标记为违规、操作类型和预设响应
        """
        flagged = False
        preset_response = ""

        # 如果启用了输入审核配置
        if self.config['inputs_config']['enabled']:
            preset_response = self.config['inputs_config']['preset_response']

            # 如果存在查询字符串，添加到输入中
            if query:
                inputs['query__'] = query

            # 移除空值，准备关键词列表
            keywords_list = [keyword for keyword in self.config['keywords'].split('\n') if keyword]

            # 检查输入是否违反了关键词列表
            flagged = self._is_violated(inputs, keywords_list)

        return ModerationInputsResult(flagged=flagged, action=ModerationAction.DIRECT_OUTPUT, preset_response=preset_response)

    def moderation_for_outputs(self, text: str) -> ModerationOutputsResult:
        """
        对输出内容进行审核。

        :param text: 待审核的文本字符串
        :return: 返回审核结果，包括是否标记为违规、操作类型和预设响应
        """
        flagged = False
        preset_response = ""

        # 如果启用了输出审核配置
        if self.config['outputs_config']['enabled']:
            # 移除空值，准备关键词列表
            keywords_list = [keyword for keyword in self.config['keywords'].split('\n') if keyword]

            # 检查文本是否违反了关键词列表
            flagged = self._is_violated({'text': text}, keywords_list)
            preset_response = self.config['outputs_config']['preset_response']

        return ModerationOutputsResult(flagged=flagged, action=ModerationAction.DIRECT_OUTPUT, preset_response=preset_response)

    def _is_violated(self, inputs: dict, keywords_list: list) -> bool:
        """
        检查输入中是否包含任何违规关键词。

        :param inputs: 待检查的输入字典
        :param keywords_list: 关键词列表
        :return: 如果发现违规关键词，返回True，否则返回False
        """
        for value in inputs.values():
            # 遍历输入值，检查是否包含关键词
            if self._check_keywords_in_value(keywords_list, value):
                return True

        return False

    def _check_keywords_in_value(self, keywords_list, value):
        """
        检查给定值中是否包含任何关键词。

        :param keywords_list: 关键词列表
        :param value: 待检查的值
        :return: 如果值中包含关键词，返回True，否则返回False
        """
        for keyword in keywords_list:
            # 检查值中是否包含关键词，不区分大小写
            if keyword.lower() in value.lower():
                return True
        return False