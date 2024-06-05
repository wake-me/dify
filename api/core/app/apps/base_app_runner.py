import time
from collections.abc import Generator
from typing import Optional, Union

from core.app.app_config.entities import ExternalDataVariableEntity, PromptTemplateEntity
from core.app.apps.base_app_queue_manager import AppQueueManager, PublishFrom
from core.app.entities.app_invoke_entities import (
    AppGenerateEntity,
    EasyUIBasedAppGenerateEntity,
    InvokeFrom,
    ModelConfigWithCredentialsEntity,
)
from core.app.entities.queue_entities import QueueAgentMessageEvent, QueueLLMChunkEvent, QueueMessageEndEvent
from core.app.features.annotation_reply.annotation_reply import AnnotationReplyFeature
from core.app.features.hosting_moderation.hosting_moderation import HostingModerationFeature
from core.external_data_tool.external_data_fetch import ExternalDataFetch
from core.file.file_obj import FileVar
from core.memory.token_buffer_memory import TokenBufferMemory
from core.model_manager import ModelInstance
from core.model_runtime.entities.llm_entities import LLMResult, LLMResultChunk, LLMResultChunkDelta, LLMUsage
from core.model_runtime.entities.message_entities import AssistantPromptMessage, PromptMessage
from core.model_runtime.entities.model_entities import ModelPropertyKey
from core.model_runtime.errors.invoke import InvokeBadRequestError
from core.moderation.input_moderation import InputModeration
from core.prompt.advanced_prompt_transform import AdvancedPromptTransform
from core.prompt.entities.advanced_prompt_entities import ChatModelMessage, CompletionModelPromptTemplate, MemoryConfig
from core.prompt.simple_prompt_transform import ModelMode, SimplePromptTransform
from models.model import App, AppMode, Message, MessageAnnotation


