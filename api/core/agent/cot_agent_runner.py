import json
from abc import ABC, abstractmethod
from collections.abc import Generator
from typing import Union

from core.agent.base_agent_runner import BaseAgentRunner
from core.agent.entities import AgentScratchpadUnit
from core.agent.output_parser.cot_output_parser import CotAgentOutputParser
from core.app.apps.base_app_queue_manager import PublishFrom
from core.app.entities.queue_entities import QueueAgentThoughtEvent, QueueMessageEndEvent, QueueMessageFileEvent
from core.model_runtime.entities.llm_entities import LLMResult, LLMResultChunk, LLMResultChunkDelta, LLMUsage
from core.model_runtime.entities.message_entities import (
    AssistantPromptMessage,
    PromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
)
from core.prompt.agent_history_prompt_transform import AgentHistoryPromptTransform
from core.tools.entities.tool_entities import ToolInvokeMeta
from core.tools.tool.tool import Tool
from core.tools.tool_engine import ToolEngine
from models.model import Message


class CotAgentRunner(BaseAgentRunner, ABC):
    """
    CotAgentRunner类，继承自BaseAgentRunner，是一个抽象基类，用于定义对话代理运行器的基本行为。
    
    属性:
    - _is_first_iteration: 表示是否是第一次迭代，用于控制流程的初始化操作。
    - _ignore_observation_providers: 一个列表，包含应忽略的观测提供者名称。
    - _historic_prompt_messages: 存储历史提示消息的列表，用于对话上下文的维护。
    - _agent_scratchpad: 一个列表，用于存储AgentScratchpadUnit对象，辅助代理进行临时数据存储和计算。
    - _instruction: 存储当前的指令信息。
    - _query: 存储当前的查询信息。
    - _prompt_messages_tools: 用于存储提示消息工具的列表，辅助生成和管理提示消息。
    """
    _is_first_iteration = True
    _ignore_observation_providers = ['wenxin']
    _historic_prompt_messages: list[PromptMessage] = None
    _agent_scratchpad: list[AgentScratchpadUnit] = None
    _instruction: str = None
    _query: str = None
    _prompt_messages_tools: list[PromptMessage] = None

    def run(self, message: Message,
            query: str,
            inputs: dict[str, str],
            ) -> Union[Generator, LLMResult]:
        """
        运行Cot代理应用程序。

        参数:
        - message: 消息对象，包含与消息相关的元数据。
        - query: 用户查询字符串。
        - inputs: 用于填充模板的外部数据工具输入字典。

        返回值:
        - 生成器或LLMResult对象，代表模型的响应过程或最终结果。
        """
        # 初始化实体生成和反应状态
        app_generate_entity = self.application_generate_entity
        self._repack_app_generate_entity(app_generate_entity)
        self._init_react_state(query)

        # check model mode
        if 'Observation' not in app_generate_entity.model_conf.stop:
            if app_generate_entity.model_conf.provider not in self._ignore_observation_providers:
                app_generate_entity.model_conf.stop.append('Observation')

        app_config = self.app_config

        # 初始化指令
        inputs = inputs or {}
        instruction = app_config.prompt_template.simple_prompt_template
        self._instruction = self._fill_in_inputs_from_external_data_tools(
            instruction, inputs)

        # 设置迭代步骤和最大迭代次数
        iteration_step = 1
        max_iteration_steps = min(app_config.agent.max_iteration, 5) + 1

        # 将工具转换为ModelRuntime Tool格式
        tool_instances, self._prompt_messages_tools = self._init_prompt_tools()

        function_call_state = True
        llm_usage = {
            'usage': None
        }
        final_answer = ''

        def increase_usage(final_llm_usage_dict: dict[str, LLMUsage], usage: LLMUsage):
            # 增加LLM使用情况统计
            if not final_llm_usage_dict['usage']:
                final_llm_usage_dict['usage'] = usage
            else:
                llm_usage = final_llm_usage_dict['usage']
                llm_usage.prompt_tokens += usage.prompt_tokens
                llm_usage.completion_tokens += usage.completion_tokens
                llm_usage.prompt_price += usage.prompt_price
                llm_usage.completion_price += usage.completion_price

        model_instance = self.model_instance

        while function_call_state and iteration_step <= max_iteration_steps:
            # 直到没有工具调用为止继续运行
            function_call_state = False

            if iteration_step == max_iteration_steps:
                # 最后一次迭代，移除所有工具
                self._prompt_messages_tools = []

            message_file_ids = []

            # 创建代理思考
            agent_thought = self.create_agent_thought(
                message_id=message.id,
                message='',
                tool_name='',
                tool_input='',
                messages_ids=message_file_ids
            )

            # 如果不是第一次迭代，则发布代理思考事件
            if iteration_step > 1:
                self.queue_manager.publish(QueueAgentThoughtEvent(
                    agent_thought_id=agent_thought.id
                ), PublishFrom.APPLICATION_MANAGER)

            # 重新计算LLM最大令牌数
            prompt_messages = self._organize_prompt_messages()
            self.recalc_llm_max_tokens(self.model_config, prompt_messages)
            # 调用模型
            chunks: Generator[LLMResultChunk, None, None] = model_instance.invoke_llm(
                prompt_messages=prompt_messages,
                model_parameters=app_generate_entity.model_conf.parameters,
                tools=[],
                stop=app_generate_entity.model_conf.stop,
                stream=True,
                user=self.user_id,
                callbacks=[],
            )

            # 检查LLM结果
            if not chunks:
                raise ValueError("failed to invoke llm")

            usage_dict = {}
            react_chunks = CotAgentOutputParser.handle_react_stream_output(
                chunks, usage_dict)
            scratchpad = AgentScratchpadUnit(
                agent_response='',
                thought='',
                action_str='',
                observation='',
                action=None,
            )

            # 如果是第一次迭代，则发布代理思考事件
            if iteration_step == 1:
                self.queue_manager.publish(QueueAgentThoughtEvent(
                    agent_thought_id=agent_thought.id
                ), PublishFrom.APPLICATION_MANAGER)

            # 处理反应块并生成结果
            for chunk in react_chunks:
                if isinstance(chunk, AgentScratchpadUnit.Action):
                    action = chunk
                    # detect action
                    scratchpad.agent_response += json.dumps(chunk.model_dump())
                    scratchpad.action_str = json.dumps(chunk.model_dump())
                    scratchpad.action = action
                else:
                    scratchpad.agent_response += chunk
                    scratchpad.thought += chunk
                    yield LLMResultChunk(
                        model=self.model_config.model,
                        prompt_messages=prompt_messages,
                        system_fingerprint='',
                        delta=LLMResultChunkDelta(
                            index=0,
                            message=AssistantPromptMessage(
                                content=chunk
                            ),
                            usage=None
                        )
                    )

            scratchpad.thought = scratchpad.thought.strip(
            ) or 'I am thinking about how to help you'
            self._agent_scratchpad.append(scratchpad)

            # get llm usage
            if 'usage' in usage_dict:
                increase_usage(llm_usage, usage_dict['usage'])
            else:
                usage_dict['usage'] = LLMUsage.empty_usage()

            self.save_agent_thought(
                agent_thought=agent_thought,
                tool_name=scratchpad.action.action_name if scratchpad.action else '',
                tool_input={
                    scratchpad.action.action_name: scratchpad.action.action_input
                } if scratchpad.action else {},
                tool_invoke_meta={},
                thought=scratchpad.thought,
                observation='',
                answer=scratchpad.agent_response,
                messages_ids=[],
                llm_usage=usage_dict['usage']
            )

            if not scratchpad.is_final():
                self.queue_manager.publish(QueueAgentThoughtEvent(
                    agent_thought_id=agent_thought.id
                ), PublishFrom.APPLICATION_MANAGER)

            # 处理最终回答或工具调用
            if not scratchpad.action:
                # failed to extract action, return final answer directly
                final_answer = ''
            else:
                if scratchpad.action.action_name.lower() == "final answer":
                    # 如果动作是最终回答，则直接返回回答
                    try:
                        if isinstance(scratchpad.action.action_input, dict):
                            final_answer = json.dumps(
                                scratchpad.action.action_input)
                        elif isinstance(scratchpad.action.action_input, str):
                            final_answer = scratchpad.action.action_input
                        else:
                            final_answer = f'{scratchpad.action.action_input}'
                    except json.JSONDecodeError:
                        final_answer = f'{scratchpad.action.action_input}'
                else:
                    # 如果动作是工具调用，则调用工具并更新状态
                    function_call_state = True
                    tool_invoke_response, tool_invoke_meta = self._handle_invoke_action(
                        action=scratchpad.action,
                        tool_instances=tool_instances,
                        message_file_ids=message_file_ids
                    )
                    scratchpad.observation = tool_invoke_response
                    scratchpad.agent_response = tool_invoke_response

                    self.save_agent_thought(
                        agent_thought=agent_thought,
                        tool_name=scratchpad.action.action_name,
                        tool_input={
                            scratchpad.action.action_name: scratchpad.action.action_input},
                        thought=scratchpad.thought,
                        observation={
                            scratchpad.action.action_name: tool_invoke_response},
                        tool_invoke_meta={
                            scratchpad.action.action_name: tool_invoke_meta.to_dict()},
                        answer=scratchpad.agent_response,
                        messages_ids=message_file_ids,
                        llm_usage=usage_dict['usage']
                    )

                    self.queue_manager.publish(QueueAgentThoughtEvent(
                        agent_thought_id=agent_thought.id
                    ), PublishFrom.APPLICATION_MANAGER)

                # 更新提示工具消息
                for prompt_tool in self._prompt_messages_tools:
                    self.update_prompt_message_tool(
                        tool_instances[prompt_tool.name], prompt_tool)

            iteration_step += 1

        # 生成最终结果并保存代理思考记录
        yield LLMResultChunk(
            model=model_instance.model,
            prompt_messages=prompt_messages,
            delta=LLMResultChunkDelta(
                index=0,
                message=AssistantPromptMessage(
                    content=final_answer
                ),
                usage=llm_usage['usage']
            ),
            system_fingerprint=''
        )

        self.save_agent_thought(
            agent_thought=agent_thought,
            tool_name='',
            tool_input={},
            tool_invoke_meta={},
            thought=final_answer,
            observation={},
            answer=final_answer,
            messages_ids=[]
        )

        self.update_db_variables(self.variables_pool, self.db_variables_pool)
        # 发布结束事件
        self.queue_manager.publish(QueueMessageEndEvent(llm_result=LLMResult(
            model=model_instance.model,
            prompt_messages=prompt_messages,
            message=AssistantPromptMessage(
                content=final_answer
            ),
            usage=llm_usage['usage'] if llm_usage['usage'] else LLMUsage.empty_usage(
            ),
            system_fingerprint=''
        )), PublishFrom.APPLICATION_MANAGER)

    def _handle_invoke_action(self, action: AgentScratchpadUnit.Action,
                              tool_instances: dict[str, Tool],
                              message_file_ids: list[str]) -> tuple[str, ToolInvokeMeta]:
        """
        处理调用工具的动作。
        :param action: 动作对象，包含要执行的动作名称和参数。
        :param tool_instances: 工具实例字典， key 为工具名称，value 为工具实例。
        :return: 一个元组，包含工具执行后的观察结果和调用元数据。
        """
        # 解析动作信息，尝试调用相应的工具
        tool_call_name = action.action_name
        tool_call_args = action.action_input
        tool_instance = tool_instances.get(tool_call_name)

        if not tool_instance:
            # 如果找不到对应的工具实例，返回错误信息
            answer = f"there is not a tool named {tool_call_name}"
            return answer, ToolInvokeMeta.error_instance(answer)

        if isinstance(tool_call_args, str):
            try:
                tool_call_args = json.loads(tool_call_args)
            except json.JSONDecodeError:
                pass

        # 调用工具，处理响应并收集返回的文件信息
        tool_invoke_response, message_files, tool_invoke_meta = ToolEngine.agent_invoke(
            tool=tool_instance,
            tool_parameters=tool_call_args,
            user_id=self.user_id,
            tenant_id=self.tenant_id,
            message=self.message,
            invoke_from=self.application_generate_entity.invoke_from,
            agent_tool_callback=self.agent_callback
        )

        # 发布文件，将文件保存至变量池并发布消息文件事件
        for message_file, save_as in message_files:
            if save_as:
                self.variables_pool.set_file(
                    tool_name=tool_call_name, value=message_file.id, name=save_as)

            # 发布消息文件
            self.queue_manager.publish(QueueMessageFileEvent(
                message_file_id=message_file.id
            ), PublishFrom.APPLICATION_MANAGER)
            # 收集消息文件 ID
            message_file_ids.append(message_file.id)

        return tool_invoke_response, tool_invoke_meta

    def _convert_dict_to_action(self, action: dict) -> AgentScratchpadUnit.Action:
        """
        将字典转换为操作。

        参数:
        - action: 一个包含操作名称和操作输入的字典。

        返回值:
        - 转换后得到的 AgentScratchpadUnit.Action 对象。
        """
        return AgentScratchpadUnit.Action(
            action_name=action['action'],  # 从字典中提取操作名称
            action_input=action['action_input']  # 从字典中提取操作输入
        )

    def _fill_in_inputs_from_external_data_tools(self, instruction: str, inputs: dict) -> str:
        """
        从外部数据工具填充输入值。
        
        参数:
        - instruction: str，含有占位符的指令字符串，占位符格式为{{{{key}}}}。
        - inputs: dict，包含要替换占位符的键值对，键对应于instruction中的占位符key。
        
        返回值:
        - str，替换占位符后的指令字符串。
        """
        # 遍历输入字典，替换指令中的占位符
        for key, value in inputs.items():
            try:
                instruction = instruction.replace(f'{{{{{key}}}}}', str(value))
            except Exception as e:
                # 如果替换过程中出现异常，则跳过当前占位符的替换
                continue

        return instruction

    def _init_react_state(self, query) -> None:
        """
        初始化反应状态。

        该方法用于初始化代理的“临时工作区”，并组织历史提示消息。

        参数:
        - query: 查询信息，用于初始化或更新代理的工作区。

        返回值:
        - 无
        """
        self._query = query
        self._agent_scratchpad = []
        self._historic_prompt_messages = self._organize_historic_prompt_messages()

    @abstractmethod
    def _organize_prompt_messages(self) -> list[PromptMessage]:
        """
        组织提示消息

        该方法用于组织和整理提示消息，使之更加有序和易于访问。

        返回值:
            list[PromptMessage]: 返回一个PromptMessage类型的列表，其中包含了经过组织的提示消息。
        """

    def _format_assistant_message(self, agent_scratchpad: list[AgentScratchpadUnit]) -> str:
        """
            格式化助手消息

            参数:
            agent_scratchpad: 一个AgentScratchpadUnit类型的列表，包含了对话代理的草稿信息。

            返回值:
            返回一个字符串，该字符串格式化了所有传入的草稿信息，包括最终答案、思考、行动和观察结果。
        """
        message = ''
        for scratchpad in agent_scratchpad:
            if scratchpad.is_final():
                # 如果是最终回答，则追加到消息中
                message += f"Final Answer: {scratchpad.agent_response}"
            else:
                # 如果不是最终回答，则追加思考内容
                message += f"Thought: {scratchpad.thought}\n\n"
                # 如果存在行动字符串，则追加行动内容
                if scratchpad.action_str:
                    message += f"Action: {scratchpad.action_str}\n\n"
                # 如果存在观察结果，则追加观察内容
                if scratchpad.observation:
                    message += f"Observation: {scratchpad.observation}\n\n"

        return message

    def _organize_historic_prompt_messages(self, current_session_messages: list[PromptMessage] = None) -> list[PromptMessage]:
        """
        组织历史提示消息。

        该函数遍历历史提示消息，将它们分类整理，并以特定的顺序放入结果列表中。
        主要将消息分为用户提示消息、工具提示消息和助手提示消息，并在特定条件下将助手的思考过程也加入结果中。

        返回:
            list[PromptMessage]: 经过组织整理后的提示消息列表。
        """
        result: list[PromptMessage] = []
        scratchpads: list[AgentScratchpadUnit] = []
        current_scratchpad: AgentScratchpadUnit = None

        for message in self.history_prompt_messages:
            if isinstance(message, AssistantPromptMessage):
                if not current_scratchpad:
                    current_scratchpad = AgentScratchpadUnit(
                        agent_response=message.content,
                        thought=message.content or 'I am thinking about how to help you',
                        action_str='',
                        action=None,
                        observation=None,
                    )
                    scratchpads.append(current_scratchpad)
                if message.tool_calls:
                    try:
                        current_scratchpad.action = AgentScratchpadUnit.Action(
                            action_name=message.tool_calls[0].function.name,
                            action_input=json.loads(
                                message.tool_calls[0].function.arguments)
                        )
                        current_scratchpad.action_str = json.dumps(
                            current_scratchpad.action.to_dict()
                        )
                    except:
                        pass
            elif isinstance(message, ToolPromptMessage):
                # 如果是工具提示消息，将其观察结果加入当前的助手思考单元
                if current_scratchpad:
                    current_scratchpad.observation = message.content
            elif isinstance(message, UserPromptMessage):
                if scratchpads:
                    result.append(AssistantPromptMessage(
                        content=self._format_assistant_message(scratchpads)
                    ))
                    scratchpads = []
                    current_scratchpad = None

                result.append(message)

        if scratchpads:
            result.append(AssistantPromptMessage(
                content=self._format_assistant_message(scratchpads)
            ))

        historic_prompts = AgentHistoryPromptTransform(
            model_config=self.model_config,
            prompt_messages=current_session_messages or [],
            history_messages=result,
            memory=self.memory
        ).get_prompt()
        return historic_prompts
