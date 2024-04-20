import logging
from typing import cast

from core.agent.cot_agent_runner import CotAgentRunner
from core.agent.entities import AgentEntity
from core.agent.fc_agent_runner import FunctionCallAgentRunner
from core.app.apps.agent_chat.app_config_manager import AgentChatAppConfig
from core.app.apps.base_app_queue_manager import AppQueueManager, PublishFrom
from core.app.apps.base_app_runner import AppRunner
from core.app.entities.app_invoke_entities import AgentChatAppGenerateEntity, ModelConfigWithCredentialsEntity
from core.app.entities.queue_entities import QueueAnnotationReplyEvent
from core.memory.token_buffer_memory import TokenBufferMemory
from core.model_manager import ModelInstance
from core.model_runtime.entities.llm_entities import LLMUsage
from core.model_runtime.entities.model_entities import ModelFeature
from core.model_runtime.model_providers.__base.large_language_model import LargeLanguageModel
from core.moderation.base import ModerationException
from core.tools.entities.tool_entities import ToolRuntimeVariablePool
from extensions.ext_database import db
from models.model import App, Conversation, Message, MessageAgentThought
from models.tools import ToolConversationVariables

logger = logging.getLogger(__name__)


class AgentChatAppRunner(AppRunner):
    """
    Agent Application Runner
    """
    def run(self, application_generate_entity: AgentChatAppGenerateEntity,
            queue_manager: AppQueueManager,
            conversation: Conversation,
            message: Message) -> None:
        """
        运行助手应用程序
        :param application_generate_entity: 应用生成实体，包含应用配置、输入、查询等信息
        :param queue_manager: 应用队列管理器，用于消息的发布和订阅
        :param conversation: 会话对象，包含会话的相关信息
        :param message: 消息对象，包含消息的内容、发送者等信息
        :return: 无返回值
        """
        # 加载应用配置并验证应用是否存在
        app_config = application_generate_entity.app_config
        app_config = cast(AgentChatAppConfig, app_config)

        app_record = db.session.query(App).filter(App.id == app_config.app_id).first()
        if not app_record:
            raise ValueError("App not found")

        # 处理输入参数和查询，并进行前置计算，确定模型处理能力范围
        inputs = application_generate_entity.inputs
        query = application_generate_entity.query
        files = application_generate_entity.files

        self.get_pre_calculate_rest_tokens(
            app_record=app_record,
            model_config=application_generate_entity.model_config,
            prompt_template_entity=app_config.prompt_template,
            inputs=inputs,
            files=files,
            query=query
        )

        # 如果存在会话ID，则获取会话内存（只读）
        memory = None
        if application_generate_entity.conversation_id:
            model_instance = ModelInstance(
                provider_model_bundle=application_generate_entity.model_config.provider_model_bundle,
                model=application_generate_entity.model_config.model
            )

            memory = TokenBufferMemory(
                conversation=conversation,
                model_instance=model_instance
            )

        # 组织输入和模板到提示消息中
        prompt_messages, _ = self.organize_prompt_messages(
            app_record=app_record,
            model_config=application_generate_entity.model_config,
            prompt_template_entity=app_config.prompt_template,
            inputs=inputs,
            files=files,
            query=query,
            memory=memory
        )

        # 中介审核，处理敏感词避免
        try:
            _, inputs, query = self.moderation_for_inputs(
                app_id=app_record.id,
                tenant_id=app_config.tenant_id,
                app_generate_entity=application_generate_entity,
                inputs=inputs,
                query=query,
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

        # 如果存在查询，进行注解回复处理
        if query:
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

        # 如果存在外部数据工具，填充输入变量
        external_data_tools = app_config.external_data_variables
        if external_data_tools:
            inputs = self.fill_in_inputs_from_external_data_tools(
                tenant_id=app_record.tenant_id,
                app_id=app_record.id,
                external_data_tools=external_data_tools,
                inputs=inputs,
                query=query
            )

        # 重新组织输入和模板到提示消息中，包括外部数据和数据集上下文
        prompt_messages, _ = self.organize_prompt_messages(
            app_record=app_record,
            model_config=application_generate_entity.model_config,
            prompt_template_entity=app_config.prompt_template,
            inputs=inputs,
            files=files,
            query=query,
            memory=memory
        )

        # 进行宿主中介审核
        hosting_moderation_result = self.check_hosting_moderation(
            application_generate_entity=application_generate_entity,
            queue_manager=queue_manager,
            prompt_messages=prompt_messages
        )

        if hosting_moderation_result:
            return

        # 加载代理实体并处理工具变量
        agent_entity = app_config.agent

        tool_conversation_variables = self._load_tool_variables(conversation_id=conversation.id,
                                                            user_id=application_generate_entity.user_id,
                                                            tenant_id=app_config.tenant_id)

        tool_variables = self._convert_db_variables_to_tool_variables(tool_conversation_variables)

        # 初始化模型实例
        model_instance = ModelInstance(
            provider_model_bundle=application_generate_entity.model_config.provider_model_bundle,
            model=application_generate_entity.model_config.model
        )
        prompt_message, _ = self.organize_prompt_messages(
            app_record=app_record,
            model_config=application_generate_entity.model_config,
            prompt_template_entity=app_config.prompt_template,
            inputs=inputs,
            files=files,
            query=query,
            memory=memory,
        )

        # 根据LLM模型，改变函数调用策略
        llm_model = cast(LargeLanguageModel, model_instance.model_type_instance)
        model_schema = llm_model.get_model_schema(model_instance.model, model_instance.credentials)

        if set([ModelFeature.MULTI_TOOL_CALL, ModelFeature.TOOL_CALL]).intersection(model_schema.features or []):
            agent_entity.strategy = AgentEntity.Strategy.FUNCTION_CALLING

        # 更新会话和消息对象，并关闭数据库会话
        conversation = db.session.query(Conversation).filter(Conversation.id == conversation.id).first()
        message = db.session.query(Message).filter(Message.id == message.id).first()
        db.session.close()

        # 根据代理调用策略，启动相应运行器处理会话和消息
        if agent_entity.strategy == AgentEntity.Strategy.CHAIN_OF_THOUGHT:
            assistant_cot_runner = CotAgentRunner(
                tenant_id=app_config.tenant_id,
                application_generate_entity=application_generate_entity,
                app_config=app_config,
                model_config=application_generate_entity.model_config,
                config=agent_entity,
                queue_manager=queue_manager,
                message=message,
                user_id=application_generate_entity.user_id,
                memory=memory,
                prompt_messages=prompt_message,
                variables_pool=tool_variables,
                db_variables=tool_conversation_variables,
                model_instance=model_instance
            )
            invoke_result = assistant_cot_runner.run(
                conversation=conversation,
                message=message,
                query=query,
                inputs=inputs,
            )
        elif agent_entity.strategy == AgentEntity.Strategy.FUNCTION_CALLING:
            assistant_fc_runner = FunctionCallAgentRunner(
                tenant_id=app_config.tenant_id,
                application_generate_entity=application_generate_entity,
                app_config=app_config,
                model_config=application_generate_entity.model_config,
                config=agent_entity,
                queue_manager=queue_manager,
                message=message,
                user_id=application_generate_entity.user_id,
                memory=memory,
                prompt_messages=prompt_message,
                variables_pool=tool_variables,
                db_variables=tool_conversation_variables,
                model_instance=model_instance
            )
            invoke_result = assistant_fc_runner.run(
                conversation=conversation,
                message=message,
                query=query,
            )

        # 处理调用结果
        self._handle_invoke_result(
            invoke_result=invoke_result,
            queue_manager=queue_manager,
            stream=application_generate_entity.stream,
            agent=True
        )

    def _load_tool_variables(self, conversation_id: str, user_id: str, tenant_id: str) -> ToolConversationVariables:
        """
        从数据库加载工具会话变量。
        
        参数:
        conversation_id (str): 会话ID。
        user_id (str): 用户ID。
        tenant_id (str): 租户ID。
        
        返回:
        ToolConversationVariables: 加载的工具会话变量实例。
        """
        # 从数据库查询现有的工具会话变量
        tool_variables: ToolConversationVariables = db.session.query(ToolConversationVariables).filter(
            ToolConversationVariables.conversation_id == conversation_id,
            ToolConversationVariables.tenant_id == tenant_id
        ).first()

        if tool_variables:
            # 如果变量已存在，则将其添加到会话中以备后续更新
            db.session.add(tool_variables)
        else:
            # 如果变量不存在，则创建新的工具会话变量并保存到数据库
            tool_variables = ToolConversationVariables(
                conversation_id=conversation_id,
                user_id=user_id,
                tenant_id=tenant_id,
                variables_str='[]',
            )
            db.session.add(tool_variables)
            db.session.commit()  # 提交数据库事务以保存新的会话变量

        return tool_variables
    
    def _convert_db_variables_to_tool_variables(self, db_variables: ToolConversationVariables) -> ToolRuntimeVariablePool:
        """
        将数据库变量转换为工具变量。

        参数:
        - db_variables: ToolConversationVariables 类型，包含从数据库获取的会话变量。

        返回值:
        - ToolRuntimeVariablePool 类型，是一个包含转换后工具运行时变量的池。
        """
        # 使用关键字参数构造 ToolRuntimeVariablePool 实例
        return ToolRuntimeVariablePool(**{
            'conversation_id': db_variables.conversation_id,  # 会话ID
            'user_id': db_variables.user_id,  # 用户ID
            'tenant_id': db_variables.tenant_id,  # 租户ID
            'pool': db_variables.variables  # 变量池
        })

    def _get_usage_of_all_agent_thoughts(self, model_config: ModelConfigWithCredentialsEntity,
                                         message: Message) -> LLMUsage:
        """
        获取所有代理思考的使用情况
        :param model_config: 模型配置，包含认证信息
        :param message: 消息对象
        :return: 返回模型使用情况
        """
        # 从数据库查询与当前消息关联的所有代理思考记录
        agent_thoughts = (db.session.query(MessageAgentThought)
                          .filter(MessageAgentThought.message_id == message.id).all())

        # 初始化消息令牌和答案令牌的总数
        all_message_tokens = 0
        all_answer_tokens = 0
        # 计算所有代理思考中消息和答案的令牌总数
        for agent_thought in agent_thoughts:
            all_message_tokens += agent_thought.message_tokens
            all_answer_tokens += agent_thought.answer_tokens

        # 获取模型类型实例，并强制转换为大型语言模型类型
        model_type_instance = model_config.provider_model_bundle.model_type_instance
        model_type_instance = cast(LargeLanguageModel, model_type_instance)

        # 计算并返回响应的使用情况
        return model_type_instance._calc_response_usage(
            model_config.model,
            model_config.credentials,
            all_message_tokens,
            all_answer_tokens
        )
