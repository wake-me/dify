import logging
from typing import Optional

from core.app.app_config.entities import AppConfig
from core.moderation.base import ModerationAction, ModerationException
from core.moderation.factory import ModerationFactory
from core.ops.entities.trace_entity import TraceTaskName
from core.ops.ops_trace_manager import TraceQueueManager, TraceTask
from core.ops.utils import measure_time

logger = logging.getLogger(__name__)


class InputModeration:
    def check(
        self, app_id: str,
        tenant_id: str,
        app_config: AppConfig,
        inputs: dict,
        query: str,
        message_id: str,
        trace_manager: Optional[TraceQueueManager] = None
    ) -> tuple[bool, dict, str]:
        """
        Process sensitive_word_avoidance.
        :param app_id: app id
        :param tenant_id: tenant id
        :param app_config: app config
        :param inputs: inputs
        :param query: query
        :param message_id: message id
        :param trace_manager: trace manager
        :return:
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

        with measure_time() as timer:
            moderation_result = moderation_factory.moderation_for_inputs(inputs, query)

        if trace_manager:
            trace_manager.add_trace_task(
                TraceTask(
                    TraceTaskName.MODERATION_TRACE,
                    message_id=message_id,
                    moderation_result=moderation_result,
                    inputs=inputs,
                    timer=timer
                )
            )

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