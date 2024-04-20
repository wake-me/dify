from core.app.apps.base_app_queue_manager import AppQueueManager, GenerateTaskStoppedException, PublishFrom
from core.app.entities.app_invoke_entities import InvokeFrom
from core.app.entities.queue_entities import (
    AppQueueEvent,
    QueueErrorEvent,
    QueueMessageEndEvent,
    QueueStopEvent,
    QueueWorkflowFailedEvent,
    QueueWorkflowSucceededEvent,
    WorkflowQueueMessage,
)


class WorkflowAppQueueManager(AppQueueManager):

    def __init__(self, task_id: str,
                 user_id: str,
                 invoke_from: InvokeFrom,
                 app_mode: str) -> None:
        """
        初始化函数
        
        :param task_id: 任务ID，字符串类型，用于标识任务
        :param user_id: 用户ID，字符串类型，标识任务的发起用户
        :param invoke_from: 调用来源，InvokeFrom枚举类型，标识任务的调用来源
        :param app_mode: 应用模式，字符串类型，标识应用的运行模式
        :return: 无返回值
        """
        super().__init__(task_id, user_id, invoke_from)  # 调用父类构造函数初始化共同属性

        self._app_mode = app_mode  # 初始化应用模式属性

    def _publish(self, event: AppQueueEvent, pub_from: PublishFrom) -> None:
        """
        将事件发布到队列中。
        
        :param event: 要发布到队列的事件，类型为AppQueueEvent。
        :param pub_from: 事件的来源，类型为PublishFrom。
        :return: 无返回值。
        """
        # 构造工作流队列消息
        message = WorkflowQueueMessage(
            task_id=self._task_id,
            app_mode=self._app_mode,
            event=event
        )

        # 将消息放入队列
        self._q.put(message)

        # 检查事件类型，如果是终止队列监听的事件，则停止监听
        if isinstance(event, QueueStopEvent
                             | QueueErrorEvent
                             | QueueMessageEndEvent
                             | QueueWorkflowSucceededEvent
                             | QueueWorkflowFailedEvent):
            self.stop_listen()

        # 如果事件来源是应用管理器，并且当前状态为已停止，则抛出任务停止异常
        if pub_from == PublishFrom.APPLICATION_MANAGER and self._is_stopped():
            raise GenerateTaskStoppedException()
