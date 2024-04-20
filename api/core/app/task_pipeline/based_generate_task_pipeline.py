import logging
import time
from typing import Optional, Union

from core.app.apps.base_app_queue_manager import AppQueueManager
from core.app.entities.app_invoke_entities import (
    AppGenerateEntity,
)
from core.app.entities.queue_entities import (
    QueueErrorEvent,
)
from core.app.entities.task_entities import (
    ErrorStreamResponse,
    PingStreamResponse,
    TaskState,
)
from core.errors.error import QuotaExceededError
from core.model_runtime.errors.invoke import InvokeAuthorizationError, InvokeError
from core.moderation.output_moderation import ModerationRule, OutputModeration
from extensions.ext_database import db
from models.account import Account
from models.model import EndUser, Message

logger = logging.getLogger(__name__)


class BasedGenerateTaskPipeline:
    """
    BasedGenerateTaskPipeline是一个为应用程序生成流式输出和状态管理的类。
    """

    _task_state: TaskState  # 任务状态
    _application_generate_entity: AppGenerateEntity  # 应用生成实体

    def __init__(self, application_generate_entity: AppGenerateEntity,
                 queue_manager: AppQueueManager,
                 user: Union[Account, EndUser],
                 stream: bool) -> None:
        """
        初始化GenerateTaskPipeline。
        :param application_generate_entity: 应用生成实体
        :param queue_manager: 队列管理器
        :param user: 用户
        :param stream: 是否为流式
        """
        self._application_generate_entity = application_generate_entity
        self._queue_manager = queue_manager
        self._user = user
        self._start_at = time.perf_counter()  # 记录开始时间
        self._output_moderation_handler = self._init_output_moderation()  # 初始化输出审核
        self._stream = stream

    def _handle_error(self, event: QueueErrorEvent, message: Optional[Message] = None) -> Exception:
        """
        处理错误事件。
        :param event: 错误事件
        :param message: 消息，可选
        :return: 异常
        """
        logger.debug("error: %s", event.error)
        e = event.error

        if isinstance(e, InvokeAuthorizationError):
            err = InvokeAuthorizationError('Incorrect API key provided')  # API密钥错误
        elif isinstance(e, InvokeError) or isinstance(e, ValueError):
            err = e
        else:
            err = Exception(e.description if getattr(e, 'description', None) is not None else str(e))  # 其他异常

        if message:
            message = db.session.query(Message).filter(Message.id == message.id).first()  # 更新消息状态
            err_desc = self._error_to_desc(err)
            message.status = 'error'
            message.error = err_desc

            db.session.commit()

        return err

    @classmethod
    def _error_to_desc(cls, e: Exception) -> str:
        """
        将异常转换为描述字符串。
        :param e: 异常
        :return: 描述字符串
        """
        if isinstance(e, QuotaExceededError):
            return ("Your quota for Dify Hosted Model Provider has been exhausted. "
                    "Please go to Settings -> Model Provider to complete your own provider credentials.")  # 配额超出

        message = getattr(e, 'description', str(e))
        if not message:
            message = 'Internal Server Error, please contact support.'  # 服务器错误

        return message

    def _error_to_stream_response(self, e: Exception) -> ErrorStreamResponse:
        """
        将异常转换为流式响应。
        :param e: 异常
        :return: 错误流响应
        """
        return ErrorStreamResponse(
            task_id=self._application_generate_entity.task_id,
            err=e
        )

    def _ping_stream_response(self) -> PingStreamResponse:
        """
        生成心跳流响应。
        :return: 心跳流响应
        """
        return PingStreamResponse(task_id=self._application_generate_entity.task_id)

    def _init_output_moderation(self) -> Optional[OutputModeration]:
        """
        初始化输出审核。
        :return: 输出审核实例，如果不需要审核则为None
        """
        app_config = self._application_generate_entity.app_config
        sensitive_word_avoidance = app_config.sensitive_word_avoidance

        if sensitive_word_avoidance:
            return OutputModeration(
                tenant_id=app_config.tenant_id,
                app_id=app_config.app_id,
                rule=ModerationRule(
                    type=sensitive_word_avoidance.type,
                    config=sensitive_word_avoidance.config
                ),
                queue_manager=self._queue_manager
            )

    def _handle_output_moderation_when_task_finished(self, completion: str) -> Optional[str]:
        """
        任务完成时处理输出审核。
        :param completion: 完成状态
        :return: 经过审核的完成状态，如果未进行审核则为None
        """
        # 如果存在输出审核处理器，则停止线程并处理完成状态
        if self._output_moderation_handler:
            self._output_moderation_handler.stop_thread()

            completion = self._output_moderation_handler.moderation_completion(
                completion=completion,
                public_event=False
            )

            self._output_moderation_handler = None  # 清除审核处理器

            return completion

        return None