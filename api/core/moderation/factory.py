from core.extension.extensible import ExtensionModule
from core.moderation.base import Moderation, ModerationInputsResult, ModerationOutputsResult
from extensions.ext_code_based_extension import code_based_extension


class ModerationFactory:
    __extension_instance: Moderation

    def __init__(self, name: str, app_id: str, tenant_id: str, config: dict) -> None:
        """
        初始化 ModerationFactory 实例。

        :param name: 扩展名。
        :param app_id: 应用ID。
        :param tenant_id: 工作空间ID。
        :param config: 扩展配置字典。
        """
        extension_class = code_based_extension.extension_class(ExtensionModule.MODERATION, name)
        self.__extension_instance = extension_class(app_id, tenant_id, config)

    @classmethod
    def validate_config(cls, name: str, tenant_id: str, config: dict) -> None:
        """
        验证传入的表单配置数据。

        :param name: 扩展名称。
        :param tenant_id: 工作空间ID。
        :param config: 表单配置数据。
        """
        code_based_extension.validate_form_schema(ExtensionModule.MODERATION, name, config)
        extension_class = code_based_extension.extension_class(ExtensionModule.MODERATION, name)
        extension_class.validate_config(tenant_id, config)

    def moderation_for_inputs(self, inputs: dict, query: str = "") -> ModerationInputsResult:
        """
        对输入内容进行审核。
        
        在用户输入后，调用此方法对用户输入进行敏感内容审查，并返回处理结果。

        :param inputs: 用户输入的内容字典。
        :param query: 查询字符串（在聊天应用中为必需）。
        :return: 返回审核输入结果的实例。
        """
        return self.__extension_instance.moderation_for_inputs(inputs, query)

    def moderation_for_outputs(self, text: str) -> ModerationOutputsResult:
        """
        对输出内容进行审核。
        
        当LLM输出内容时，前端会将输出内容（可能是分段的）传给此方法进行敏感内容审查，审查失败的内容将被屏蔽。

        :param text: LLM输出的内容。
        :return: 返回审核输出结果的实例。
        """
        return self.__extension_instance.moderation_for_outputs(text)