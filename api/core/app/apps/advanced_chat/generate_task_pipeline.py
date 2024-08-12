import json
import logging
import time
from collections.abc import Generator
from typing import Any, Optional, Union, cast

from constants.tts_auto_play_timeout import TTS_AUTO_PLAY_TIMEOUT, TTS_AUTO_PLAY_YIELD_CPU_TIME
from core.app.apps.advanced_chat.app_generator_tts_publisher import AppGeneratorTTSPublisher, AudioTrunk
from core.app.apps.base_app_queue_manager import AppQueueManager, PublishFrom
from core.app.entities.app_invoke_entities import (
    AdvancedChatAppGenerateEntity,
)
from core.app.entities.queue_entities import (
    QueueAdvancedChatMessageEndEvent,
    QueueAnnotationReplyEvent,
    QueueErrorEvent,
    QueueIterationCompletedEvent,
    QueueIterationNextEvent,
    QueueIterationStartEvent,
    QueueMessageReplaceEvent,
    QueueNodeFailedEvent,
    QueueNodeStartedEvent,
    QueueNodeSucceededEvent,
    QueuePingEvent,
    QueueRetrieverResourcesEvent,
    QueueStopEvent,
    QueueTextChunkEvent,
    QueueWorkflowFailedEvent,
    QueueWorkflowStartedEvent,
    QueueWorkflowSucceededEvent,
)
from core.app.entities.task_entities import (
    AdvancedChatTaskState,
    ChatbotAppBlockingResponse,
    ChatbotAppStreamResponse,
    ChatflowStreamGenerateRoute,
    ErrorStreamResponse,
    MessageAudioEndStreamResponse,
    MessageAudioStreamResponse,
    MessageEndStreamResponse,
    StreamResponse,
)
from core.app.task_pipeline.based_generate_task_pipeline import BasedGenerateTaskPipeline
from core.app.task_pipeline.message_cycle_manage import MessageCycleManage
from core.app.task_pipeline.workflow_cycle_manage import WorkflowCycleManage
from core.file.file_obj import FileVar
from core.model_runtime.entities.llm_entities import LLMUsage
from core.model_runtime.utils.encoders import jsonable_encoder
from core.ops.ops_trace_manager import TraceQueueManager
from core.workflow.entities.node_entities import NodeType, SystemVariable
from core.workflow.nodes.answer.answer_node import AnswerNode
from core.workflow.nodes.answer.entities import TextGenerateRouteChunk, VarGenerateRouteChunk
from events.message_event import message_was_created
from extensions.ext_database import db
from models.account import Account
from models.model import Conversation, EndUser, Message
from models.workflow import (
    Workflow,
    WorkflowNodeExecution,
    WorkflowRunStatus,
)

logger = logging.getLogger(__name__)


