from core.model_manager import ModelManager
from core.model_runtime.entities.model_entities import ModelType
from core.moderation.base import Moderation, ModerationAction, ModerationInputsResult, ModerationOutputsResult


class OpenAIModeration(Moderation):
    # OpenAI内容审核模块，继承自Moderation基类
    name: str = "openai_moderation"

    @classmethod
    def validate_config(cls, tenant_id: str, config: dict) -> None:
        """
        验证传入的表单配置数据。

        :param tenant_id: 工作空间的id
        :param config: 表单配置数据
        :return: 无返回值
        """
        cls._validate_inputs_and_outputs_config(config, True)

    def moderation_for_inputs(self, inputs: dict, query: str = "") -> ModerationInputsResult:
        """
        对输入内容进行审核。

        :param inputs: 待审核的输入字典
        :param query: 查询字符串（可选）
        :return: 返回审核结果，包括是否标记为违规、操作类型和预设响应
        """
        flagged = False  # 标记是否违规
        preset_response = ""  # 预设响应文本

        # 如果输入审核启用
        if self.config['inputs_config']['enabled']:
            preset_response = self.config['inputs_config']['preset_response']  # 获取预设响应

            if query:
                inputs['query__'] = query  # 如果存在查询字符串，添加到输入中
            flagged = self._is_violated(inputs)  # 检查是否违规

        return ModerationInputsResult(flagged=flagged, action=ModerationAction.DIRECT_OUTPUT, preset_response=preset_response)

    def moderation_for_outputs(self, text: str) -> ModerationOutputsResult:
        """
        对输出内容进行审核。

        :param text: 待审核的文本
        :return: 返回审核结果，包括是否标记为违规、操作类型和预设响应
        """
        flagged = False  # 标记是否违规
        preset_response = ""  # 预设响应文本

        # 如果输出审核启用
        if self.config['outputs_config']['enabled']:
            flagged = self._is_violated({'text': text})  # 检查文本是否违规
            preset_response = self.config['outputs_config']['preset_response']  # 获取预设响应

        return ModerationOutputsResult(flagged=flagged, action=ModerationAction.DIRECT_OUTPUT, preset_response=preset_response)

    def _is_violated(self, inputs: dict):
        """
        检查输入内容是否违规。

        :param inputs: 待检查的输入字典
        :return: 返回是否违规的判断结果
        """
        text = '\n'.join(inputs.values())  # 将输入字典的值合并为文本字符串
        model_manager = ModelManager()  # 获取模型管理器实例
        model_instance = model_manager.get_model_instance(
            tenant_id=self.tenant_id,
            provider="openai",
            model_type=ModelType.MODERATION,
            model="text-moderation-stable"
        )  # 获取OpenAI的文本审核模型实例

        openai_moderation = model_instance.invoke_moderation(
            text=text  # 调用模型对文本进行审核
        )

        return openai_moderation  # 返回审核结果