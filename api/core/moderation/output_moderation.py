import logging
import threading
import time
from typing import Any, Optional

from flask import Flask, current_app
from pydantic import BaseModel, ConfigDict

from core.app.apps.base_app_queue_manager import AppQueueManager, PublishFrom
from core.app.entities.queue_entities import QueueMessageReplaceEvent
from core.moderation.base import ModerationAction, ModerationOutputsResult
from core.moderation.factory import ModerationFactory

logger = logging.getLogger(__name__)


class ModerationRule(BaseModel):
    # 中介规则类，定义了中介规则的类型和配置
    type: str  # 规则类型
    config: dict[str, Any]  # 规则配置字典

class OutputModeration(BaseModel):
    # 输出中介类，用于处理和中介相关的输出逻辑
    DEFAULT_BUFFER_SIZE: int = 300  # 默认缓冲区大小

    tenant_id: str  # 租户ID
    app_id: str  # 应用ID

    rule: ModerationRule  # 中介规则
    queue_manager: AppQueueManager  # 队列管理器

    thread: Optional[threading.Thread] = None
    thread_running: bool = True
    buffer: str = ''
    is_final_chunk: bool = False
    final_output: Optional[str] = None
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def should_direct_output(self):
        """
        判断是否应该直接输出
        Returns:
            bool: 如果存在最终输出结果则返回True，否则返回False
        """
        return self.final_output is not None

    def get_final_output(self):
        """
        获取最终输出结果
        Returns:
            Optional[str]: 最终输出结果，如果不存在则为None
        """
        return self.final_output

    def append_new_token(self, token: str):
        """
        向缓冲区追加新token
        Args:
            token (str): 待追加的token
        """
        self.buffer += token

        if not self.thread:
            self.thread = self.start_thread()  # 如果线程未启动，则启动线程

    def moderation_completion(self, completion: str, public_event: bool = False) -> str:
        """
        完成中介处理，并根据处理结果进行相应操作
        Args:
            completion (str): 中介处理完成的数据
            public_event (bool, optional): 是否发布公共事件，默认为False
        Returns:
            str: 最终输出结果
        """
        self.buffer = completion
        self.is_final_chunk = True

        result = self.moderation(
            tenant_id=self.tenant_id,
            app_id=self.app_id,
            moderation_buffer=completion
        )

        if not result or not result.flagged:
            return completion

        if result.action == ModerationAction.DIRECT_OUTPUT:
            final_output = result.preset_response
        else:
            final_output = result.text

        if public_event:
            self.queue_manager.publish(
                QueueMessageReplaceEvent(
                    text=final_output
                ),
                PublishFrom.TASK_PIPELINE
            )

        return final_output

    def start_thread(self) -> threading.Thread:
        """
        启动工作线程
        Returns:
            threading.Thread: 启动的工作线程
        """
        buffer_size = int(current_app.config.get('MODERATION_BUFFER_SIZE', self.DEFAULT_BUFFER_SIZE))
        thread = threading.Thread(target=self.worker, kwargs={
            'flask_app': current_app._get_current_object(),
            'buffer_size': buffer_size if buffer_size > 0 else self.DEFAULT_BUFFER_SIZE
        })

        thread.start()

        return thread

    def stop_thread(self):
        """
        停止工作线程
        """
        if self.thread and self.thread.is_alive():
            self.thread_running = False

    def worker(self, flask_app: Flask, buffer_size: int):
        """
        工作线程入口函数，用于在后台持续处理缓冲区数据
        Args:
            flask_app (Flask): Flask应用实例
            buffer_size (int): 缓冲区大小
        """
        with flask_app.app_context():
            current_length = 0
            while self.thread_running:
                moderation_buffer = self.buffer
                buffer_length = len(moderation_buffer)
                if not self.is_final_chunk:
                    chunk_length = buffer_length - current_length
                    if 0 <= chunk_length < buffer_size:
                        time.sleep(1)
                        continue  # 如果数据块长度未达到缓冲区大小，则继续等待

                current_length = buffer_length

                result = self.moderation(
                    tenant_id=self.tenant_id,
                    app_id=self.app_id,
                    moderation_buffer=moderation_buffer
                )

                if not result or not result.flagged:
                    continue  # 如果结果未标记，则继续收集数据

                if result.action == ModerationAction.DIRECT_OUTPUT:
                    final_output = result.preset_response
                    self.final_output = final_output
                else:
                    final_output = result.text + self.buffer[len(moderation_buffer):]

                # 触发替换事件
                if self.thread_running:
                    self.queue_manager.publish(
                        QueueMessageReplaceEvent(
                            text=final_output
                        ),
                        PublishFrom.TASK_PIPELINE
                    )

                if result.action == ModerationAction.DIRECT_OUTPUT:
                    break

    def moderation(self, tenant_id: str, app_id: str, moderation_buffer: str) -> Optional[ModerationOutputsResult]:
        """
        执行中介处理
        Args:
            tenant_id (str): 租户ID
            app_id (str): 应用ID
            moderation_buffer (str): 待处理的缓冲区数据
        Returns:
            Optional[ModerationOutputsResult]: 中介处理结果，如果处理失败则返回None
        """
        try:
            moderation_factory = ModerationFactory(
                name=self.rule.type,
                app_id=app_id,
                tenant_id=tenant_id,
                config=self.rule.config
            )

            result: ModerationOutputsResult = moderation_factory.moderation_for_outputs(moderation_buffer)
            return result
        except Exception as e:
            logger.error("Moderation Output error: %s", e)

        return None