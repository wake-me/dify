import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Union, cast

from core.agent.entities import AgentEntity, AgentToolEntity
from core.app.app_config.features.file_upload.manager import FileUploadConfigManager
from core.app.apps.agent_chat.app_config_manager import AgentChatAppConfig
from core.app.apps.base_app_queue_manager import AppQueueManager
from core.app.apps.base_app_runner import AppRunner
from core.app.entities.app_invoke_entities import (
    AgentChatAppGenerateEntity,
    ModelConfigWithCredentialsEntity,
)
from core.callback_handler.agent_tool_callback_handler import DifyAgentCallbackHandler
from core.callback_handler.index_tool_callback_handler import DatasetIndexToolCallbackHandler
from core.file.message_file_parser import MessageFileParser
from core.memory.token_buffer_memory import TokenBufferMemory
from core.model_manager import ModelInstance
from core.model_runtime.entities.llm_entities import LLMUsage
from core.model_runtime.entities.message_entities import (
    AssistantPromptMessage,
    PromptMessage,
    PromptMessageTool,
    SystemPromptMessage,
    TextPromptMessageContent,
    ToolPromptMessage,
    UserPromptMessage,
)
from core.model_runtime.entities.model_entities import ModelFeature
from core.model_runtime.model_providers.__base.large_language_model import LargeLanguageModel
from core.model_runtime.utils.encoders import jsonable_encoder
from core.tools.entities.tool_entities import (
    ToolInvokeMessage,
    ToolParameter,
    ToolRuntimeVariablePool,
)
from core.tools.tool.dataset_retriever_tool import DatasetRetrieverTool
from core.tools.tool.tool import Tool
from core.tools.tool_manager import ToolManager
from core.tools.utils.tool_parameter_converter import ToolParameterConverter
from extensions.ext_database import db
from models.model import Conversation, Message, MessageAgentThought
from models.tools import ToolConversationVariables

logger = logging.getLogger(__name__)

