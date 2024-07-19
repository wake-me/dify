import logging
from typing import cast

from core.app.apps.base_app_queue_manager import AppQueueManager, PublishFrom
from core.app.apps.base_app_runner import AppRunner
from core.app.apps.chat.app_config_manager import ChatAppConfig
from core.app.entities.app_invoke_entities import (
    ChatAppGenerateEntity,
)
from core.app.entities.queue_entities import QueueAnnotationReplyEvent
from core.callback_handler.index_tool_callback_handler import DatasetIndexToolCallbackHandler
from core.memory.token_buffer_memory import TokenBufferMemory
from core.model_manager import ModelInstance
from core.moderation.base import ModerationException
from core.rag.retrieval.dataset_retrieval import DatasetRetrieval
from extensions.ext_database import db
from models.model import App, Conversation, Message

logger = logging.getLogger(__name__)


class ChatAppRunner(AppRunner):
    """
    Chat Application Runner
    """

    def run(self, application_generate_entity: ChatAppGenerateEntity,
            queue_manager: AppQueueManager,
            conversation: Conversation,
            message: Message) -> None:
        """
        运行应用程序。
        
        :param application_generate_entity: 应用生成实体，包含应用配置、输入、查询等信息。
        :param queue_manager: 应用队列管理器，用于消息的发布和处理。
        :param conversation: 会话对象，包含会话相关的信息。
        :param message: 消息对象，包含消息内容等信息。
        :return: 无返回值。
        """
        # 加载应用配置
        app_config = application_generate_entity.app_config
        app_config = cast(ChatAppConfig, app_config)

        # 根据应用ID查询应用记录
        app_record = db.session.query(App).filter(App.id == app_config.app_id).first()
        if not app_record:
            raise ValueError("App not found")

        # 解析输入参数、查询、文件等
        inputs = application_generate_entity.inputs
        query = application_generate_entity.query
        files = application_generate_entity.files

        # 预计算提示消息的令牌数，并根据模型上下文令牌大小限制和最大令牌大小限制返回剩余令牌数。
        # 如果剩余令牌数不足，则抛出异常。
        self.get_pre_calculate_rest_tokens(
            app_record=app_record,
            model_config=application_generate_entity.model_conf,
            prompt_template_entity=app_config.prompt_template,
            inputs=inputs,
            files=files,
            query=query
        )

        memory = None
        if application_generate_entity.conversation_id:
            # 获取会话内存（只读）
            model_instance = ModelInstance(
                provider_model_bundle=application_generate_entity.model_conf.provider_model_bundle,
                model=application_generate_entity.model_conf.model
            )

            memory = TokenBufferMemory(
                conversation=conversation,
                model_instance=model_instance
            )

        # 组织所有输入和模板到提示消息中
        prompt_messages, stop = self.organize_prompt_messages(
            app_record=app_record,
            model_config=application_generate_entity.model_conf,
            prompt_template_entity=app_config.prompt_template,
            inputs=inputs,
            files=files,
            query=query,
            memory=memory
        )

        # 中介审核
        try:
            # 处理敏感词规避
            _, inputs, query = self.moderation_for_inputs(
                app_id=app_record.id,
                tenant_id=app_config.tenant_id,
                app_generate_entity=application_generate_entity,
                inputs=inputs,
                query=query,
                message_id=message.id
            )
        except ModerationException as e:
            self.direct_output(
                queue_manager=queue_manager,
                app_generate_entity=application_generate_entity,
                prompt_messages=prompt_messages,
                text=str(e),
                stream=application_generate_entity.stream
            )
            return

        if query:
            # 查询应用注解并回复
            annotation_reply = self.query_app_annotations_to_reply(
                app_record=app_record,
                message=message,
                query=query,
                user_id=application_generate_entity.user_id,
                invoke_from=application_generate_entity.invoke_from
            )

            if annotation_reply:
                queue_manager.publish(
                    QueueAnnotationReplyEvent(message_annotation_id=annotation_reply.id),
                    PublishFrom.APPLICATION_MANAGER
                )

                self.direct_output(
                    queue_manager=queue_manager,
                    app_generate_entity=application_generate_entity,
                    prompt_messages=prompt_messages,
                    text=annotation_reply.content,
                    stream=application_generate_entity.stream
                )
                return

        # 如果存在，从外部数据工具填充变量输入
        external_data_tools = app_config.external_data_variables
        if external_data_tools:
            inputs = self.fill_in_inputs_from_external_data_tools(
                tenant_id=app_record.tenant_id,
                app_id=app_record.id,
                external_data_tools=external_data_tools,
                inputs=inputs,
                query=query
            )

        # 从数据集获取上下文
        context = None
        if app_config.dataset and app_config.dataset.dataset_ids:
            hit_callback = DatasetIndexToolCallbackHandler(
                queue_manager,
                app_record.id,
                message.id,
                application_generate_entity.user_id,
                application_generate_entity.invoke_from
            )

            dataset_retrieval = DatasetRetrieval(application_generate_entity)
            context = dataset_retrieval.retrieve(
                app_id=app_record.id,
                user_id=application_generate_entity.user_id,
                tenant_id=app_record.tenant_id,
                model_config=application_generate_entity.model_conf,
                config=app_config.dataset,
                query=query,
                invoke_from=application_generate_entity.invoke_from,
                show_retrieve_source=app_config.additional_features.show_retrieve_source,
                hit_callback=hit_callback,
                memory=memory,
                message_id=message.id,
            )

        # 重新组织所有输入和模板到提示消息中，包括外部数据和数据集上下文（如果存在）
        prompt_messages, stop = self.organize_prompt_messages(
            app_record=app_record,
            model_config=application_generate_entity.model_conf,
            prompt_template_entity=app_config.prompt_template,
            inputs=inputs,
            files=files,
            query=query,
            context=context,
            memory=memory
        )

        # 检查托管中介
        hosting_moderation_result = self.check_hosting_moderation(
            application_generate_entity=application_generate_entity,
            queue_manager=queue_manager,
            prompt_messages=prompt_messages
        )

        if hosting_moderation_result:
            return

        # 重新计算最大令牌数，如果提示令牌数加上最大令牌数超过模型令牌限制
        self.recalc_llm_max_tokens(
            model_config=application_generate_entity.model_conf,
            prompt_messages=prompt_messages
        )

        # 调用模型
        model_instance = ModelInstance(
            provider_model_bundle=application_generate_entity.model_conf.provider_model_bundle,
            model=application_generate_entity.model_conf.model
        )

        db.session.close()

        # 模型调用结果处理
        invoke_result = model_instance.invoke_llm(
            prompt_messages=prompt_messages,
            model_parameters=application_generate_entity.model_conf.parameters,
            stop=stop,
            stream=application_generate_entity.stream,
            user=application_generate_entity.user_id,
        )

        # 处理调用结果
        self._handle_invoke_result(
            invoke_result=invoke_result,
            queue_manager=queue_manager,
            stream=application_generate_entity.stream
        )