class AdvancedChatAppGenerateTaskPipeline(BasedGenerateTaskPipeline, WorkflowCycleManage, MessageCycleManage):
    """
    AdvancedChatAppGenerateTaskPipeline 类负责为应用生成流式输出和状态管理。
    """
    _task_state: AdvancedChatTaskState
    _application_generate_entity: AdvancedChatAppGenerateEntity
    _workflow: Workflow
    _user: Union[Account, EndUser]
    _workflow_system_variables: dict[SystemVariable, Any]
    _iteration_nested_relations: dict[str, list[str]]

    def __init__(
            self, application_generate_entity: AdvancedChatAppGenerateEntity,
            workflow: Workflow,
            queue_manager: AppQueueManager,
            conversation: Conversation,
            message: Message,
            user: Union[Account, EndUser],
            stream: bool
    ) -> None:
        """
        初始化 AdvancedChatAppGenerateTaskPipeline。
        :param application_generate_entity: 应用生成实体，包含生成任务所需的基本信息。
        :param workflow: 工作流，定义了任务处理的流程。
        :param queue_manager: 队列管理器，用于管理任务队列。
        :param conversation: 会话，标识了当前的会话上下文。
        :param message: 消息，包含了用户输入的消息内容。
        :param user: 用户，执行任务的用户。
        :param stream: 流式标志，指示是否开启流式生成。
        """
        super().__init__(application_generate_entity, queue_manager, user, stream)

        if isinstance(self._user, EndUser):
            user_id = self._user.session_id
        else:
            user_id = self._user.id

        self._workflow = workflow
        self._conversation = conversation
        self._message = message
        # 初始化工作流系统变量，如查询内容、文件和会话ID
        self._workflow_system_variables = {
            SystemVariable.QUERY: message.query,
            SystemVariable.FILES: application_generate_entity.files,
            SystemVariable.CONVERSATION_ID: conversation.id,
            SystemVariable.USER_ID: user_id
        }

        # 初始化任务状态
        self._task_state = AdvancedChatTaskState(
            usage=LLMUsage.empty_usage()
        )

        self._iteration_nested_relations = self._get_iteration_nested_relations(self._workflow.graph_dict)
        self._stream_generate_routes = self._get_stream_generate_routes()
        self._conversation_name_generate_thread = None

    def process(self):
        """
        处理生成任务流水线。
        
        :return: 返回聊天机器人应用的响应，可能是阻塞响应（ChatbotAppBlockingResponse），
                 也可能是流式响应（Generator[ChatbotAppStreamResponse, None, None]）。
        """
        # 刷新工作流和用户信息的数据库会话，并关闭数据库会话
        db.session.refresh(self._workflow)
        db.session.refresh(self._user)
        db.session.close()

        # start generate conversation name thread
        self._conversation_name_generate_thread = self._generate_conversation_name(
            self._conversation,
            self._application_generate_entity.query
        )

        generator = self._wrapper_process_stream_response(
            trace_manager=self._application_generate_entity.trace_manager
        )
        if self._stream:
            # 如果设置为流式响应，则转换并返回流式响应
            return self._to_stream_response(generator)
        else:
            # 否则，转换并返回阻塞响应
            return self._to_blocking_response(generator)

    def _to_blocking_response(self, generator: Generator[StreamResponse, None, None]) -> ChatbotAppBlockingResponse:
        """
        处理阻塞响应。
        :param generator: 一个生成器，产生StreamResponse类型的对象。
        :return: 返回一个ChatbotAppBlockingResponse对象。
        """
        for stream_response in generator:
            if isinstance(stream_response, ErrorStreamResponse):
                # 如果遇到错误响应，抛出错误
                raise stream_response.err
            elif isinstance(stream_response, MessageEndStreamResponse):
                # 如果遇到消息结束响应，构造并返回ChatbotAppBlockingResponse对象
                extras = {}  # 用于存放额外信息的字典
                if stream_response.metadata:
                    extras['metadata'] = stream_response.metadata

                return ChatbotAppBlockingResponse(
                    task_id=stream_response.task_id,
                    data=ChatbotAppBlockingResponse.Data(
                        id=self._message.id,
                        mode=self._conversation.mode,
                        conversation_id=self._conversation.id,
                        message_id=self._message.id,
                        answer=self._task_state.answer,
                        created_at=int(self._message.created_at.timestamp()),
                        **extras
                    )
                )
            else:
                # 如果是其他类型的响应，继续迭代下一个
                continue

        # 如果生成器提前终止，抛出异常
        raise Exception('Queue listening stopped unexpectedly.')

    def _to_stream_response(self, generator: Generator[StreamResponse, None, None]) -> Generator[ChatbotAppStreamResponse, Any, None]:
        """
        将生成器中的流响应转换为特定的ChatbotAppStreamResponse格式。
        
        :param generator: 一个生成器，产生StreamResponse类型的对象。
        :return: 一个生成器，产生ChatbotAppStreamResponse类型的对象，包含了会话ID、消息ID和创建时间等额外信息。
        """
        for stream_response in generator:
            # 为每个流响应生成并yield一个包装后的ChatbotAppStreamResponse对象
            yield ChatbotAppStreamResponse(
                conversation_id=self._conversation.id,
                message_id=self._message.id,
                created_at=int(self._message.created_at.timestamp()),
                stream_response=stream_response
            )

    def _listenAudioMsg(self, publisher, task_id: str):
        if not publisher:
            return None
        audio_msg: AudioTrunk = publisher.checkAndGetAudio()
        if audio_msg and audio_msg.status != "finish":
            return MessageAudioStreamResponse(audio=audio_msg.audio, task_id=task_id)
        return None

    def _wrapper_process_stream_response(self, trace_manager: Optional[TraceQueueManager] = None) -> \
            Generator[StreamResponse, None, None]:

        publisher = None
        task_id = self._application_generate_entity.task_id
        tenant_id = self._application_generate_entity.app_config.tenant_id
        features_dict = self._workflow.features_dict

        if features_dict.get('text_to_speech') and features_dict['text_to_speech'].get('enabled') and features_dict[
                'text_to_speech'].get('autoPlay') == 'enabled':
            publisher = AppGeneratorTTSPublisher(tenant_id, features_dict['text_to_speech'].get('voice'))
        for response in self._process_stream_response(publisher=publisher, trace_manager=trace_manager):
            while True:
                audio_response = self._listenAudioMsg(publisher, task_id=task_id)
                if audio_response:
                    yield audio_response
                else:
                    break
            yield response

        start_listener_time = time.time()
        # timeout
        while (time.time() - start_listener_time) < TTS_AUTO_PLAY_TIMEOUT:
            try:
                if not publisher:
                    break
                audio_trunk = publisher.checkAndGetAudio()
                if audio_trunk is None:
                    # release cpu
                    # sleep 20 ms ( 40ms => 1280 byte audio file,20ms => 640 byte audio file)
                    time.sleep(TTS_AUTO_PLAY_YIELD_CPU_TIME)
                    continue
                if audio_trunk.status == "finish":
                    break
                else:
                    start_listener_time = time.time()
                    yield MessageAudioStreamResponse(audio=audio_trunk.audio, task_id=task_id)
            except Exception as e:
                logger.error(e)
                break
        yield MessageAudioEndStreamResponse(audio='', task_id=task_id)

    def _process_stream_response(
            self,
            publisher: AppGeneratorTTSPublisher,
            trace_manager: Optional[TraceQueueManager] = None
    ) -> Generator[StreamResponse, None, None]:
        """
        处理流式响应。
        :return: 生成器，返回流式响应对象
        """
        for message in self._queue_manager.listen():
            if (message.event
                    and hasattr(message.event, 'metadata')
                    and message.event.metadata
                    and message.event.metadata.get('is_answer_previous_node', False)
                    and publisher):
                publisher.publish(message=message)
            elif (hasattr(message.event, 'execution_metadata')
                  and message.event.execution_metadata
                  and message.event.execution_metadata.get('is_answer_previous_node', False)
                  and publisher):
                publisher.publish(message=message)
            event = message.event

            # 处理队列错误事件
            if isinstance(event, QueueErrorEvent):
                err = self._handle_error(event, self._message)
                yield self._error_to_stream_response(err)
                break
            # 处理工作流开始事件
            elif isinstance(event, QueueWorkflowStartedEvent):
                workflow_run = self._handle_workflow_start()

                # 更新数据库中的消息对象，设置工作流运行ID
                self._message = db.session.query(Message).filter(Message.id == self._message.id).first()
                self._message.workflow_run_id = workflow_run.id

                db.session.commit()
                db.session.refresh(self._message)
                db.session.close()

                yield self._workflow_start_to_stream_response(
                    task_id=self._application_generate_entity.task_id,
                    workflow_run=workflow_run
                )
            # 处理节点开始事件
            elif isinstance(event, QueueNodeStartedEvent):
                workflow_node_execution = self._handle_node_start(event)

                # 如果节点是流生成的起点，则更新当前流生成状态
                if not self._task_state.current_stream_generate_state and event.node_id in self._stream_generate_routes:
                    self._task_state.current_stream_generate_state = self._stream_generate_routes[event.node_id]
                    # reset current route position to 0
                    self._task_state.current_stream_generate_state.current_route_position = 0

                    # 节点开始时生成流输出
                    yield from self._generate_stream_outputs_when_node_started()

                yield self._workflow_node_start_to_stream_response(
                    event=event,
                    task_id=self._application_generate_entity.task_id,
                    workflow_node_execution=workflow_node_execution
                )
            # 处理节点成功或失败事件
            elif isinstance(event, QueueNodeSucceededEvent | QueueNodeFailedEvent):
                workflow_node_execution = self._handle_node_finished(event)

                # 节点结束时生成流输出
                generator = self._generate_stream_outputs_when_node_finished()
                if generator:
                    yield from generator

                yield self._workflow_node_finish_to_stream_response(
                    task_id=self._application_generate_entity.task_id,
                    workflow_node_execution=workflow_node_execution
                )

                if isinstance(event, QueueNodeFailedEvent):
                    yield from self._handle_iteration_exception(
                        task_id=self._application_generate_entity.task_id,
                        error=f'Child node failed: {event.error}'
                    )
            elif isinstance(event, QueueIterationStartEvent | QueueIterationNextEvent | QueueIterationCompletedEvent):
                if isinstance(event, QueueIterationNextEvent):
                    # clear ran node execution infos of current iteration
                    iteration_relations = self._iteration_nested_relations.get(event.node_id)
                    if iteration_relations:
                        for node_id in iteration_relations:
                            self._task_state.ran_node_execution_infos.pop(node_id, None)

                yield self._handle_iteration_to_stream_response(self._application_generate_entity.task_id, event)
                self._handle_iteration_operation(event)
            elif isinstance(event, QueueStopEvent | QueueWorkflowSucceededEvent | QueueWorkflowFailedEvent):
                workflow_run = self._handle_workflow_finished(
                    event, conversation_id=self._conversation.id, trace_manager=trace_manager
                )
                if workflow_run:
                    yield self._workflow_finish_to_stream_response(
                        task_id=self._application_generate_entity.task_id,
                        workflow_run=workflow_run
                    )

                    # 如果工作流失败，则生成错误响应
                    if workflow_run.status == WorkflowRunStatus.FAILED.value:
                        err_event = QueueErrorEvent(error=ValueError(f'Run failed: {workflow_run.error}'))
                        yield self._error_to_stream_response(self._handle_error(err_event, self._message))
                        break

                # 如果是停止事件，则保存消息并生成消息结束响应
                if isinstance(event, QueueStopEvent):
                    self._save_message()

                    yield self._message_end_to_stream_response()
                    break
                else:
                    self._queue_manager.publish(
                        QueueAdvancedChatMessageEndEvent(),
                        PublishFrom.TASK_PIPELINE
                    )
            # 处理输出审核结束事件
            elif isinstance(event, QueueAdvancedChatMessageEndEvent):
                output_moderation_answer = self._handle_output_moderation_when_task_finished(self._task_state.answer)
                if output_moderation_answer:
                    self._task_state.answer = output_moderation_answer
                    yield self._message_replace_to_stream_response(answer=output_moderation_answer)

                # 保存消息并生成消息结束响应
                self._save_message()

                yield self._message_end_to_stream_response()
            # 处理检索资源事件
            elif isinstance(event, QueueRetrieverResourcesEvent):
                self._handle_retriever_resources(event)
            # 处理注解回复事件
            elif isinstance(event, QueueAnnotationReplyEvent):
                self._handle_annotation_reply(event)
            elif isinstance(event, QueueTextChunkEvent):
                delta_text = event.text
                if delta_text is None:
                    continue

                # 如果不支持流式输出，则跳过
                if not self._is_stream_out_support(
                        event=event
                ):
                    continue

                # 处理输出审核片段
                should_direct_answer = self._handle_output_moderation_chunk(delta_text)
                if should_direct_answer:
                    continue

                self._task_state.answer += delta_text
                yield self._message_to_stream_response(delta_text, self._message.id)
            # 处理消息替换事件
            elif isinstance(event, QueueMessageReplaceEvent):
                yield self._message_replace_to_stream_response(answer=event.text)
            # 处理心跳事件
            elif isinstance(event, QueuePingEvent):
                yield self._ping_stream_response()
            else:
                continue
        if publisher:
            publisher.publish(None)
        if self._conversation_name_generate_thread:
            self._conversation_name_generate_thread.join()

    def _save_message(self) -> None:
        """
        保存消息。
        :return: 无返回值
        """
        # 从数据库中查询当前消息对象
        self._message = db.session.query(Message).filter(Message.id == self._message.id).first()

        # 更新消息内容和响应延迟时间
        self._message.answer = self._task_state.answer
        self._message.provider_response_latency = time.perf_counter() - self._start_at
        # 更新消息元数据，如果存在
        self._message.message_metadata = json.dumps(jsonable_encoder(self._task_state.metadata)) \
            if self._task_state.metadata else None

        # 如果存在使用情况 metadata，则更新消息和回答的令牌数量、单位价格、总价格等
        if self._task_state.metadata and self._task_state.metadata.get('usage'):
            usage = LLMUsage(**self._task_state.metadata['usage'])

            self._message.message_tokens = usage.prompt_tokens
            self._message.message_unit_price = usage.prompt_unit_price
            self._message.message_price_unit = usage.prompt_price_unit
            self._message.answer_tokens = usage.completion_tokens
            self._message.answer_unit_price = usage.completion_unit_price
            self._message.answer_price_unit = usage.completion_price_unit
            self._message.total_price = usage.total_price
            self._message.currency = usage.currency

        # 提交数据库会话，保存更改
        db.session.commit()

        # 发送消息创建事件
        message_was_created.send(
            self._message,
            application_generate_entity=self._application_generate_entity,
            conversation=self._conversation,
            is_first_message=self._application_generate_entity.conversation_id is None,
            extras=self._application_generate_entity.extras
        )

    def _message_end_to_stream_response(self) -> MessageEndStreamResponse:
        """
        将消息结束转换为流响应。
        
        该函数不接受任何参数。
        
        :return: 返回一个MessageEndStreamResponse实例，包含任务ID、消息ID和可能的元数据。
        """
        # 准备额外信息字典，用于存放可能的元数据
        extras = {}
        # 如果任务状态中包含元数据，则将其添加到额外信息中
        if self._task_state.metadata:
            extras['metadata'] = self._task_state.metadata

        # 构造并返回一个MessageEndStreamResponse实例，包含任务ID、消息ID和额外信息
        return MessageEndStreamResponse(
            task_id=self._application_generate_entity.task_id,
            id=self._message.id,
            **extras
        )

    def _get_stream_generate_routes(self) -> dict[str, ChatflowStreamGenerateRoute]:
        """
        获取流生成路由。
        :return: 返回一个字典，键为起始节点ID，值为StreamGenerateRoute对象，该对象包含答案节点ID和生成路由信息。
        """
        # 查找所有答案节点
        graph = self._workflow.graph_dict
        answer_node_configs = [
            node for node in graph['nodes']
            if node.get('data', {}).get('type') == NodeType.ANSWER.value
        ]

        # 解析答案节点的流输出节点值选择器
        stream_generate_routes = {}
        for node_config in answer_node_configs:
            # 为流输出获取生成路由
            answer_node_id = node_config['id']
            generate_route = AnswerNode.extract_generate_route_selectors(node_config)
            start_node_ids = self._get_answer_start_at_node_ids(graph, answer_node_id)
            if not start_node_ids:
                continue

            for start_node_id in start_node_ids:
                stream_generate_routes[start_node_id] = ChatflowStreamGenerateRoute(
                    answer_node_id=answer_node_id,
                    generate_route=generate_route
                )

        return stream_generate_routes

    def _get_answer_start_at_node_ids(self, graph: dict, target_node_id: str) \
            -> list[str]:
        """
        获取从特定节点开始的答案路径的起始节点ID列表。
        :param graph: 表示图结构的数据字典，包含节点和边的信息。
        :param target_node_id: 目标节点ID，函数将从该节点开始回溯寻找答案路径的起始节点。
        :return: 包含所有答案路径起始节点ID的列表。如果没有找到答案路径起始节点，则返回空列表。
        """
        nodes = graph.get('nodes')  # 获取图中的节点列表
        edges = graph.get('edges')  # 获取图中的边列表

        # 从目标节点收集所有指向它的入边
        ingoing_edges = []
        for edge in edges:
            if edge.get('target') == target_node_id:
                ingoing_edges.append(edge)

        if not ingoing_edges:
            # check if it's the first node in the iteration
            target_node = next((node for node in nodes if node.get('id') == target_node_id), None)
            if not target_node:
                return []

            node_iteration_id = target_node.get('data', {}).get('iteration_id')
            # get iteration start node id
            for node in nodes:
                if node.get('id') == node_iteration_id:
                    if node.get('data', {}).get('start_node_id') == target_node_id:
                        return [target_node_id]

            return []

        start_node_ids = []
        for ingoing_edge in ingoing_edges:
            source_node_id = ingoing_edge.get('source')
            source_node = next((node for node in nodes if node.get('id') == source_node_id), None)
            if not source_node:
                continue  # 如果找不到源节点，则跳过当前入边

            node_type = source_node.get('data', {}).get('type')
            node_iteration_id = source_node.get('data', {}).get('iteration_id')
            iteration_start_node_id = None
            if node_iteration_id:
                iteration_node = next((node for node in nodes if node.get('id') == node_iteration_id), None)
                iteration_start_node_id = iteration_node.get('data', {}).get('start_node_id')

            if node_type in [
                NodeType.ANSWER.value,
                NodeType.IF_ELSE.value,
                NodeType.QUESTION_CLASSIFIER.value,
                NodeType.ITERATION.value,
                NodeType.LOOP.value
            ]:
                start_node_id = target_node_id
                start_node_ids.append(start_node_id)
            elif node_type == NodeType.START.value or \
                    node_iteration_id is not None and iteration_start_node_id == source_node.get('id'):
                start_node_id = source_node_id
                start_node_ids.append(start_node_id)
            else:
                # 递归寻找当前节点上游的起始节点，并将其加入列表
                sub_start_node_ids = self._get_answer_start_at_node_ids(graph, source_node_id)
                if sub_start_node_ids:
                    start_node_ids.extend(sub_start_node_ids)

        return start_node_ids

    def _get_iteration_nested_relations(self, graph: dict) -> dict[str, list[str]]:
        """
        Get iteration nested relations.
        :param graph: graph
        :return:
        """
        nodes = graph.get('nodes')

        iteration_ids = [node.get('id') for node in nodes
                         if node.get('data', {}).get('type') in [
                             NodeType.ITERATION.value,
                             NodeType.LOOP.value,
                         ]]

        return {
            iteration_id: [
                node.get('id') for node in nodes if node.get('data', {}).get('iteration_id') == iteration_id
            ] for iteration_id in iteration_ids
        }

    def _generate_stream_outputs_when_node_started(self) -> Generator:
        """
        当节点启动时生成流输出。
        
        :return: 一个生成器，用于逐个产生流的输出。
        """
        # 检查当前是否处于流生成状态
        if self._task_state.current_stream_generate_state:
            # 获取当前路由位置之后的所有路由块
            route_chunks = self._task_state.current_stream_generate_state.generate_route[
                           self._task_state.current_stream_generate_state.current_route_position:
                           ]

            for route_chunk in route_chunks:
                # 处理文本类型的路由块
                if route_chunk.type == 'text':
                    route_chunk = cast(TextGenerateRouteChunk, route_chunk)

                    # handle output moderation chunk
                    should_direct_answer = self._handle_output_moderation_chunk(route_chunk.text)
                    if should_direct_answer:
                        continue

                    self._task_state.answer += route_chunk.text
                    yield self._message_to_stream_response(route_chunk.text, self._message.id)
                else:
                    break  # 如果遇到非文本类型的路由块，终止循环

                # 更新当前路由位置，准备处理下一个路由块
                self._task_state.current_stream_generate_state.current_route_position += 1

            # 如果所有路由块都已处理完毕，则重置当前流生成状态
            if self._task_state.current_stream_generate_state.current_route_position == len(
                    self._task_state.current_stream_generate_state.generate_route
            ):
                self._task_state.current_stream_generate_state = None

    def _generate_stream_outputs_when_node_finished(self) -> Optional[Generator]:
        """
        生成流式输出。
        :return: 返回一个生成器，用于逐个生成流式输出的消息。
        """
        # 如果当前没有流生成状态，则直接返回None
        if not self._task_state.current_stream_generate_state:
            return

        # 获取当前路由位置之后的所有路由块
        route_chunks = self._task_state.current_stream_generate_state.generate_route[
                       self._task_state.current_stream_generate_state.current_route_position:]

        for route_chunk in route_chunks:
            # 处理文本类型的路由块
            if route_chunk.type == 'text':
                route_chunk = cast(TextGenerateRouteChunk, route_chunk)
                self._task_state.answer += route_chunk.text
                yield self._message_to_stream_response(route_chunk.text, self._message.id)
            else:
                value = None
                route_chunk = cast(VarGenerateRouteChunk, route_chunk)
                value_selector = route_chunk.value_selector
                # 如果没有值选择器，则跳过当前路由块，继续处理下一个
                if not value_selector:
                    self._task_state.current_stream_generate_state.current_route_position += 1
                    continue

                route_chunk_node_id = value_selector[0]

                # 根据路由块节点ID获取值
                if route_chunk_node_id == 'sys':
                    # 系统变量
                    value = self._workflow_system_variables.get(SystemVariable.value_of(value_selector[1]))
                elif route_chunk_node_id in self._iteration_nested_relations:
                    # it's a iteration variable
                    if not self._iteration_state or route_chunk_node_id not in self._iteration_state.current_iterations:
                        continue
                    iteration_state = self._iteration_state.current_iterations[route_chunk_node_id]
                    iterator = iteration_state.inputs
                    if not iterator:
                        continue
                    iterator_selector = iterator.get('iterator_selector', [])
                    if value_selector[1] == 'index':
                        value = iteration_state.current_index
                    elif value_selector[1] == 'item':
                        value = iterator_selector[iteration_state.current_index] if iteration_state.current_index < len(
                            iterator_selector
                        ) else None
                else:
                    # 检查路由块节点ID是否在已执行的节点信息中
                    if route_chunk_node_id not in self._task_state.ran_node_execution_infos:
                        break

                    latest_node_execution_info = self._task_state.latest_node_execution_info

                    # 获取路由块节点的执行信息
                    route_chunk_node_execution_info = self._task_state.ran_node_execution_infos[route_chunk_node_id]
                    # 判断是否仅支持LLM类型的节点进行流式输出
                    if (route_chunk_node_execution_info.node_type == NodeType.LLM
                            and latest_node_execution_info.node_type == NodeType.LLM):
                        self._task_state.current_stream_generate_state.current_route_position += 1
                        continue

                    # 获取路由块节点的执行情况
                    route_chunk_node_execution = db.session.query(WorkflowNodeExecution).filter(
                        WorkflowNodeExecution.id == route_chunk_node_execution_info.workflow_node_execution_id
                    ).first()

                    outputs = route_chunk_node_execution.outputs_dict

                    # 从输出中获取值
                    value = None
                    for key in value_selector[1:]:
                        if not value:
                            value = outputs.get(key) if outputs else None
                        else:
                            value = value.get(key)

                if value is not None:
                    text = ''
                    if isinstance(value, str | int | float):
                        text = str(value)
                    elif isinstance(value, FileVar):
                        # 将文件变量转换为markdown格式
                        text = value.to_markdown()
                    elif isinstance(value, dict):
                        # 处理文件变量和其他类型
                        file_vars = self._fetch_files_from_variable_value(value)
                        if file_vars:
                            file_var = file_vars[0]
                            try:
                                file_var_obj = FileVar(**file_var)

                                # 转换文件为markdown格式
                                text = file_var_obj.to_markdown()
                            except Exception as e:
                                logger.error(f'Error creating file var: {e}')

                        if not text:
                            # 其他类型，转为JSON字符串
                            text = json.dumps(value, ensure_ascii=False)
                    elif isinstance(value, list):
                        # 处理文件变量和其他类型
                        file_vars = self._fetch_files_from_variable_value(value)
                        for file_var in file_vars:
                            try:
                                file_var_obj = FileVar(**file_var)
                            except Exception as e:
                                logger.error(f'Error creating file var: {e}')
                                continue

                            # 将文件变量转换为markdown格式
                            text = file_var_obj.to_markdown() + ' '

                        text = text.strip()

                        if not text and value:
                            # 其他类型，转为JSON字符串
                            text = json.dumps(value, ensure_ascii=False)

                    if text:
                        self._task_state.answer += text
                        yield self._message_to_stream_response(text, self._message.id)

            # 更新当前路由位置，准备处理下一个路由块
            self._task_state.current_stream_generate_state.current_route_position += 1

        # 所有路由块都处理完毕后，重置当前流生成状态
        if self._task_state.current_stream_generate_state.current_route_position == len(
                self._task_state.current_stream_generate_state.generate_route
        ):
            self._task_state.current_stream_generate_state = None

    def _is_stream_out_support(self, event: QueueTextChunkEvent) -> bool:
        """
        判断是否支持流式输出。
        :param event: 队列文本块事件，包含元数据信息，用于判断是否支持流式输出。
        :return: 布尔值，如果支持流式输出则返回 True，否则返回 False。
        """
        # 如果事件元数据不存在，认为支持流式输出
        if not event.metadata:
            return True

        # 如果元数据中没有 node_id 字段，也认为支持流式输出
        if 'node_id' not in event.metadata:
            return True

        # 从元数据中获取节点类型和值选择器
        node_type = event.metadata.get('node_type')
        stream_output_value_selector = event.metadata.get('value_selector')
        # 如果没有值选择器，则不支持流式输出
        if not stream_output_value_selector:
            return False

        # 如果当前没有流生成状态，则不支持流式输出
        if not self._task_state.current_stream_generate_state:
            return False

        # 获取当前路由位置的块
        route_chunk = self._task_state.current_stream_generate_state.generate_route[
            self._task_state.current_stream_generate_state.current_route_position]

        # 如果块类型不是 'var'，则不支持流式输出
        if route_chunk.type != 'var':
            return False

        # 只有 LLM 节点类型支持块流式输出
        if node_type != NodeType.LLM:
            return False

        # 断言 route_chunk 的类型，并获取值选择器
        route_chunk = cast(VarGenerateRouteChunk, route_chunk)
        value_selector = route_chunk.value_selector

        # 检查块的节点 ID 是否在当前节点 ID 之前或相等
        if value_selector != stream_output_value_selector:
            return False

        # 所有检查通过，支持流式输出
        return True

    def _handle_output_moderation_chunk(self, text: str) -> bool:
        """
        处理输出审查片段。
        :param text: 待审查的文本
        :return: 如果输出审查应该指导输出，则返回True，否则返回False
        """
        if self._output_moderation_handler:  # 如果存在输出审查处理器
            if self._output_moderation_handler.should_direct_output():
                # 当输出审查决定指导输出时，停止订阅新令牌
                self._task_state.answer = self._output_moderation_handler.get_final_output()
                # 向队列管理器发布最终输出文本
                self._queue_manager.publish(
                    QueueTextChunkEvent(
                        text=self._task_state.answer
                    ), PublishFrom.TASK_PIPELINE
                )

                # 向队列管理器发布停止事件，表示由于输出审查的原因停止处理
                self._queue_manager.publish(
                    QueueStopEvent(stopped_by=QueueStopEvent.StopBy.OUTPUT_MODERATION),
                    PublishFrom.TASK_PIPELINE
                )
                return True
            else:
                # 如果当前不需指导输出，则将文本追加到审查处理器中
                self._output_moderation_handler.append_new_token(text)

        return False