class BaseAgentRunner(AppRunner):
    def __init__(self, tenant_id: str,
                 application_generate_entity: AgentChatAppGenerateEntity,
                 conversation: Conversation,
                 app_config: AgentChatAppConfig,
                 model_config: ModelConfigWithCredentialsEntity,
                 config: AgentEntity,
                 queue_manager: AppQueueManager,
                 message: Message,
                 user_id: str,
                 memory: Optional[TokenBufferMemory] = None,
                 prompt_messages: Optional[list[PromptMessage]] = None,
                 variables_pool: Optional[ToolRuntimeVariablePool] = None,
                 db_variables: Optional[ToolConversationVariables] = None,
                 model_instance: ModelInstance = None
                 ) -> None:
        """
        初始化BaseAgentRunner，负责管理对话代理的运行环境和状态。

        :param tenant_id: 租户ID。
        :param application_generate_entity: 代理聊天应用生成实体，用于应用相关的配置和数据处理。
        :param conversation: 对话实例，包含对话的历史和状态。
        :param app_config: 代理聊天应用配置，包含应用的设置和数据。
        :param model_config: 模型配置，包含模型的详细设置和认证信息。
        :param config: 数据集配置，用于指定数据集的相关设置。
        :param queue_manager: 队列管理器，用于消息和任务的队列管理。
        :param message: 当前消息实例，包含消息内容和相关元数据。
        :param user_id: 用户ID，标识发起对话的用户。
        :param memory: 令牌缓冲区记忆，用于存储对话过程中的临时状态和数据（可选）。
        :param prompt_messages: 提示消息列表，用于对话中的各种提示信息（可选）。
        :param variables_pool: 工具运行时变量池，用于存储和管理变量（可选）。
        :param db_variables: 工具对话变量，用于存储对话过程中的持久化变量（可选）。
        :param model_instance: 模型实例，包含模型的具体实现和认证信息（可选）。
        """
        # 初始化各种属性，包括消息、用户ID、配置等
        self.tenant_id = tenant_id
        self.application_generate_entity = application_generate_entity
        self.conversation = conversation
        self.app_config = app_config
        self.model_config = model_config
        self.config = config
        self.queue_manager = queue_manager
        self.message = message
        self.user_id = user_id
        self.memory = memory
        self.history_prompt_messages = self.organize_agent_history(
            prompt_messages=prompt_messages or []
        )
        self.variables_pool = variables_pool
        self.db_variables_pool = db_variables
        self.model_instance = model_instance

        # 初始化回调处理
        self.agent_callback = DifyAgentCallbackHandler()
        # 初始化数据集工具
        hit_callback = DatasetIndexToolCallbackHandler(
            queue_manager=queue_manager,
            app_id=self.app_config.app_id,
            message_id=message.id,
            user_id=user_id,
            invoke_from=self.application_generate_entity.invoke_from,
        )
        self.dataset_tools = DatasetRetrieverTool.get_dataset_tools(
            tenant_id=tenant_id,
            dataset_ids=app_config.dataset.dataset_ids if app_config.dataset else [],
            retrieve_config=app_config.dataset.retrieve_config if app_config.dataset else None,
            return_resource=app_config.additional_features.show_retrieve_source,
            invoke_from=application_generate_entity.invoke_from,
            hit_callback=hit_callback
        )
        # 计算已经创建的代理思考数量
        self.agent_thought_count = db.session.query(MessageAgentThought).filter(
            MessageAgentThought.message_id == self.message.id,
        ).count()
        db.session.close()

        # 检查模型是否支持流式工具调用
        llm_model = cast(LargeLanguageModel, model_instance.model_type_instance)
        model_schema = llm_model.get_model_schema(model_instance.model, model_instance.credentials)
        if model_schema and ModelFeature.STREAM_TOOL_CALL in (model_schema.features or []):
            self.stream_tool_call = True
        else:
            self.stream_tool_call = False

        # 检查模型是否支持视觉处理
        if model_schema and ModelFeature.VISION in (model_schema.features or []):
            self.files = application_generate_entity.files
        else:
            self.files = []
        self.query = None
        self._current_thoughts: list[PromptMessage] = []

    def _repack_app_generate_entity(self, app_generate_entity: AgentChatAppGenerateEntity) \
            -> AgentChatAppGenerateEntity:
        """
        重新打包应用生成实体
        
        参数:
        app_generate_entity: AgentChatAppGenerateEntity - 输入的应用生成实体对象
        
        返回值:
        AgentChatAppGenerateEntity - 处理后的应用生成实体对象
        """
        # 确保app_config.prompt_template.simple_prompt_template不为None，若为None则设置为空字符串
        if app_generate_entity.app_config.prompt_template.simple_prompt_template is None:
            app_generate_entity.app_config.prompt_template.simple_prompt_template = ''

        return app_generate_entity

    def _convert_tool_response_to_str(self, tool_response: list[ToolInvokeMessage]) -> str:
        """
        处理工具响应并将之转换为字符串格式。
        
        参数:
        - tool_response: 工具响应列表，每个元素是 ToolInvokeMessage 类型，包含不同类型的响应信息（文本、链接、图片等）。
        
        返回值:
        - result: 转换后的字符串，包含所有响应信息的文本表示。
        """
        result = ''
        for response in tool_response:
            # 根据响应类型处理不同的响应信息
            if response.type == ToolInvokeMessage.MessageType.TEXT:
                result += response.message
            elif response.type == ToolInvokeMessage.MessageType.LINK:
                # 对链接响应添加特定提示信息
                result += f"result link: {response.message}. please tell user to check it."
            elif response.type == ToolInvokeMessage.MessageType.IMAGE_LINK or \
                response.type == ToolInvokeMessage.MessageType.IMAGE:
                # 对图片响应添加统一的处理信息，表明图片已发送给用户
                result += "image has been created and sent to user already, you do not need to create it, just tell the user to check it now."
            else:
                # 对于未处理的其他类型响应，添加通用处理信息
                result += f"tool response: {response.message}."

        return result
    
    def _convert_tool_to_prompt_message_tool(self, tool: AgentToolEntity) -> tuple[PromptMessageTool, Tool]:
        """
            将工具转换为提示消息工具。

            参数:
            tool: AgentToolEntity - 需要转换的工具实体对象。

            返回值:
            返回一个元组，包含转换后的PromptMessageTool对象和Tool对象。
        """
        # 获取工具的运行时实体，并加载变量池中的变量
        tool_entity = ToolManager.get_agent_tool_runtime(
            tenant_id=self.tenant_id,
            app_id=self.app_config.app_id,
            agent_tool=tool,
            invoke_from=self.application_generate_entity.invoke_from
        )
        tool_entity.load_variables(self.variables_pool)

        # 初始化PromptMessageTool对象，设置名称、描述和参数
        message_tool = PromptMessageTool(
            name=tool.tool_name,
            description=tool_entity.description.llm,
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            }
        )

        # 遍历工具的所有运行时参数，配置PromptMessageTool的参数
        parameters = tool_entity.get_all_runtime_parameters()
        for parameter in parameters:
            if parameter.form != ToolParameter.ToolParameterForm.LLM:
                continue

            parameter_type = ToolParameterConverter.get_parameter_type(parameter.type)
            enum = []
            if parameter.type == ToolParameter.ToolParameterType.SELECT:
                enum = [option.value for option in parameter.options]

            message_tool.parameters['properties'][parameter.name] = {
                "type": parameter_type,
                "description": parameter.llm_description or '',
            }

            # 如果参数有枚举值，添加到配置中
            if len(enum) > 0:
                message_tool.parameters['properties'][parameter.name]['enum'] = enum

            # 如果参数是必需的，则添加到必需参数列表中
            if parameter.required:
                message_tool.parameters['required'].append(parameter.name)

        return message_tool, tool_entity
    
    def _convert_dataset_retriever_tool_to_prompt_message_tool(self, tool: DatasetRetrieverTool) -> PromptMessageTool:
        """
        将数据集检索工具转换为提示消息工具
        
        参数:
        tool: DatasetRetrieverTool - 需要转换的数据集检索工具实例
        
        返回值:
        PromptMessageTool - 转换后的提示消息工具实例
        """
        # 初始化提示消息工具，设置名称和描述
        prompt_tool = PromptMessageTool(
            name=tool.identity.name,
            description=tool.description.llm,
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            }
        )

        # 遍历检索工具的运行时参数，设置提示消息工具的参数
        for parameter in tool.get_runtime_parameters():
            parameter_type = 'string'  # 默认参数类型为字符串
        
            # 为参数添加类型和描述到提示消息工具的参数配置中
            prompt_tool.parameters['properties'][parameter.name] = {
                "type": parameter_type,
                "description": parameter.llm_description or '',
            }

            # 如果参数是必需的，则将其添加到必需参数列表中
            if parameter.required:
                if parameter.name not in prompt_tool.parameters['required']:
                    prompt_tool.parameters['required'].append(parameter.name)

        return prompt_tool
    
    def _init_prompt_tools(self) -> tuple[dict[str, Tool], list[PromptMessageTool]]:
        """
        初始化工具及其消息提示工具。

        本函数负责根据应用配置和数据集工具配置，初始化并构建工具实体及其相关的消息提示工具实例。
        其中，会尝试将应用配置中的工具和数据集工具转换为消息提示工具，并收集所有工具实体。

        返回值:
            - tool_instances: 字典，键为工具名称，值为工具实体。
            - prompt_messages_tools: 列表，包含所有消息提示工具实例。
        """
        tool_instances = {}
        prompt_messages_tools = []

        # 遍历应用配置中的工具，尝试将其转换为消息提示工具
        for tool in self.app_config.agent.tools if self.app_config.agent else []:
            try:
                prompt_tool, tool_entity = self._convert_tool_to_prompt_message_tool(tool)
            except Exception:
                # 如果转换过程中出现异常，则跳过当前工具，可能是API工具已被删除
                continue
            # 保存工具实体和消息提示工具
            tool_instances[tool.tool_name] = tool_entity
            prompt_messages_tools.append(prompt_tool)

        # 将数据集工具转换为消息提示工具，并保存
        for dataset_tool in self.dataset_tools:
            prompt_tool = self._convert_dataset_retriever_tool_to_prompt_message_tool(dataset_tool)
            # 保存消息提示工具和工具实体
            prompt_messages_tools.append(prompt_tool)
            tool_instances[dataset_tool.identity.name] = dataset_tool

        return tool_instances, prompt_messages_tools

    def update_prompt_message_tool(self, tool: Tool, prompt_tool: PromptMessageTool) -> PromptMessageTool:
        """
        更新提示消息工具的信息。

        :param tool: 工具对象，提供运行时参数。
        :param prompt_tool: 提示消息工具对象，用于收集和展示参数信息。
        :return: 返回更新后的提示消息工具对象。
        """
        # 尝试获取工具的运行时参数
        tool_runtime_parameters = tool.get_runtime_parameters() or []

        for parameter in tool_runtime_parameters:
            # 如果参数形式不是 LLM，跳过处理
            if parameter.form != ToolParameter.ToolParameterForm.LLM:
                continue

            parameter_type = ToolParameterConverter.get_parameter_type(parameter.type)
            enum = []
            if parameter.type == ToolParameter.ToolParameterType.SELECT:
                enum = [option.value for option in parameter.options]
        
            # 更新提示工具的参数信息
            prompt_tool.parameters['properties'][parameter.name] = {
                "type": parameter_type,
                "description": parameter.llm_description or '',
            }

            # 如果参数为选择类型，添加枚举信息
            if len(enum) > 0:
                prompt_tool.parameters['properties'][parameter.name]['enum'] = enum

            # 如果参数为必需的，则将其添加到必需参数列表中
            if parameter.required:
                if parameter.name not in prompt_tool.parameters['required']:
                    prompt_tool.parameters['required'].append(parameter.name)

        return prompt_tool
        
    def create_agent_thought(self, message_id: str, message: str, 
                            tool_name: str, tool_input: str, messages_ids: list[str]
                            ) -> MessageAgentThought:
        """
        创建代理思考记录。

        参数:
        - message_id: 消息的唯一标识符。
        - message: 消息的内容。
        - tool_name: 使用的工具的名称。
        - tool_input: 提供给工具的输入。
        - messages_ids: 关联的消息ID列表。
        
        返回值:
        - MessageAgentThought对象，代表创建的思考记录。
        """
        # 初始化MessageAgentThought对象
        thought = MessageAgentThought(
            message_id=message_id,
            message_chain_id=None,
            thought='',
            tool=tool_name,
            tool_labels_str='{}',
            tool_meta_str='{}',
            tool_input=tool_input,
            message=message,
            message_token=0,
            message_unit_price=0,
            message_price_unit=0,
            message_files=json.dumps(messages_ids) if messages_ids else '',
            answer='',
            observation='',
            answer_token=0,
            answer_unit_price=0,
            answer_price_unit=0,
            tokens=0,
            total_price=0,
            position=self.agent_thought_count + 1,
            currency='USD',
            latency=0,
            created_by_role='account',
            created_by=self.user_id,
        )

        # 将思考记录添加到数据库并提交更改
        db.session.add(thought)
        db.session.commit()
        db.session.refresh(thought)  # 刷新对象以获取最新的数据库状态
        db.session.close()  # 关闭数据库会话

        self.agent_thought_count += 1  # 更新代理思考计数

        return thought  # 返回创建的思考记录对象

    def save_agent_thought(self, 
                        agent_thought: MessageAgentThought, 
                        tool_name: str,
                        tool_input: Union[str, dict],
                        thought: str, 
                        observation: Union[str, dict], 
                        tool_invoke_meta: Union[str, dict],
                        answer: str,
                        messages_ids: list[str],
                        llm_usage: LLMUsage = None) -> MessageAgentThought:
        """
        保存代理思考结果到数据库。
        
        参数:
        - agent_thought: MessageAgentThought对象，代表一个代理的思考记录。
        - tool_name: 字符串，表示使用的工具名称。
        - tool_input: 字符串或字典，表示工具的输入信息。
        - thought: 字符串，表示代理的思考内容。
        - observation: 字符串或字典，表示代理观察到的结果。
        - tool_invoke_meta: 字符串或字典，包含调用工具的元数据。
        - answer: 字符串，表示代理给出的答案。
        - messages_ids: 字符串列表，表示与消息相关的文件ID。
        - llm_usage: LLMUsage对象，包含关于大语言模型使用情况的详细信息。
        
        返回:
        - 更新后的MessageAgentThought对象。
        """
        
        # 从数据库获取对应的agent_thought对象
        agent_thought = db.session.query(MessageAgentThought).filter(
            MessageAgentThought.id == agent_thought.id
        ).first()

        # 更新思考结果、工具名称、工具输入、观察结果、答案和消息文件ID
        if thought is not None:
            agent_thought.thought = thought

        if tool_name is not None:
            agent_thought.tool = tool_name

        if tool_input is not None:
            if isinstance(tool_input, dict):
                try:
                    tool_input = json.dumps(tool_input, ensure_ascii=False)
                except Exception as e:
                    tool_input = json.dumps(tool_input)

            agent_thought.tool_input = tool_input

        if observation is not None:
            if isinstance(observation, dict):
                try:
                    observation = json.dumps(observation, ensure_ascii=False)
                except Exception as e:
                    observation = json.dumps(observation)
                    
            agent_thought.observation = observation

        if answer is not None:
            agent_thought.answer = answer

        if messages_ids is not None and len(messages_ids) > 0:
            agent_thought.message_files = json.dumps(messages_ids)
        
        if llm_usage:
            # 更新与大语言模型使用相关的数据
            agent_thought.message_token = llm_usage.prompt_tokens
            agent_thought.message_price_unit = llm_usage.prompt_price_unit
            agent_thought.message_unit_price = llm_usage.prompt_unit_price
            agent_thought.answer_token = llm_usage.completion_tokens
            agent_thought.answer_price_unit = llm_usage.completion_price_unit
            agent_thought.answer_unit_price = llm_usage.completion_unit_price
            agent_thought.tokens = llm_usage.total_tokens
            agent_thought.total_price = llm_usage.total_price

        # 更新工具标签
        labels = agent_thought.tool_labels or {}
        tools = agent_thought.tool.split(';') if agent_thought.tool else []
        for tool in tools:
            if not tool:
                continue
            if tool not in labels:
                tool_label = ToolManager.get_tool_label(tool)
                if tool_label:
                    labels[tool] = tool_label.to_dict()
                else:
                    labels[tool] = {'en_US': tool, 'zh_Hans': tool}

        agent_thought.tool_labels_str = json.dumps(labels)

        if tool_invoke_meta is not None:
            # 更新工具调用元数据
            if isinstance(tool_invoke_meta, dict):
                try:
                    tool_invoke_meta = json.dumps(tool_invoke_meta, ensure_ascii=False)
                except Exception as e:
                    tool_invoke_meta = json.dumps(tool_invoke_meta)

            agent_thought.tool_meta_str = tool_invoke_meta

        # 提交数据库事务并关闭数据库会话
        db.session.commit()
        db.session.close()
    
    def update_db_variables(self, tool_variables: ToolRuntimeVariablePool, db_variables: ToolConversationVariables):
        """
        将工具变量更新到数据库变量中。

        :param tool_variables: ToolRuntimeVariablePool 类型，表示当前工具运行时的变量池。
        :param db_variables: ToolConversationVariables 类型，表示数据库中与当前对话相关的变量存储。
        :return: 无返回值。
        """
        # 从数据库中查询当前对话对应的变量存储对象
        db_variables = db.session.query(ToolConversationVariables).filter(
            ToolConversationVariables.conversation_id == self.message.conversation_id,
        ).first()

        # 更新数据库变量的最后更新时间和变量值
        db_variables.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db_variables.variables_str = json.dumps(jsonable_encoder(tool_variables.pool))

        # 提交数据库事务并关闭数据库会话
        db.session.commit()
        db.session.close()

    def organize_agent_history(self, prompt_messages: list[PromptMessage]) -> list[PromptMessage]:
        """
        组织代理历史记录
        
        参数:
        - prompt_messages: 一个 PromptMessage 对象的列表，代表对话中的消息历史
        
        返回值:
        - 一个 PromptMessage 对象的列表，按照时间顺序组织好的代理对话历史
        """
        result = []
        # 检查对话开始是否有系统消息
        for prompt_message in prompt_messages:
            if isinstance(prompt_message, SystemPromptMessage):
                result.append(prompt_message)

        # 从数据库中查询消息记录，并按照创建时间升序排序
        messages: list[Message] = db.session.query(Message).filter(
            Message.conversation_id == self.message.conversation_id,
        ).order_by(Message.created_at.asc()).all()

        for message in messages:
            if message.id == self.message.id:
                continue

            result.append(self.organize_agent_user_prompt(message))
            
            # 处理消息中的代理思考内容
            agent_thoughts: list[MessageAgentThought] = message.agent_thoughts
            if agent_thoughts:
                for agent_thought in agent_thoughts:
                    tools = agent_thought.tool
                    if tools:
                        tools = tools.split(';')
                        tool_calls: list[AssistantPromptMessage.ToolCall] = []
                        tool_call_response: list[ToolPromptMessage] = []
                        try:
                            tool_inputs = json.loads(agent_thought.tool_input)
                        except Exception as e:
                            tool_inputs = { tool: {} for tool in tools }
                        try:
                            tool_responses = json.loads(agent_thought.observation)
                        except Exception as e:
                            tool_responses = { tool: agent_thought.observation for tool in tools }

                        for tool in tools:
                            # 为工具调用生成一个唯一标识符
                            tool_call_id = str(uuid.uuid4())
                            tool_calls.append(AssistantPromptMessage.ToolCall(
                                id=tool_call_id,
                                type='function',
                                function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                                    name=tool,
                                    arguments=json.dumps(tool_inputs.get(tool, {})),
                                )
                            ))
                            tool_call_response.append(ToolPromptMessage(
                                content=tool_responses.get(tool, agent_thought.observation),
                                name=tool,
                                tool_call_id=tool_call_id,
                            ))

                        # 将工具调用和响应消息添加到结果列表中
                        result.extend([
                            AssistantPromptMessage(
                                content=agent_thought.thought,
                                tool_calls=tool_calls,
                            ),
                            *tool_call_response
                        ])
                    if not tools:
                        result.append(AssistantPromptMessage(content=agent_thought.thought))
            else:
                # 如果是用户的回答，则直接添加到结果中
                if message.answer:
                    result.append(AssistantPromptMessage(content=message.answer))

        db.session.close()

        return result

    def organize_agent_user_prompt(self, message: Message) -> UserPromptMessage:
        """
        组织代理用户提示信息。
        
        根据传入的消息对象，解析其中的文件信息，并根据文件额外配置（如存在），生成相应的用户提示消息。
        如果消息中包含文件且有额外配置，则将查询内容和文件信息一并返回；若无文件或无额外配置，则仅返回查询内容。
        
        参数:
        - message: Message 类型，包含用户查询和可能附带的文件信息的消息对象。
        
        返回值:
        - UserPromptMessage 类型，包含组织后的用户提示信息，可能是纯文本查询内容，或查询内容加上文件信息。
        """
        
        # 初始化消息文件解析器
        message_file_parser = MessageFileParser(
            tenant_id=self.tenant_id,
            app_id=self.app_config.app_id,
        )

        files = message.message_files
        if files:
            # 尝试从消息应用模型配置中转换出文件上传的额外配置
            file_extra_config = FileUploadConfigManager.convert(message.app_model_config.to_dict())

            if file_extra_config:
                # 如果存在文件上传额外配置，就解析消息中的文件
                file_objs = message_file_parser.transform_message_files(
                    files,
                    file_extra_config
                )
            else:
                # 无额外配置时，文件对象列表为空
                file_objs = []

            if not file_objs:
                # 如果没有解析出文件对象，则只返回查询内容
                return UserPromptMessage(content=message.query)
            else:
                # 如果有解析出文件对象，将查询内容和每个文件对象的提示信息组织成一个列表后返回
                prompt_message_contents = [TextPromptMessageContent(data=message.query)]
                for file_obj in file_objs:
                    prompt_message_contents.append(file_obj.prompt_message_content)

                return UserPromptMessage(content=prompt_message_contents)
        else:
            # 消息中无文件时，直接返回查询内容
            return UserPromptMessage(content=message.query)
         