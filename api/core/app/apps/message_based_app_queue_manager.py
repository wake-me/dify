from core.app.apps.base_app_queue_manager import AppQueueManager, GenerateTaskStoppedException, PublishFrom
from core.app.entities.app_invoke_entities import InvokeFrom
from core.app.entities.queue_entities import (
    AppQueueEvent,
    MessageQueueMessage,
    QueueAdvancedChatMessageEndEvent,
    QueueErrorEvent,
    QueueMessage,
    QueueMessageEndEvent,
    QueueStopEvent,
)


class MessageBasedAppQueueManager(AppQueueManager):
    """
    基于消息的應用队列管理器，继承自AppQueueManager。
    用于管理和发布应用队列事件。

    :param task_id: 任务ID，字符串类型。
    :param user_id: 用户ID，字符串类型。
    :param invoke_from: 调用来源，InvokeFrom枚举类型。
    :param conversation_id: 对话ID，字符串类型。
    :param app_mode: 应用模式，字符串类型。
    :param message_id: 消息ID，字符串类型。
    """

    def __init__(self, task_id: str,
                 user_id: str,
                 invoke_from: InvokeFrom,
                 conversation_id: str,
                 app_mode: str,
                 message_id: str) -> None:
        super().__init__(task_id, user_id, invoke_from)
        # 初始化对话ID、应用模式和消息ID
        self._conversation_id = str(conversation_id)
        self._app_mode = app_mode
        self._message_id = str(message_id)

    def construct_queue_message(self, event: AppQueueEvent) -> QueueMessage:
        """
        构建队列消息对象。
        
        :param event: 应用队列事件，AppQueueEvent类型。
        :return: 队列消息对象，QueueMessage类型。
        """
        return MessageQueueMessage(
            task_id=self._task_id,
            message_id=self._message_id,
            conversation_id=self._conversation_id,
            app_mode=self._app_mode,
            event=event
        )

    def _publish(self, event: AppQueueEvent, pub_from: PublishFrom) -> None:
        """
        将事件发布到队列中。
        
        :param event: 要发布的应用队列事件。
        :param pub_from: 发布来源，PublishFrom枚举类型。
        :return: 无返回值。
        """
        # 构建消息队列消息对象并放入队列
        message = MessageQueueMessage(
            task_id=self._task_id,
            message_id=self._message_id,
            conversation_id=self._conversation_id,
            app_mode=self._app_mode,
            event=event
        )
        self._q.put(message)

        # 如果事件为停止、错误、消息结束或高级聊天消息结束事件，则停止监听
        if isinstance(event, QueueStopEvent
                             | QueueErrorEvent
                             | QueueMessageEndEvent
                             | QueueAdvancedChatMessageEndEvent):
            self.stop_listen()

        # 如果发布来源为应用管理器，并且队列已停止，则抛出生成任务停止异常
        if pub_from == PublishFrom.APPLICATION_MANAGER and self._is_stopped():
            raise GenerateTaskStoppedException()