class AppRunner:
    def get_pre_calculate_rest_tokens(self, app_record: App,
                                      model_config: ModelConfigWithCredentialsEntity,
                                      prompt_template_entity: PromptTemplateEntity,
                                      inputs: dict[str, str],
                                      files: list[FileVar],
                                      query: Optional[str] = None) -> int:
        """
        获取预计算剩余令牌数
        :param app_record: 应用记录
        :param model_config: 模型配置实体
        :param prompt_template_entity: 提示模板实体
        :param inputs: 输入参数
        :param files: 文件列表
        :param query: 查询字符串（可选）
        :return: 剩余令牌数。如果无法确定剩余令牌数，返回-1；如果请求的令牌数超过模型允许的最大值，抛出异常。
        """
        # Invoke model
        model_instance = ModelInstance(
            provider_model_bundle=model_config.provider_model_bundle,
            model=model_config.model
        )

        # 尝试从模型属性中获取上下文大小
        model_context_tokens = model_config.model_schema.model_properties.get(ModelPropertyKey.CONTEXT_SIZE)

        # 遍历参数规则，获取最大令牌数配置
        max_tokens = 0
        for parameter_rule in model_config.model_schema.parameter_rules:
            if (parameter_rule.name == 'max_tokens'
                    or (parameter_rule.use_template and parameter_rule.use_template == 'max_tokens')):
                max_tokens = (model_config.parameters.get(parameter_rule.name)
                              or model_config.parameters.get(parameter_rule.use_template)) or 0

        # 如果未配置上下文大小，返回-1
        if model_context_tokens is None:
            return -1

        # 如果未配置最大令牌数，将最大令牌数设为0
        if max_tokens is None:
            max_tokens = 0

        # 组织提示消息，不包括记忆和上下文
        prompt_messages, stop = self.organize_prompt_messages(
            app_record=app_record,
            model_config=model_config,
            prompt_template_entity=prompt_template_entity,
            inputs=inputs,
            files=files,
            query=query
        )

        prompt_tokens = model_instance.get_llm_num_tokens(
            prompt_messages
        )

        # 计算剩余令牌数
        rest_tokens = model_context_tokens - max_tokens - prompt_tokens
        if rest_tokens < 0:
            # 如果剩余令牌数小于0，表示请求的查询或前缀提示过长，抛出异常
            raise InvokeBadRequestError("Query or prefix prompt is too long, you can reduce the prefix prompt, "
                                        "or shrink the max token, or switch to a llm with a larger token limit size.")

        return rest_tokens

    def recalc_llm_max_tokens(self, model_config: ModelConfigWithCredentialsEntity,
                              prompt_messages: list[PromptMessage]):
        # recalc max_tokens if sum(prompt_token +  max_tokens) over model token limit
        model_instance = ModelInstance(
            provider_model_bundle=model_config.provider_model_bundle,
            model=model_config.model
        )

        # 尝试获取模型的上下文令牌数
        model_context_tokens = model_config.model_schema.model_properties.get(ModelPropertyKey.CONTEXT_SIZE)

        # 统计所有参数规则中名为'max_tokens'或使用模板为'max_tokens'的规则的最大令牌数
        max_tokens = 0
        for parameter_rule in model_config.model_schema.parameter_rules:
            if (parameter_rule.name == 'max_tokens'
                    or (parameter_rule.use_template and parameter_rule.use_template == 'max_tokens')):
                max_tokens = (model_config.parameters.get(parameter_rule.name)
                            or model_config.parameters.get(parameter_rule.use_template)) or 0

        # 如果没有获取到上下文令牌数，直接返回-1
        if model_context_tokens is None:
            return -1

        # 如果没有指定最大令牌数，则默认为0
        if max_tokens is None:
            max_tokens = 0

        prompt_tokens = model_instance.get_llm_num_tokens(
            prompt_messages
        )

        # 如果提示消息和最大令牌数的总和超过模型的上下文令牌数，调整最大令牌数
        if prompt_tokens + max_tokens > model_context_tokens:
            max_tokens = max(model_context_tokens - prompt_tokens, 16)

            # 更新模型配置中的最大令牌数参数
            for parameter_rule in model_config.model_schema.parameter_rules:
                if (parameter_rule.name == 'max_tokens'
                        or (parameter_rule.use_template and parameter_rule.use_template == 'max_tokens')):
                    model_config.parameters[parameter_rule.name] = max_tokens

    def organize_prompt_messages(self, app_record: App,
                                model_config: ModelConfigWithCredentialsEntity,
                                prompt_template_entity: PromptTemplateEntity,
                                inputs: dict[str, str],
                                files: list[FileVar],
                                query: Optional[str] = None,
                                context: Optional[str] = None,
                                memory: Optional[TokenBufferMemory] = None) \
            -> tuple[list[PromptMessage], Optional[list[str]]]:
        """
        组织提示消息
        :param context: 上下文信息
        :param app_record: 应用记录
        :param model_config: 模型配置实体
        :param prompt_template_entity: 提示模板实体
        :param inputs: 输入信息
        :param files: 文件信息
        :param query: 查询信息
        :param memory: 内存（TokenBufferMemory）
        :return: 返回提示消息列表和停止标志（可选）
        """
        # 根据提示模板类型获取提示消息，不考虑内存和上下文
        if prompt_template_entity.prompt_type == PromptTemplateEntity.PromptType.SIMPLE:
            prompt_transform = SimplePromptTransform()
            prompt_messages, stop = prompt_transform.get_prompt(
                app_mode=AppMode.value_of(app_record.mode),
                prompt_template_entity=prompt_template_entity,
                inputs=inputs,
                query=query if query else '',
                files=files,
                context=context,
                memory=memory,
                model_config=model_config
            )
        else:
            # 高级提示配置，禁用内存窗口
            memory_config = MemoryConfig(
                window=MemoryConfig.WindowConfig(
                    enabled=False
                )
            )

            model_mode = ModelMode.value_of(model_config.mode)
            if model_mode == ModelMode.COMPLETION:
                # 完成式提示模板配置
                advanced_completion_prompt_template = prompt_template_entity.advanced_completion_prompt_template
                prompt_template = CompletionModelPromptTemplate(
                    text=advanced_completion_prompt_template.prompt
                )

                if advanced_completion_prompt_template.role_prefix:
                    # 角色前缀配置
                    memory_config.role_prefix = MemoryConfig.RolePrefix(
                        user=advanced_completion_prompt_template.role_prefix.user,
                        assistant=advanced_completion_prompt_template.role_prefix.assistant
                    )
            else:
                # 聊天式提示模板配置
                prompt_template = []
                for message in prompt_template_entity.advanced_chat_prompt_template.messages:
                    prompt_template.append(ChatModelMessage(
                        text=message.text,
                        role=message.role
                    ))

            prompt_transform = AdvancedPromptTransform()
            prompt_messages = prompt_transform.get_prompt(
                prompt_template=prompt_template,
                inputs=inputs,
                query=query if query else '',
                files=files,
                context=context,
                memory_config=memory_config,
                memory=memory,
                model_config=model_config
            )
            stop = model_config.stop

        return prompt_messages, stop

    def direct_output(self, queue_manager: AppQueueManager,
                    app_generate_entity: EasyUIBasedAppGenerateEntity,
                    prompt_messages: list,
                    text: str,
                    stream: bool,
                    usage: Optional[LLMUsage] = None) -> None:
        """
        直接输出功能。
        
        :param queue_manager: 应用队列管理器，用于消息的发布。
        :param app_generate_entity: 应用生成实体，包含应用相关的配置信息。
        :param prompt_messages: 提示信息列表，用于上下文提示。
        :param text: 需要输出的文本内容。
        :param stream: 是否流式输出，如果为True，则将文本内容拆分并逐个发送。
        :param usage: 使用情况，用于记录该操作的使用情况，如果未提供，则默认为空使用情况。
        :return: 无返回值。
        """
        # 如果是流式输出，则将文本按字符逐个发送
        if stream:
            index = 0  # 用于追踪当前发送到哪个字符
            for token in text:  # 拆分文本为单个字符
                chunk = LLMResultChunk(
                    model=app_generate_entity.model_config.model,  # 模型配置
                    prompt_messages=prompt_messages,  # 提示信息列表
                    delta=LLMResultChunkDelta(
                        index=index,  # 当前字符位置
                        message=AssistantPromptMessage(content=token)  # 当前字符内容
                    )
                )

                queue_manager.publish(
                    QueueLLMChunkEvent(
                        chunk=chunk
                    ), PublishFrom.APPLICATION_MANAGER
                )  # 发布到队列
                index += 1
                time.sleep(0.01)  # 为避免发送太频繁，添加短暂停顿

        # 发送文本输出的结束消息，包含完整的文本内容和使用情况
        queue_manager.publish(
            QueueMessageEndEvent(
                llm_result=LLMResult(
                    model=app_generate_entity.model_config.model,
                    prompt_messages=prompt_messages,
                    message=AssistantPromptMessage(content=text),
                    usage=usage if usage else LLMUsage.empty_usage()  # 如果提供了使用情况则使用，否则使用空使用情况
                ),
            ), PublishFrom.APPLICATION_MANAGER
        )

    def _handle_invoke_result(self, invoke_result: Union[LLMResult, Generator],
                            queue_manager: AppQueueManager,
                            stream: bool,
                            agent: bool = False) -> None:
        """
        处理调用结果。
        
        :param invoke_result: 调用结果，可以是LLMResult类型或Generator类型。
        :param queue_manager: 应用程序队列管理器，用于管理消息队列。
        :param stream: 布尔值，指示结果是否以流的形式返回。
        :param agent: 布尔值，标识是否为代理调用，默认为False。
        :return: 无返回值。
        """
        # 根据结果是否以流的形式返回，选择不同的处理方法
        if not stream:
            self._handle_invoke_result_direct(
                invoke_result=invoke_result,
                queue_manager=queue_manager,
                agent=agent
            )
        else:
            self._handle_invoke_result_stream(
                invoke_result=invoke_result,
                queue_manager=queue_manager,
                agent=agent
            )

    def _handle_invoke_result_direct(self, invoke_result: LLMResult,
                                        queue_manager: AppQueueManager,
                                        agent: bool) -> None:
        """
        处理直接调用结果
        :param invoke_result: 调用结果
        :param queue_manager: 应用程序队列管理器
        :return: 无返回值
        """
        # 向队列管理器发布调用结果结束事件
        queue_manager.publish(
            QueueMessageEndEvent(
                llm_result=invoke_result,
            ), PublishFrom.APPLICATION_MANAGER
        )

    def _handle_invoke_result_stream(self, invoke_result: Generator,
                                    queue_manager: AppQueueManager,
                                    agent: bool) -> None:
        """
        处理调用结果流。
        :param invoke_result: 调用结果，是一个生成器，逐个返回调用结果项。
        :param queue_manager: 应用队列管理器，用于发布消息到不同的队列。
        :param agent: 布尔值，指示是否是代理调用。
        :return: 无返回值。
        """
        # 初始化变量
        model = None
        prompt_messages = []
        text = ''
        usage = None

        # 遍历调用结果，发布消息并累积文本、模型信息等
        for result in invoke_result:
            # 根据是否是代理调用，发布不同类型的事件消息
            if not agent:
                queue_manager.publish(
                    QueueLLMChunkEvent(
                        chunk=result
                    ), PublishFrom.APPLICATION_MANAGER
                )
            else:
                queue_manager.publish(
                    QueueAgentMessageEvent(
                        chunk=result
                    ), PublishFrom.APPLICATION_MANAGER
                )

            # 累加响应文本
            text += result.delta.message.content

            # 初始化或更新模型、提示消息、使用信息
            if not model:
                model = result.model

            if not prompt_messages:
                prompt_messages = result.prompt_messages

            if not usage and result.delta.usage:
                usage = result.delta.usage

        # 如果未获取到使用信息，则创建一个空的使用信息
        if not usage:
            usage = LLMUsage.empty_usage()

        # 构建最终的LLM结果，并发布到队列
        llm_result = LLMResult(
            model=model,
            prompt_messages=prompt_messages,
            message=AssistantPromptMessage(content=text),
            usage=usage
        )

        queue_manager.publish(
            QueueMessageEndEvent(
                llm_result=llm_result,
            ), PublishFrom.APPLICATION_MANAGER
        )

    def moderation_for_inputs(self, app_id: str,
                            tenant_id: str,
                            app_generate_entity: AppGenerateEntity,
                            inputs: dict,
                            query: str) -> tuple[bool, dict, str]:
        """
        处理输入内容的审查流程。
        
        :param app_id: 应用ID
        :param tenant_id: 租户ID
        :param app_generate_entity: 应用生成实体，包含应用配置等信息
        :param inputs: 输入的内容字典
        :param query: 查询字符串，可能为空
        :return: 返回一个元组，包含审查结果（布尔值，是否通过审查）、审查详细信息（字典）和查询字符串（字符串）
        """
        # 初始化输入审查特性对象
        moderation_feature = InputModeration()
        # 执行审查检查
        return moderation_feature.check(
            app_id=app_id,
            tenant_id=tenant_id,
            app_config=app_generate_entity.app_config,
            inputs=inputs,
            query=query if query else ''
        )
    
    def check_hosting_moderation(self, application_generate_entity: EasyUIBasedAppGenerateEntity,
                                    queue_manager: AppQueueManager,
                                    prompt_messages: list[PromptMessage]) -> bool:
        """
        检查宿主审核
        :param application_generate_entity: 应用生成实体，包含应用的详细信息
        :param queue_manager: 队列管理器，用于管理审核队列
        :param prompt_messages: 提示消息列表，用于记录和输出过程中的提示信息
        :return: 布尔值，表示审核是否通过
        """
        # 初始化宿主审核特性对象
        hosting_moderation_feature = HostingModerationFeature()
        # 执行审核检查
        moderation_result = hosting_moderation_feature.check(
            application_generate_entity=application_generate_entity,
            prompt_messages=prompt_messages
        )

        # 如果审核不通过，则向用户输出特定消息
        if moderation_result:
            self.direct_output(
                queue_manager=queue_manager,
                app_generate_entity=application_generate_entity,
                prompt_messages=prompt_messages,
                text="I apologize for any confusion, " \
                    "but I'm an AI assistant to be helpful, harmless, and honest.",
                stream=application_generate_entity.stream
            )

        return moderation_result

    def fill_in_inputs_from_external_data_tools(self, tenant_id: str,
                                                    app_id: str,
                                                    external_data_tools: list[ExternalDataVariableEntity],
                                                    inputs: dict,
                                                    query: str) -> dict:
        """
        如果存在，从外部数据工具填充变量输入。

        :param tenant_id: 工作空间id
        :param app_id: 应用id
        :param external_data_tools: 外部数据工具配置
        :param inputs: 输入参数
        :param query: 查询语句
        :return: 填充后的输入参数
        """
        # 初始化外部数据获取特性
        external_data_fetch_feature = ExternalDataFetch()
        # 调用外部数据获取特性进行数据填充
        return external_data_fetch_feature.fetch(
            tenant_id=tenant_id,
            app_id=app_id,
            external_data_tools=external_data_tools,
            inputs=inputs,
            query=query
        )
        
    def query_app_annotations_to_reply(self, app_record: App,
                                        message: Message,
                                        query: str,
                                        user_id: str,
                                        invoke_from: InvokeFrom) -> Optional[MessageAnnotation]:
        """
        查询应用注解以回复
        :param app_record: 应用记录
        :param message: 消息
        :param query: 查询内容
        :param user_id: 用户ID
        :param invoke_from: 调用来源
        :return: 返回查询到的消息注解，可能为None
        """
        # 初始化注解回复特性对象
        annotation_reply_feature = AnnotationReplyFeature()
        # 执行查询，并返回查询结果
        return annotation_reply_feature.query(
            app_record=app_record,
            message=message,
            query=query,
            user_id=user_id,
            invoke_from=invoke_from
        )
