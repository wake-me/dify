import logging
from typing import cast

from core.app.apps.base_app_queue_manager import AppQueueManager
from core.app.apps.base_app_runner import AppRunner
from core.app.apps.completion.app_config_manager import CompletionAppConfig
from core.app.entities.app_invoke_entities import (
    CompletionAppGenerateEntity,
)
from core.callback_handler.index_tool_callback_handler import DatasetIndexToolCallbackHandler
from core.model_manager import ModelInstance
from core.moderation.base import ModerationException
from core.rag.retrieval.dataset_retrieval import DatasetRetrieval
from extensions.ext_database import db
from models.model import App, Message

logger = logging.getLogger(__name__)


class CompletionAppRunner(AppRunner):
    """
    Completion Application Runner
    """

    def run(self, application_generate_entity: CompletionAppGenerateEntity,
            queue_manager: AppQueueManager,
            message: Message) -> None:
        """
        运行应用程序。
        
        :param application_generate_entity: 应用生成实体，包含应用配置、输入、查询等信息。
        :param queue_manager: 应用队列管理器，用于管理消息队列。
        :param message: 消息对象，包含应用运行所需的消息内容。
        :return: 无返回值。
        """
        # 根据应用ID查询应用记录
        app_config = application_generate_entity.app_config
        app_config = cast(CompletionAppConfig, app_config)

        app_record = db.session.query(App).filter(App.id == app_config.app_id).first()
        if not app_record:
            raise ValueError("App not found")

        inputs = application_generate_entity.inputs
        query = application_generate_entity.query
        files = application_generate_entity.files

        # 预计算提示消息中的令牌数量，并根据模型上下文和最大令牌数限制返回剩余令牌数。
        # 如果剩余令牌数不足，则抛出异常。
        self.get_pre_calculate_rest_tokens(
            app_record=app_record,
            model_config=application_generate_entity.model_conf,
            prompt_template_entity=app_config.prompt_template,
            inputs=inputs,
            files=files,
            query=query
        )

        # 组织所有输入和模板到提示消息中
        prompt_messages, stop = self.organize_prompt_messages(
            app_record=app_record,
            model_config=application_generate_entity.model_conf,
            prompt_template_entity=app_config.prompt_template,
            inputs=inputs,
            files=files,
            query=query
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

            dataset_config = app_config.dataset
            if dataset_config and dataset_config.retrieve_config.query_variable:
                query = inputs.get(dataset_config.retrieve_config.query_variable, "")

            dataset_retrieval = DatasetRetrieval(application_generate_entity)
            context = dataset_retrieval.retrieve(
                app_id=app_record.id,
                user_id=application_generate_entity.user_id,
                tenant_id=app_record.tenant_id,
                model_config=application_generate_entity.model_conf,
                config=dataset_config,
                query=query,
                invoke_from=application_generate_entity.invoke_from,
                show_retrieve_source=app_config.additional_features.show_retrieve_source,
                hit_callback=hit_callback,
                message_id=message.id
            )

        # 重新组织所有输入和模板到提示消息中，包括记忆、外部数据和数据集上下文（如果存在）
        prompt_messages, stop = self.organize_prompt_messages(
            app_record=app_record,
            model_config=application_generate_entity.model_conf,
            prompt_template_entity=app_config.prompt_template,
            inputs=inputs,
            files=files,
            query=query,
            context=context
        )

        # 检查宿主中介审核
        hosting_moderation_result = self.check_hosting_moderation(
            application_generate_entity=application_generate_entity,
            queue_manager=queue_manager,
            prompt_messages=prompt_messages
        )

        if hosting_moderation_result:
            return

        # 如果提示令牌数和最大令牌数之和超过模型令牌限制，则重新计算最大令牌数
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
    