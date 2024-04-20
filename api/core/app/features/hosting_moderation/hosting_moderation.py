import logging

from core.app.entities.app_invoke_entities import EasyUIBasedAppGenerateEntity
from core.helper import moderation
from core.model_runtime.entities.message_entities import PromptMessage

logger = logging.getLogger(__name__)

class HostingModerationFeature:
    def check(self, application_generate_entity: EasyUIBasedAppGenerateEntity,
              prompt_messages: list[PromptMessage]) -> bool:
        """
        检查宿主审核
        :param application_generate_entity: 应用生成实体，包含应用的配置信息等
        :param prompt_messages: 提示信息列表，每个提示信息可能包含需要审核的文本内容
        :return: 审核结果，True表示通过，False表示不通过
        """
        # 获取应用的模型配置
        model_config = application_generate_entity.model_config

        # 组合所有提示信息中的文本内容
        text = ""
        for prompt_message in prompt_messages:
            if isinstance(prompt_message.content, str):
                text += prompt_message.content + "\n"

        # 使用模型配置和文本内容进行审核检查
        moderation_result = moderation.check_moderation(
            model_config,
            text
        )

        return moderation_result