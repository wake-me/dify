import json
import logging
import time
from collections.abc import Generator
from typing import Optional, Union, cast

from constants.tts_auto_play_timeout import TTS_AUTO_PLAY_TIMEOUT, TTS_AUTO_PLAY_YIELD_CPU_TIME
from core.app.apps.advanced_chat.app_generator_tts_publisher import AppGeneratorTTSPublisher, AudioTrunk
from core.app.apps.base_app_queue_manager import AppQueueManager, PublishFrom
from core.app.entities.app_invoke_entities import (
    AgentChatAppGenerateEntity,
    ChatAppGenerateEntity,
    CompletionAppGenerateEntity,
)
from core.app.entities.queue_entities import (
    QueueAgentMessageEvent,
    QueueAgentThoughtEvent,
    QueueAnnotationReplyEvent,
    QueueErrorEvent,
    QueueLLMChunkEvent,
    QueueMessageEndEvent,
    QueueMessageFileEvent,
    QueueMessageReplaceEvent,
    QueuePingEvent,
    QueueRetrieverResourcesEvent,
    QueueStopEvent,
)
from core.app.entities.task_entities import (
    AgentMessageStreamResponse,
    AgentThoughtStreamResponse,
    ChatbotAppBlockingResponse,
    ChatbotAppStreamResponse,
    CompletionAppBlockingResponse,
    CompletionAppStreamResponse,
    EasyUITaskState,
    ErrorStreamResponse,
    MessageAudioEndStreamResponse,
    MessageAudioStreamResponse,
    MessageEndStreamResponse,
    StreamResponse,
)
from core.app.task_pipeline.based_generate_task_pipeline import BasedGenerateTaskPipeline
from core.app.task_pipeline.message_cycle_manage import MessageCycleManage
from core.model_manager import ModelInstance
from core.model_runtime.entities.llm_entities import LLMResult, LLMResultChunk, LLMResultChunkDelta, LLMUsage
from core.model_runtime.entities.message_entities import (
    AssistantPromptMessage,
)
from core.model_runtime.model_providers.__base.large_language_model import LargeLanguageModel
from core.model_runtime.utils.encoders import jsonable_encoder
from core.ops.entities.trace_entity import TraceTaskName
from core.ops.ops_trace_manager import TraceQueueManager, TraceTask
from core.prompt.utils.prompt_message_util import PromptMessageUtil
from core.prompt.utils.prompt_template_parser import PromptTemplateParser
from events.message_event import message_was_created
from extensions.ext_database import db
from models.account import Account
from models.model import AppMode, Conversation, EndUser, Message, MessageAgentThought

logger = logging.getLogger(__name__)


