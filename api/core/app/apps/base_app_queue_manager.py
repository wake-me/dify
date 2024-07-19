import queue
import time
from abc import abstractmethod
from collections.abc import Generator
from enum import Enum
from typing import Any

from flask import current_app
from sqlalchemy.orm import DeclarativeMeta

from core.app.entities.app_invoke_entities import InvokeFrom
from core.app.entities.queue_entities import (
    AppQueueEvent,
    QueueErrorEvent,
    QueuePingEvent,
    QueueStopEvent,
)
from extensions.ext_redis import redis_client


class PublishFrom(Enum):
    """
    发布来源枚举类，定义了发布内容的来源类型。

    参数:
    无

    返回值:
    无
    """

    APPLICATION_MANAGER = 1  # 来自应用管理器
    TASK_PIPELINE = 2  # 来自任务管道

class AppQueueManager:
    """
    应用队列管理器类，用于管理和操作与特定任务和用户相关的队列。
    
    参数:
    - task_id: str，任务的唯一标识符。
    - user_id: str，用户的唯一标识符。
    - invoke_from: InvokeFrom，指示调用来源的枚举值。
    
    返回值:
    - 无。
    
    异常:
    - 如果user_id为空，则抛出ValueError。
    """
    def __init__(self, task_id: str,
                 user_id: str,
                 invoke_from: InvokeFrom) -> None:
        if not user_id:
            raise ValueError("user is required")

        self._task_id = task_id  # 任务ID
        self._user_id = user_id  # 用户ID
        self._invoke_from = invoke_from  # 调用来源

        # 根据调用来源设置用户前缀，并在Redis中设置任务归属缓存
        user_prefix = 'account' if self._invoke_from in [InvokeFrom.EXPLORE, InvokeFrom.DEBUGGER] else 'end-user'
        redis_client.setex(AppQueueManager._generate_task_belong_cache_key(self._task_id), 1800,
                           f"{user_prefix}-{self._user_id}")

        q = queue.Queue()  # 创建一个队列实例

        self._q = q  # 将队列实例赋值给成员变量

    def listen(self) -> Generator:
        """
        监听队列
        :return: 生成器，逐个返回队列中的消息
        """
        # wait for APP_MAX_EXECUTION_TIME seconds to stop listen
        listen_timeout = current_app.config.get("APP_MAX_EXECUTION_TIME")
        start_time = time.time()
        last_ping_time = 0
        while True:
            try:
                message = self._q.get(timeout=1)  # 尝试从队列获取消息
                if message is None:
                    break  # 如果获取到None，表示要停止监听

                yield message  # 返回消息给调用者
            except queue.Empty:  # 如果队列为空，继续尝试
                continue
            finally:
                elapsed_time = time.time() - start_time  # 计算已过去的时间
                if elapsed_time >= listen_timeout or self._is_stopped():
                    # 如果超过监听超时或已停止，则发送停止信号
                    self.publish(
                        QueueStopEvent(stopped_by=QueueStopEvent.StopBy.USER_MANUAL),
                        PublishFrom.TASK_PIPELINE
                    )

                if elapsed_time // 10 > last_ping_time:  # 每10秒发送一次心跳消息
                    self.publish(QueuePingEvent(), PublishFrom.TASK_PIPELINE)
                    last_ping_time = elapsed_time // 10

    def stop_listen(self) -> None:
        """
        停止监听队列

        本函数用于向队列中放入一个特殊的None值，以通知监听者停止监听队列。
        此方法不接受任何参数。

        :return: 无返回值
        """
        self._q.put(None)  # 向队列中放入None，以指示停止监听

    def publish_error(self, e, pub_from: PublishFrom) -> None:
        """
        发布错误信息
        :param e: 错误对象
        :param pub_from: 发布来源
        :return: 无返回值
        """
        # 发送错误事件到指定的发布来源
        self.publish(QueueErrorEvent(
            error=e
        ), pub_from)

    def publish(self, event: AppQueueEvent, pub_from: PublishFrom) -> None:
        """
        将事件发布到队列中。
        
        :param event: 需要发布的事件对象，继承自AppQueueEvent。
        :param pub_from: 发布事件的来源，使用PublishFrom枚举类型标识。
        :return: 无返回值。
        """
        self._check_for_sqlalchemy_models(event.model_dump())
        self._publish(event, pub_from)

    @abstractmethod
    def _publish(self, event: AppQueueEvent, pub_from: PublishFrom) -> None:
        """
        将事件发布到队列中
        
        :param event: 需要发布的事件对象，继承自AppQueueEvent
        :param pub_from: 发布事件的来源，使用PublishFrom枚举类型标识
        :return: 无返回值
        """
        raise NotImplementedError

    @classmethod
    def set_stop_flag(cls, task_id: str, invoke_from: InvokeFrom, user_id: str) -> None:
        """
        设置任务停止标志
        
        :param cls: 类的引用
        :param task_id: 任务ID，字符串类型
        :param invoke_from: 调用来源枚举类型，标识任务是被探索、调试器还是其他方式触发
        :param user_id: 用户ID，字符串类型
        :return: 无返回值
        """
        # 尝试从Redis获取任务归属的缓存键值
        result = redis_client.get(cls._generate_task_belong_cache_key(task_id))
        if result is None:
            return  # 如果缓存中无此任务归属信息，则直接返回

        # 根据调用来源确定用户前缀
        user_prefix = 'account' if invoke_from in [InvokeFrom.EXPLORE, InvokeFrom.DEBUGGER] else 'end-user'
        # 检查当前操作用户是否为任务归属用户，如果不是，则直接返回
        if result.decode('utf-8') != f"{user_prefix}-{user_id}":
            return

        # 为任务设置停止标志的缓存键，并设置过期时间为600秒
        stopped_cache_key = cls._generate_stopped_cache_key(task_id)
        redis_client.setex(stopped_cache_key, 600, 1)

    def _is_stopped(self) -> bool:
        """
        检查任务是否已停止
        
        :return: 返回一个布尔值，如果任务停止，则为True；否则为False。
        """
        # 生成任务停止状态的缓存键
        stopped_cache_key = AppQueueManager._generate_stopped_cache_key(self._task_id)
        # 从Redis获取任务停止状态
        result = redis_client.get(stopped_cache_key)
        if result is not None:
            # 如果存在停止状态，则任务已停止
            return True

        # 如果没有找到停止状态，则任务未停止
        return False

    @classmethod
    def _generate_task_belong_cache_key(cls, task_id: str) -> str:
        """
        生成任务所属的缓存键
        :param task_id: 任务id，类型为字符串
        :return: 返回生成的缓存键，类型为字符串
        """
        return f"generate_task_belong:{task_id}"

    @classmethod
    def _generate_stopped_cache_key(cls, task_id: str) -> str:
        """
        生成任务停止的缓存键

        :param task_id: 任务id，用于生成特定任务的停止缓存键
        :type task_id: str
        :return: 返回生成的停止缓存键
        :rtype: str
        """
        return f"generate_task_stopped:{task_id}"

    def _check_for_sqlalchemy_models(self, data: Any):
        """
        检查传入的数据中是否包含SQLAlchemy模型实例。
        这个方法递归检查字典或列表中的每一项，如果发现是SQLAlchemy模型实例，
        则抛出TypeError异常，因为传入SQLAlchemy模型实例可能会导致线程安全问题。

        参数:
        - data: 任意类型的数据，通常是字典或列表，其中可能包含SQLAlchemy模型实例。

        返回值:
        - 无返回值，但如果发现SQLAlchemy模型实例，则抛出TypeError异常。
        """
        # 判断data是字典还是列表，进行递归检查
        if isinstance(data, dict):
            for key, value in data.items():
                self._check_for_sqlalchemy_models(value)
        elif isinstance(data, list):
            for item in data:
                self._check_for_sqlalchemy_models(item)
        else:
            # 检查是否是SQLAlchemy模型实例
            if isinstance(data, DeclarativeMeta) or hasattr(data, '_sa_instance_state'):
                raise TypeError("Critical Error: Passing SQLAlchemy Model instances "
                                "that cause thread safety issues is not allowed.")


class GenerateTaskStoppedException(Exception):
    pass
