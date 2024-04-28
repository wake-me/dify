from threading import Thread
from typing import Optional, Union

from flask import Flask, current_app

from core.app.entities.app_invoke_entities import (
    AdvancedChatAppGenerateEntity,
    AgentChatAppGenerateEntity,
    ChatAppGenerateEntity,
    CompletionAppGenerateEntity,
    InvokeFrom,
)
from core.app.entities.queue_entities import (
    QueueAnnotationReplyEvent,
    QueueMessageFileEvent,
    QueueRetrieverResourcesEvent,
)
from core.app.entities.task_entities import (
    AdvancedChatTaskState,
    EasyUITaskState,
    MessageFileStreamResponse,
    MessageReplaceStreamResponse,
    MessageStreamResponse,
)
from core.llm_generator.llm_generator import LLMGenerator
from core.tools.tool_file_manager import ToolFileManager
from extensions.ext_database import db
from models.model import AppMode, Conversation, MessageAnnotation, MessageFile
from services.annotation_service import AppAnnotationService


class MessageCycleManage:
    # 类 `MessageCycleManage` 用于管理消息循环过程中的各种状态和事件处理。
    _application_generate_entity: Union[
        ChatAppGenerateEntity,
        CompletionAppGenerateEntity,
        AgentChatAppGenerateEntity,
        AdvancedChatAppGenerateEntity
    ]
    # `_application_generate_entity` 属性用于指定应用程序生成实体的类型，可以是多种聊天应用生成实体中的一种。
    _task_state: Union[EasyUITaskState, AdvancedChatTaskState]

    def _generate_conversation_name(self, conversation: Conversation, query: str) -> Optional[Thread]:
        """
        Generate conversation name.
        :param conversation: conversation
        :param query: query
        :return: thread
        """
        is_first_message = self._application_generate_entity.conversation_id is None
        extras = self._application_generate_entity.extras
        auto_generate_conversation_name = extras.get('auto_generate_conversation_name', True)

        if auto_generate_conversation_name and is_first_message:
            # start generate thread
            thread = Thread(target=self._generate_conversation_name_worker, kwargs={
                'flask_app': current_app._get_current_object(),
                'conversation_id': conversation.id,
                'query': query
            })

            thread.start()

            return thread

        return None

    def _generate_conversation_name_worker(self,
                                           flask_app: Flask,
                                           conversation_id: str,
                                           query: str):
        with flask_app.app_context():
            # get conversation and message
            conversation = (
                db.session.query(Conversation)
                .filter(Conversation.id == conversation_id)
                .first()
            )

            if conversation.mode != AppMode.COMPLETION.value:
                app_model = conversation.app
                if not app_model:
                    return

                # generate conversation name
                try:
                    name = LLMGenerator.generate_conversation_name(app_model.tenant_id, query)
                    conversation.name = name
                except:
                    pass

                db.session.merge(conversation)
                db.session.commit()
                db.session.close()

    def _handle_annotation_reply(self, event: QueueAnnotationReplyEvent) -> Optional[MessageAnnotation]:
        """
        处理注解回复事件。
        :param event: 事件对象，包含注解回复的信息。
        :return: 返回处理得到的注解对象，如果没有找到对应的注解则返回 None。
        """
        # 根据事件中的注解ID获取注解对象
        annotation = AppAnnotationService.get_annotation_by_id(event.message_annotation_id)
        if annotation:
            # 如果找到注解，则将注解信息更新到任务状态的元数据中
            account = annotation.account
            self._task_state.metadata['annotation_reply'] = {
                'id': annotation.id,
                'account': {
                    'id': annotation.account_id,
                    'name': account.name if account else 'Dify user'
                }
            }

            return annotation

        return None

    def _handle_retriever_resources(self, event: QueueRetrieverResourcesEvent) -> None:
        """
        处理检索资源事件。
        :param event: 事件对象，包含检索资源的信息。
        """
        if self._application_generate_entity.app_config.additional_features.show_retrieve_source:
            self._task_state.metadata['retriever_resources'] = event.retriever_resources

    def _get_response_metadata(self) -> dict:
        """
        根据调用来源获取响应元数据。
        :return: 返回一个字典，包含响应中需要携带的元数据信息。
        """
        metadata = {}

        # 如果任务状态中包含检索资源信息，则将其添加到响应元数据中
        if 'retriever_resources' in self._task_state.metadata:
            metadata['retriever_resources'] = self._task_state.metadata['retriever_resources']

        # 如果任务状态中包含注解回复信息，则将其添加到响应元数据中
        if 'annotation_reply' in self._task_state.metadata:
            metadata['annotation_reply'] = self._task_state.metadata['annotation_reply']

        # 如果调用来源为调试器或服务API，则将使用信息添加到响应元数据中
        if self._application_generate_entity.invoke_from in [InvokeFrom.DEBUGGER, InvokeFrom.SERVICE_API]:
            metadata['usage'] = self._task_state.metadata['usage']

        return metadata
    def _message_file_to_stream_response(self, event: QueueMessageFileEvent) -> Optional[MessageFileStreamResponse]:
        """
        将消息文件转换为流式响应。
        :param event: 事件对象，包含消息文件的详细信息
        :return: 返回消息流式响应对象，如果找不到对应的消息文件则返回None
        """
        # 从数据库中查询对应的消息文件
        message_file: MessageFile = (
            db.session.query(MessageFile)
            .filter(MessageFile.id == event.message_file_id)
            .first()
        )

        if message_file:
            # 提取工具文件ID
            tool_file_id = message_file.url.split('/')[-1]
            # 去除扩展名
            tool_file_id = tool_file_id.split('.')[0]

            # 获取扩展名
            if '.' in message_file.url:
                extension = f'.{message_file.url.split(".")[-1]}'
                if len(extension) > 10:
                    extension = '.bin'
            else:
                extension = '.bin'
            # 为文件生成签名URL
            url = ToolFileManager.sign_file(tool_file_id=tool_file_id, extension=extension)

            # 构建并返回消息流式响应对象
            return MessageFileStreamResponse(
                task_id=self._application_generate_entity.task_id,
                id=message_file.id,
                type=message_file.type,
                belongs_to=message_file.belongs_to or 'user',
                url=url
            )

        return None

    def _message_to_stream_response(self, answer: str, message_id: str) -> MessageStreamResponse:
        """
        将消息转换为流式响应。
        :param answer: 回复的内容
        :param message_id: 消息的ID
        :return: 返回消息流式响应对象
        """
        # 构建并返回消息流式响应对象
        return MessageStreamResponse(
            task_id=self._application_generate_entity.task_id,
            id=message_id,
            answer=answer
        )

    def _message_replace_to_stream_response(self, answer: str) -> MessageReplaceStreamResponse:
        """
        将消息替换转换为流式响应。
        :param answer: 要替换为的答案内容
        :return: 返回消息替换流式响应对象
        """
        # 构建并返回消息替换流式响应对象
        return MessageReplaceStreamResponse(
            task_id=self._application_generate_entity.task_id,
            answer=answer
        )