class EasyUIBasedGenerateTaskPipeline(BasedGenerateTaskPipeline, MessageCycleManage):
    """
    EasyUIBasedGenerateTaskPipeline 是一个为应用程序生成流式输出和状态管理的类。
    """
    _task_state: EasyUITaskState  # 任务状态
    _application_generate_entity: Union[
        ChatAppGenerateEntity,
        CompletionAppGenerateEntity,
        AgentChatAppGenerateEntity
    ]  # 应用生成实体

    def __init__(self, application_generate_entity: Union[
        ChatAppGenerateEntity,
        CompletionAppGenerateEntity,
        AgentChatAppGenerateEntity
    ],
                 queue_manager: AppQueueManager,
                 conversation: Conversation,
                 message: Message,
                 user: Union[Account, EndUser],
                 stream: bool) -> None:
        """
        初始化 GenerateTaskPipeline。
        :param application_generate_entity: 应用生成实体
        :param queue_manager: 队列管理器
        :param conversation: 对话
        :param message: 消息
        :param user: 用户
        :param stream: 是否为流式
        """
        super().__init__(application_generate_entity, queue_manager, user, stream)
        self._model_config = application_generate_entity.model_conf
        self._app_config = application_generate_entity.app_config
        self._conversation = conversation
        self._message = message

        self._task_state = EasyUITaskState(
            llm_result=LLMResult(
                model=self._model_config.model,  # 模型
                prompt_messages=[],  # 提示消息列表
                message=AssistantPromptMessage(content=""),  # 助手回复消息
                usage=LLMUsage.empty_usage()  # 模型使用情况
            )
        )

        self._conversation_name_generate_thread = None

    def process(
            self,
    ) -> Union[
        ChatbotAppBlockingResponse,
        CompletionAppBlockingResponse,
        Generator[Union[ChatbotAppStreamResponse, CompletionAppStreamResponse], None, None]
    ]:
        """
        处理生成任务管道。
        :return: 根据是否为流式返回不同的响应类型
        """
        # 刷新数据库会话
        db.session.refresh(self._conversation)
        db.session.refresh(self._message)
        db.session.close()

        if self._application_generate_entity.app_config.app_mode != AppMode.COMPLETION:
            # start generate conversation name thread
            self._conversation_name_generate_thread = self._generate_conversation_name(
                self._conversation,
                self._application_generate_entity.query
            )

        generator = self._wrapper_process_stream_response(
            trace_manager=self._application_generate_entity.trace_manager
        )
        if self._stream:
            # 返回流式响应
            return self._to_stream_response(generator)
        else:
            # 返回阻塞式响应
            return self._to_blocking_response(generator)

    def _to_blocking_response(self, generator: Generator[StreamResponse, None, None]) -> Union[
        ChatbotAppBlockingResponse,
        CompletionAppBlockingResponse
    ]:
        """
        处理阻塞式响应。
        :param generator: 流式响应生成器
        :return: 阻塞式响应对象
        """
        for stream_response in generator:
            # 错误处理
            if isinstance(stream_response, ErrorStreamResponse):
                raise stream_response.err
            # 消息结束处理
            elif isinstance(stream_response, MessageEndStreamResponse):
                extras = {
                    'usage': jsonable_encoder(self._task_state.llm_result.usage)  # 使用情况
                }
                # 元数据存在时添加到额外信息中
                if self._task_state.metadata:
                    extras['metadata'] = self._task_state.metadata

                # 根据对话模式构造不同类型的响应
                if self._conversation.mode == AppMode.COMPLETION.value:
                    response = CompletionAppBlockingResponse(
                        task_id=self._application_generate_entity.task_id,
                        data=CompletionAppBlockingResponse.Data(
                            id=self._message.id,
                            mode=self._conversation.mode,
                            message_id=self._message.id,
                            answer=self._task_state.llm_result.message.content,  # 答案内容
                            created_at=int(self._message.created_at.timestamp()),
                            **extras
                        )
                    )
                else:
                    response = ChatbotAppBlockingResponse(
                        task_id=self._application_generate_entity.task_id,
                        data=ChatbotAppBlockingResponse.Data(
                            id=self._message.id,
                            mode=self._conversation.mode,
                            conversation_id=self._conversation.id,
                            message_id=self._message.id,
                            answer=self._task_state.llm_result.message.content,  # 答案内容
                            created_at=int(self._message.created_at.timestamp()),
                            **extras
                        )
                    )

                return response
            else:
                continue  # 继续处理下一条流式响应

        raise Exception('Queue listening stopped unexpectedly.')  # 队列监听意外停止异常

    def _to_stream_response(self, generator: Generator[StreamResponse, None, None]) \
            -> Generator[Union[ChatbotAppStreamResponse, CompletionAppStreamResponse], None, None]:
        """
        将生成器中的流响应转换为特定类型的响应对象。
        
        :param generator: 一个生成器，产生 StreamResponse 类型的响应。
        :return: 一个生成器，产生 ChatbotAppStreamResponse 或 CompletionAppStreamResponse 类型的响应，
                具体类型取决于应用的类型。
        """
        for stream_response in generator:
            # 根据当前应用的类型，决定生成哪种类型的响应对象
            if isinstance(self._application_generate_entity, CompletionAppGenerateEntity):
                # 如果是完成应用生成实体，则产生 CompletionAppStreamResponse 类型的响应
                yield CompletionAppStreamResponse(
                    message_id=self._message.id,
                    created_at=int(self._message.created_at.timestamp()),
                    stream_response=stream_response
                )
            else:
                # 否则，产生 ChatbotAppStreamResponse 类型的响应
                yield ChatbotAppStreamResponse(
                    conversation_id=self._conversation.id,
                    message_id=self._message.id,
                    created_at=int(self._message.created_at.timestamp()),
                    stream_response=stream_response
                )

    def _listenAudioMsg(self, publisher, task_id: str):
        if publisher is None:
            return None
        audio_msg: AudioTrunk = publisher.checkAndGetAudio()
        if audio_msg and audio_msg.status != "finish":
            # audio_str = audio_msg.audio.decode('utf-8', errors='ignore')
            return MessageAudioStreamResponse(audio=audio_msg.audio, task_id=task_id)
        return None

    def _wrapper_process_stream_response(self, trace_manager: Optional[TraceQueueManager] = None) -> \
            Generator[StreamResponse, None, None]:

        tenant_id = self._application_generate_entity.app_config.tenant_id
        task_id = self._application_generate_entity.task_id
        publisher = None
        text_to_speech_dict = self._app_config.app_model_config_dict.get('text_to_speech')
        if text_to_speech_dict and text_to_speech_dict.get('autoPlay') == 'enabled' and text_to_speech_dict.get('enabled'):
            publisher = AppGeneratorTTSPublisher(tenant_id, text_to_speech_dict.get('voice', None))
        for response in self._process_stream_response(publisher=publisher, trace_manager=trace_manager):
            while True:
                audio_response = self._listenAudioMsg(publisher, task_id)
                if audio_response:
                    yield audio_response
                else:
                    break
            yield response

        start_listener_time = time.time()
        # timeout
        while (time.time() - start_listener_time) < TTS_AUTO_PLAY_TIMEOUT:
            if publisher is None:
                break
            audio = publisher.checkAndGetAudio()
            if audio is None:
                # release cpu
                # sleep 20 ms ( 40ms => 1280 byte audio file,20ms => 640 byte audio file)
                time.sleep(TTS_AUTO_PLAY_YIELD_CPU_TIME)
                continue
            if audio.status == "finish":
                break
            else:
                start_listener_time = time.time()
                yield MessageAudioStreamResponse(audio=audio.audio,
                                                 task_id=task_id)
        yield MessageAudioEndStreamResponse(audio='', task_id=task_id)

    def _process_stream_response(
            self,
            publisher: AppGeneratorTTSPublisher,
            trace_manager: Optional[TraceQueueManager] = None
    ) -> Generator[StreamResponse, None, None]:
        """
        Process stream response.
        :return:
        """
        for message in self._queue_manager.listen():
            if publisher:
                publisher.publish(message)
            event = message.event

            # 错误处理
            if isinstance(event, QueueErrorEvent):
                err = self._handle_error(event, self._message)
                yield self._error_to_stream_response(err)
                break
            # 消息结束或停止处理
            elif isinstance(event, QueueStopEvent | QueueMessageEndEvent):
                if isinstance(event, QueueMessageEndEvent):
                    self._task_state.llm_result = event.llm_result
                else:
                    self._handle_stop(event)

                # 输出审核处理
                output_moderation_answer = self._handle_output_moderation_when_task_finished(
                    self._task_state.llm_result.message.content
                )
                if output_moderation_answer:
                    self._task_state.llm_result.message.content = output_moderation_answer
                    yield self._message_replace_to_stream_response(answer=output_moderation_answer)

                # Save message
                self._save_message(trace_manager)

                yield self._message_end_to_stream_response()
            # 检索资源事件处理
            elif isinstance(event, QueueRetrieverResourcesEvent):
                self._handle_retriever_resources(event)
            # 注释回复事件处理
            elif isinstance(event, QueueAnnotationReplyEvent):
                annotation = self._handle_annotation_reply(event)
                if annotation:
                    self._task_state.llm_result.message.content = annotation.content
            # 代理思考事件处理
            elif isinstance(event, QueueAgentThoughtEvent):
                yield self._agent_thought_to_stream_response(event)
            # 消息文件事件处理
            elif isinstance(event, QueueMessageFileEvent):
                response = self._message_file_to_stream_response(event)
                if response:
                    yield response
            # LLM数据块事件或代理消息事件处理
            elif isinstance(event, QueueLLMChunkEvent | QueueAgentMessageEvent):
                chunk = event.chunk
                delta_text = chunk.delta.message.content
                if delta_text is None:
                    continue

                if not self._task_state.llm_result.prompt_messages:
                    self._task_state.llm_result.prompt_messages = chunk.prompt_messages

                # 输出审核处理数据块
                should_direct_answer = self._handle_output_moderation_chunk(delta_text)
                if should_direct_answer:
                    continue

                self._task_state.llm_result.message.content += delta_text

                if isinstance(event, QueueLLMChunkEvent):
                    yield self._message_to_stream_response(delta_text, self._message.id)
                else:
                    yield self._agent_message_to_stream_response(delta_text, self._message.id)
            # 消息替换事件处理
            elif isinstance(event, QueueMessageReplaceEvent):
                yield self._message_replace_to_stream_response(answer=event.text)
            # Ping事件处理
            elif isinstance(event, QueuePingEvent):
                yield self._ping_stream_response()
            else:
                continue
        if publisher:
            publisher.publish(None)
        if self._conversation_name_generate_thread:
            self._conversation_name_generate_thread.join()

    def _save_message(
            self, trace_manager: Optional[TraceQueueManager] = None
    ) -> None:
        """
        保存消息。
        :return: 无返回值
        """
        # 获取当前任务状态中的LLM结果和使用情况
        llm_result = self._task_state.llm_result
        usage = llm_result.usage

        # 从数据库中更新当前消息和对话对象
        self._message = db.session.query(Message).filter(Message.id == self._message.id).first()
        self._conversation = db.session.query(Conversation).filter(Conversation.id == self._conversation.id).first()

        # 更新消息内容、令牌、价格等信息
        self._message.message = PromptMessageUtil.prompt_messages_to_prompt_for_saving(
            self._model_config.mode,
            self._task_state.llm_result.prompt_messages
        )
        self._message.message_tokens = usage.prompt_tokens
        self._message.message_unit_price = usage.prompt_unit_price
        self._message.message_price_unit = usage.prompt_price_unit
        # 如果有回答内容，则去除模板变量并保存
        self._message.answer = PromptTemplateParser.remove_template_variables(llm_result.message.content.strip()) \
            if llm_result.message.content else ''
        self._message.answer_tokens = usage.completion_tokens
        self._message.answer_unit_price = usage.completion_unit_price
        self._message.answer_price_unit = usage.completion_price_unit
        # 记录提供者响应延迟时间
        self._message.provider_response_latency = time.perf_counter() - self._start_at
        self._message.total_price = usage.total_price
        self._message.currency = usage.currency
        # 保存消息元数据
        self._message.message_metadata = json.dumps(jsonable_encoder(self._task_state.metadata)) \
            if self._task_state.metadata else None

        # 提交数据库事务
        db.session.commit()

        if trace_manager:
            trace_manager.add_trace_task(
                TraceTask(
                    TraceTaskName.MESSAGE_TRACE,
                    conversation_id=self._conversation.id,
                    message_id=self._message.id
                )
            )

        message_was_created.send(
            self._message,
            application_generate_entity=self._application_generate_entity,
            conversation=self._conversation,
            is_first_message=self._application_generate_entity.app_config.app_mode in [
                AppMode.AGENT_CHAT,
                AppMode.CHAT
            ] and self._application_generate_entity.conversation_id is None,
            extras=self._application_generate_entity.extras
        )

    def _handle_stop(self, event: QueueStopEvent) -> None:
        """
        处理停止操作。
        :param event: QueueStopEvent对象，包含停止事件的详细信息。
        :return: 无返回值
        """
        # 获取模型配置和实例化模型类型
        model_config = self._model_config
        model = model_config.model

        model_instance = ModelInstance(
            provider_model_bundle=model_config.provider_model_bundle,
            model=model_config.model
        )

        # 根据停止原因计算token数量
        prompt_tokens = 0
        if event.stopped_by != QueueStopEvent.StopBy.ANNOTATION_REPLY:
            prompt_tokens = model_instance.get_llm_num_tokens(
                self._task_state.llm_result.prompt_messages
            )

        completion_tokens = 0
        if event.stopped_by == QueueStopEvent.StopBy.USER_MANUAL:
            completion_tokens = model_instance.get_llm_num_tokens(
                [self._task_state.llm_result.message]
            )

        credentials = model_config.credentials

        # transform usage
        model_type_instance = model_config.provider_model_bundle.model_type_instance
        model_type_instance = cast(LargeLanguageModel, model_type_instance)
        self._task_state.llm_result.usage = model_type_instance._calc_response_usage(
            model,
            credentials,
            prompt_tokens,
            completion_tokens
        )

    def _message_end_to_stream_response(self) -> MessageEndStreamResponse:
        """
        将消息结束转换为流响应。
        
        该函数不接受任何参数。
        
        :return: 返回一个MessageEndStreamResponse实例，包含任务ID、消息ID和可能的元数据。
        """
        # 更新任务状态中的使用情况信息
        self._task_state.metadata['usage'] = jsonable_encoder(self._task_state.llm_result.usage)

        # 准备额外信息，如果有元数据则添加到额外信息中
        extras = {}
        if self._task_state.metadata:
            extras['metadata'] = self._task_state.metadata

        # 构造并返回流响应消息
        return MessageEndStreamResponse(
            task_id=self._application_generate_entity.task_id,
            id=self._message.id,
            **extras
        )

    def _agent_message_to_stream_response(self, answer: str, message_id: str) -> AgentMessageStreamResponse:
        """
        将代理消息转换为流式响应。
        
        :param answer: 回答的内容
        :param message_id: 消息的唯一标识符
        :return: 返回一个AgentMessageStreamResponse对象，包含任务ID、消息ID和回答内容
        """
        # 创建并返回一个AgentMessageStreamResponse对象
        return AgentMessageStreamResponse(
            task_id=self._application_generate_entity.task_id,
            id=message_id,
            answer=answer
        )

    def _agent_thought_to_stream_response(self, event: QueueAgentThoughtEvent) -> Optional[AgentThoughtStreamResponse]:
        """
        将代理思考转换为流式响应。
        :param event: 代理思考事件，包含需要查询的代理思考的ID。
        :return: 返回一个包含代理思考详细信息的流式响应对象，如果没有找到对应的代理思考，则返回None。
        """
        # 从数据库中查询指定ID的代理思考信息
        agent_thought: MessageAgentThought = (
            db.session.query(MessageAgentThought)
            .filter(MessageAgentThought.id == event.agent_thought_id)
            .first()
        )
        # 刷新数据库会话，确保获取的数据是最新的
        db.session.refresh(agent_thought)
        # 关闭数据库会话
        db.session.close()

        # 如果找到了指定的代理思考，则创建并返回一个流式响应对象
        if agent_thought:
            return AgentThoughtStreamResponse(
                task_id=self._application_generate_entity.task_id,
                id=agent_thought.id,
                position=agent_thought.position,
                thought=agent_thought.thought,
                observation=agent_thought.observation,
                tool=agent_thought.tool,
                tool_labels=agent_thought.tool_labels,
                tool_input=agent_thought.tool_input,
                message_files=agent_thought.files
            )

        # 如果没有找到指定的代理思考，则返回None
        return None

    def _handle_output_moderation_chunk(self, text: str) -> bool:
        """
        处理输出审查片段。
        :param text: 待审查的文本
        :return: 如果输出审查应该指导输出，则返回True，否则返回False
        """
        if self._output_moderation_handler:
            # 如果存在输出审查处理器，并且应该指导输出
            if self._output_moderation_handler.should_direct_output():
                # 在输出审查应该指导输出时，停止订阅新token，并发布LLM结果和停止事件
                self._task_state.llm_result.message.content = self._output_moderation_handler.get_final_output()
                self._queue_manager.publish(
                    QueueLLMChunkEvent(
                        chunk=LLMResultChunk(
                            model=self._task_state.llm_result.model,
                            prompt_messages=self._task_state.llm_result.prompt_messages,
                            delta=LLMResultChunkDelta(
                                index=0,
                                message=AssistantPromptMessage(content=self._task_state.llm_result.message.content)
                            )
                        )
                    ), PublishFrom.TASK_PIPELINE
                )

                self._queue_manager.publish(
                    QueueStopEvent(stopped_by=QueueStopEvent.StopBy.OUTPUT_MODERATION),
                    PublishFrom.TASK_PIPELINE
                )
                return True
            else:
                # 如果不应该指导输出，则将文本追加到新token列表中
                self._output_moderation_handler.append_new_token(text)

        return False
