from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional

from pydantic import BaseModel

from core.extension.extensible import Extensible, ExtensionModule


class ModerationAction(Enum):
    """
    中介行为枚举类，定义了中介操作的类型。

    属性:
    - DIRECT_OUTPUT: 直接输出
    - OVERRIDED: 被覆盖
    """
    DIRECT_OUTPUT = 'direct_output'
    OVERRIDED = 'overrided'


class ModerationInputsResult(BaseModel):
    """
    中介输入结果模型类，用于定义中介过程中的输入结果。

    属性:
    - flagged: 布尔值，标识是否被标记为需要特别关注。
    - action: ModerationAction枚举，表示采取的中介行为。
    - preset_response: 字符串，预设的响应信息。
    - inputs: 字典，包含中介过程的输入数据。
    - query: 字符串，相关的查询信息。
    """
    flagged: bool = False
    action: ModerationAction
    preset_response: str = ""
    inputs: dict = {}
    query: str = ""


class ModerationOutputsResult(BaseModel):
    """
    中介输出结果模型类，用于定义中介过程后的输出结果。

    属性:
    - flagged: 布尔值，标识最终是否被标记为需要特别关注。
    - action: ModerationAction枚举，表示最终采取的中介行为。
    - preset_response: 字符串，最终的预设响应信息。
    - text: 字符串，处理后的文本输出。
    """
    flagged: bool = False
    action: ModerationAction
    preset_response: str = ""
    text: str = ""

class Moderation(Extensible, ABC):
    """
    中介类的基类，用于定义中介处理的通用方法和属性。
    """

    module: ExtensionModule = ExtensionModule.MODERATION  # 指定模块为中介。

    def __init__(self, app_id: str, tenant_id: str, config: Optional[dict] = None) -> None:
        """
        初始化方法。
        
        :param app_id: 应用ID。
        :param tenant_id: 工作空间ID。
        :param config: 中介配置，可选。
        """
        super().__init__(tenant_id, config)
        self.app_id = app_id

    @classmethod
    @abstractmethod
    def validate_config(cls, tenant_id: str, config: dict) -> None:
        """
        验证传入的表单配置数据。
        
        :param tenant_id: 工作空间ID。
        :param config: 表单配置数据。
        """
        raise NotImplementedError

    @abstractmethod
    def moderation_for_inputs(self, inputs: dict, query: str = "") -> ModerationInputsResult:
        """
        对输入进行中介处理。
        
        :param inputs: 用户输入。
        :param query: 查询字符串（在聊天应用中为必需）。
        :return: 中介处理结果。
        """
        raise NotImplementedError

    @abstractmethod
    def moderation_for_outputs(self, text: str) -> ModerationOutputsResult:
        """
        对输出进行中介处理。
        
        :param text: LLM输出内容。
        :return: 中介处理结果。
        """
        raise NotImplementedError

    @classmethod
    def _validate_inputs_and_outputs_config(cls, config: dict, is_preset_response_required: bool) -> None:
        """
        验证输入和输出配置的合法性。

        :param config: 中介配置。
        :param is_preset_response_required: 是否需要预设响应。
        """
        # 验证输入配置
        inputs_config = config.get("inputs_config")
        if not isinstance(inputs_config, dict):
            raise ValueError("inputs_config must be a dict")

        # 验证输出配置
        outputs_config = config.get("outputs_config")
        if not isinstance(outputs_config, dict):
            raise ValueError("outputs_config must be a dict")

        # 检查是否至少开启了一种配置
        inputs_config_enabled = inputs_config.get("enabled")
        outputs_config_enabled = outputs_config.get("enabled")
        if not inputs_config_enabled and not outputs_config_enabled:
            raise ValueError("At least one of inputs_config or outputs_config must be enabled")

        # 如果需要预设响应，则验证预设响应的设置
        if not is_preset_response_required:
            return

        # 验证输入配置中的预设响应
        if inputs_config_enabled:
            if not inputs_config.get("preset_response"):
                raise ValueError("inputs_config.preset_response is required")

            if len(inputs_config.get("preset_response")) > 100:
                raise ValueError("inputs_config.preset_response must be less than 100 characters")

        # 验证输出配置中的预设响应
        if outputs_config_enabled:
            if not outputs_config.get("preset_response"):
                raise ValueError("outputs_config.preset_response is required")

            if len(outputs_config.get("preset_response")) > 100:
                raise ValueError("outputs_config.preset_response must be less than 100 characters")


class ModerationException(Exception):
    pass
