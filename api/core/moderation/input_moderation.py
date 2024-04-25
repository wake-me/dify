import logging

from core.app.app_config.entities import AppConfig
from core.moderation.base import ModerationAction, ModerationException
from core.moderation.factory import ModerationFactory

logger = logging.getLogger(__name__)


class InputModeration:
    def check(self, app_id: str,
              tenant_id: str,
              app_config: AppConfig,
              inputs: dict,
              query: str) -> tuple[bool, dict, str]:
        """
        处理输入内容的审查避免敏感词汇。
        :param app_id: 应用ID
        :param tenant_id: 租户ID
        :param app_config: 应用配置
        :param inputs: 输入内容字典
        :param query: 查询字符串
        :return: 一个元组，包含审查是否通过的布尔值，处理后的输入内容字典，以及审查后的查询字符串
        """
        # 如果应用配置中没有启用敏感词避免机制，则直接返回未处理的输入
        if not app_config.sensitive_word_avoidance:
            return False, inputs, query

        # 获取敏感词避免机制的配置
        sensitive_word_avoidance_config = app_config.sensitive_word_avoidance
        # 确定审查类型
        moderation_type = sensitive_word_avoidance_config.type

        # 根据审查类型创建审查工厂实例
        moderation_factory = ModerationFactory(
            name=moderation_type,
            app_id=app_id,
            tenant_id=tenant_id,
            config=sensitive_word_avoidance_config.config
        )

        # 使用审查工厂对输入内容和查询字符串进行审查
        moderation_result = moderation_factory.moderation_for_inputs(inputs, query)

        # 如果审查结果未标记为有问题，则返回未处理的输入
        if not moderation_result.flagged:
            return False, inputs, query

        # 根据审查结果采取相应动作，如直接输出或覆盖输入内容
        if moderation_result.action == ModerationAction.DIRECT_OUTPUT:
            raise ModerationException(moderation_result.preset_response)
        elif moderation_result.action == ModerationAction.OVERRIDED:
            inputs = moderation_result.inputs
            query = moderation_result.query

        # 返回审查通过标志，处理后的输入和查询字符串
        return True, inputs, query