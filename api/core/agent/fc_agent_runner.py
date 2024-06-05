import json
import logging
from collections.abc import Generator
from copy import deepcopy
from typing import Any, Union

from core.agent.base_agent_runner import BaseAgentRunner
from core.app.apps.base_app_queue_manager import PublishFrom
from core.app.entities.queue_entities import QueueAgentThoughtEvent, QueueMessageEndEvent, QueueMessageFileEvent
from core.model_runtime.entities.llm_entities import LLMResult, LLMResultChunk, LLMResultChunkDelta, LLMUsage
from core.model_runtime.entities.message_entities import (
    AssistantPromptMessage,
    PromptMessage,
    PromptMessageContentType,
    SystemPromptMessage,
    TextPromptMessageContent,
    ToolPromptMessage,
    UserPromptMessage,
)
from core.prompt.agent_history_prompt_transform import AgentHistoryPromptTransform
from core.tools.entities.tool_entities import ToolInvokeMeta
from core.tools.tool_engine import ToolEngine
from models.model import Message

logger = logging.getLogger(__name__)

class FunctionCallAgentRunner(BaseAgentRunner):

    def run(self, 
            message: Message, query: str, **kwargs: Any
    ) -> Generator[LLMResultChunk, None, None]:
        """
        Run FunctionCall agent application
        """
        self.query = query
        app_generate_entity = self.application_generate_entity
        app_config = self.app_config

        # convert tools into ModelRuntime Tool format
        tool_instances, prompt_messages_tools = self._init_prompt_tools()

        iteration_step = 1
        max_iteration_steps = min(app_config.agent.max_iteration, 5) + 1

        # 根据工具调用状态持续运行，直到没有工具调用或达到最大迭代次数
        function_call_state = True
        llm_usage = {
            'usage': None
        }
        final_answer = ''

        def increase_usage(final_llm_usage_dict: dict[str, LLMUsage], usage: LLMUsage):
            # 更新LLM使用情况
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
            function_call_state = False

            if iteration_step == max_iteration_steps:
                # 最后一次迭代，移除所有工具
                prompt_messages_tools = []

            message_file_ids = []
            agent_thought = self.create_agent_thought(
                message_id=message.id,
                message='',
                tool_name='',
                tool_input='',
                messages_ids=message_file_ids
            )

            # recalc llm max tokens
            prompt_messages = self._organize_prompt_messages()
            self.recalc_llm_max_tokens(self.model_config, prompt_messages)
            # 调用模型
            chunks: Union[Generator[LLMResultChunk, None, None], LLMResult] = model_instance.invoke_llm(
                prompt_messages=prompt_messages,
                model_parameters=app_generate_entity.model_config.parameters,
                tools=prompt_messages_tools,
                stop=app_generate_entity.model_config.stop,
                stream=self.stream_tool_call,
                user=self.user_id,
                callbacks=[],
            )

            tool_calls: list[tuple[str, str, dict[str, Any]]] = []

            # 保存完整响应
            response = ''

            # 保存工具调用名称和输入
            tool_call_names = ''
            tool_call_inputs = ''

            current_llm_usage = None

            if self.stream_tool_call:
                is_first_chunk = True
                for chunk in chunks:
                    if is_first_chunk:
                        self.queue_manager.publish(QueueAgentThoughtEvent(
                            agent_thought_id=agent_thought.id
                        ), PublishFrom.APPLICATION_MANAGER)
                        is_first_chunk = False
                    # 检查是否有工具调用
                    if self.check_tool_calls(chunk):
                        function_call_state = True
                        tool_calls.extend(self.extract_tool_calls(chunk))
                        tool_call_names = ';'.join([tool_call[1] for tool_call in tool_calls])
                        try:
                            tool_call_inputs = json.dumps({
                                tool_call[1]: tool_call[2] for tool_call in tool_calls
                            }, ensure_ascii=False)
                        except json.JSONDecodeError as e:
                            # 确保ascii避免编码错误
                            tool_call_inputs = json.dumps({
                                tool_call[1]: tool_call[2] for tool_call in tool_calls
                            })

                    if chunk.delta.message and chunk.delta.message.content:
                        if isinstance(chunk.delta.message.content, list):
                            for content in chunk.delta.message.content:
                                response += content.data
                        else:
                            response += chunk.delta.message.content

                    if chunk.delta.usage:
                        increase_usage(llm_usage, chunk.delta.usage)
                        current_llm_usage = chunk.delta.usage

                    yield chunk
            else:
                result: LLMResult = chunks
                # 检查是否有阻塞式工具调用
                if self.check_blocking_tool_calls(result):
                    function_call_state = True
                    tool_calls.extend(self.extract_blocking_tool_calls(result))
                    tool_call_names = ';'.join([tool_call[1] for tool_call in tool_calls])
                    try:
                        tool_call_inputs = json.dumps({
                            tool_call[1]: tool_call[2] for tool_call in tool_calls
                        }, ensure_ascii=False)
                    except json.JSONDecodeError as e:
                        # 确保ascii避免编码错误
                        tool_call_inputs = json.dumps({
                            tool_call[1]: tool_call[2] for tool_call in tool_calls
                        })

                if result.usage:
                    increase_usage(llm_usage, result.usage)
                    current_llm_usage = result.usage

                if result.message and result.message.content:
                    if isinstance(result.message.content, list):
                        for content in result.message.content:
                            response += content.data
                    else:
                        response += result.message.content

                if not result.message.content:
                    result.message.content = ''

                self.queue_manager.publish(QueueAgentThoughtEvent(
                    agent_thought_id=agent_thought.id
                ), PublishFrom.APPLICATION_MANAGER)
                
                yield LLMResultChunk(
                    model=model_instance.model,
                    prompt_messages=result.prompt_messages,
                    system_fingerprint=result.system_fingerprint,
                    delta=LLMResultChunkDelta(
                        index=0,
                        message=result.message,
                        usage=result.usage,
                    )
                )

            assistant_message = AssistantPromptMessage(
                content='',
                tool_calls=[]
            )
            if tool_calls:
                assistant_message.tool_calls=[
                    AssistantPromptMessage.ToolCall(
                        id=tool_call[0],
                        type='function',
                        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                            name=tool_call[1],
                            arguments=json.dumps(tool_call[2], ensure_ascii=False)
                        )
                    ) for tool_call in tool_calls
                ]
            else:
                assistant_message.content = response
            
            self._current_thoughts.append(assistant_message)

            # 保存思考记录
            self.save_agent_thought(
                agent_thought=agent_thought, 
                tool_name=tool_call_names,
                tool_input=tool_call_inputs,
                thought=response,
                tool_invoke_meta=None,
                observation=None,
                answer=response,
                messages_ids=[],
                llm_usage=current_llm_usage
            )
            self.queue_manager.publish(QueueAgentThoughtEvent(
                agent_thought_id=agent_thought.id
            ), PublishFrom.APPLICATION_MANAGER)
            
            final_answer += response + '\n'

            # 调用工具
            tool_responses = []
            for tool_call_id, tool_call_name, tool_call_args in tool_calls:
                tool_instance = tool_instances.get(tool_call_name)
                if not tool_instance:
                    tool_response = {
                        "tool_call_id": tool_call_id,
                        "tool_call_name": tool_call_name,
                        "tool_response": f"there is not a tool named {tool_call_name}",
                        "meta": ToolInvokeMeta.error_instance(f"there is not a tool named {tool_call_name}").to_dict()
                    }
                else:
                    # 调用工具
                    tool_invoke_response, message_files, tool_invoke_meta = ToolEngine.agent_invoke(
                        tool=tool_instance,
                        tool_parameters=tool_call_args,
                        user_id=self.user_id,
                        tenant_id=self.tenant_id,
                        message=self.message,
                        invoke_from=self.application_generate_entity.invoke_from,
                        agent_tool_callback=self.agent_callback,
                    )
                    # 发布文件
                    for message_file, save_as in message_files:
                        if save_as:
                            self.variables_pool.set_file(tool_name=tool_call_name, value=message_file.id, name=save_as)

                        # 发布消息文件
                        self.queue_manager.publish(QueueMessageFileEvent(
                            message_file_id=message_file.id
                        ), PublishFrom.APPLICATION_MANAGER)
                        # 添加消息文件ids
                        message_file_ids.append(message_file.id)
                    
                    tool_response = {
                        "tool_call_id": tool_call_id,
                        "tool_call_name": tool_call_name,
                        "tool_response": tool_invoke_response,
                        "meta": tool_invoke_meta.to_dict()
                    }
                
                tool_responses.append(tool_response)
                if tool_response['tool_response'] is not None:
                    self._current_thoughts.append(
                        ToolPromptMessage(
                            content=tool_response['tool_response'],
                            tool_call_id=tool_call_id,
                            name=tool_call_name,
                        )
                    ) 

            if len(tool_responses) > 0:
                # 保存代理思考
                self.save_agent_thought(
                    agent_thought=agent_thought, 
                    tool_name=None,
                    tool_input=None,
                    thought=None, 
                    tool_invoke_meta={
                        tool_response['tool_call_name']: tool_response['meta'] 
                        for tool_response in tool_responses
                    },
                    observation={
                        tool_response['tool_call_name']: tool_response['tool_response'] 
                        for tool_response in tool_responses
                    },
                    answer=None,
                    messages_ids=message_file_ids
                )
                self.queue_manager.publish(QueueAgentThoughtEvent(
                    agent_thought_id=agent_thought.id
                ), PublishFrom.APPLICATION_MANAGER)

            # 更新prompt工具信息
            for prompt_tool in prompt_messages_tools:
                self.update_prompt_message_tool(tool_instances[prompt_tool.name], prompt_tool)

            iteration_step += 1

        self.update_db_variables(self.variables_pool, self.db_variables_pool)
        # 发布结束事件
        self.queue_manager.publish(QueueMessageEndEvent(llm_result=LLMResult(
            model=model_instance.model,
            prompt_messages=prompt_messages,
            message=AssistantPromptMessage(
                content=final_answer
            ),
            usage=llm_usage['usage'] if llm_usage['usage'] else LLMUsage.empty_usage(),
            system_fingerprint=''
        )), PublishFrom.APPLICATION_MANAGER)

    def check_tool_calls(self, llm_result_chunk: LLMResultChunk) -> bool:
        """
        检查 llm 结果块中是否存在工具调用
        
        参数:
        - llm_result_chunk: LLMResultChunk 类型，表示一个 llm 结果块，包含着可能的工具调用信息。
        
        返回值:
        - bool 类型，如果结果块中存在工具调用，则返回 True，否则返回 False。
        """
        # 检查 llm_result_chunk 中的 delta 消息是否存在 tool_calls
        if llm_result_chunk.delta.message.tool_calls:
            return True
        return False
    
    def check_blocking_tool_calls(self, llm_result: LLMResult) -> bool:
        """
        检查 llm 结果中是否存在阻塞工具调用
        
        参数:
        - llm_result: LLMResult 类型，包含 llm 的执行结果数据
        
        返回值:
        - bool 类型，如果存在阻塞工具调用则返回 True，否则返回 False
        """
        # 检查 llm_result 中是否存在 tool_calls
        if llm_result.message.tool_calls:
            return True
        return False

    def extract_tool_calls(self, llm_result_chunk: LLMResultChunk) -> Union[None, list[tuple[str, str, dict[str, Any]]]]:
        """
        从llm结果块中提取工具调用信息
        
        参数:
            llm_result_chunk (LLMResultChunk): 包含工具调用信息的结果块
            
        返回值:
            List[Tuple[str, str, Dict[str, Any]]]: [(工具调用ID, 工具调用名称, 工具调用参数)]的列表
        """
        tool_calls = []  # 初始化存储工具调用信息的列表

        # 遍历结果块中的每个工具调用消息，将每个调用的ID、名称和参数解析并添加到列表中
        for prompt_message in llm_result_chunk.delta.message.tool_calls:
            tool_calls.append((
                prompt_message.id,
                prompt_message.function.name,
                json.loads(prompt_message.function.arguments),
            ))

        return tool_calls  # 返回包含所有工具调用信息的列表
    
    def extract_blocking_tool_calls(self, llm_result: LLMResult) -> Union[None, list[tuple[str, str, dict[str, Any]]]]:
        """
        从llm结果中提取阻塞工具调用
        
        参数:
            llm_result (LLMResult): 包含工具调用信息的LLM结果对象
            
        返回值:
            List[Tuple[str, str, Dict[str, Any]]]: [(工具调用ID, 工具调用名称, 工具调用参数)]的列表
        """
        tool_calls = []  # 初始化存储工具调用信息的列表
        # 遍历llm_result中的每个工具调用消息
        for prompt_message in llm_result.message.tool_calls:
            # 将每个工具调用的ID、名称和参数（以JSON字符串形式）加载到列表中
            tool_calls.append((
                prompt_message.id,
                prompt_message.function.name,
                json.loads(prompt_message.function.arguments),
            ))

        return tool_calls  # 返回包含工具调用信息的列表

    def _init_system_message(self, prompt_template: str, prompt_messages: list[PromptMessage] = None) -> list[PromptMessage]:
        """
        初始化系统消息
        
        :param prompt_template: 提示信息模板，字符串类型
        :param prompt_messages: 提示消息列表，列表类型，每个元素是PromptMessage类型，可选
        :return: 返回提示消息列表，列表类型，每个元素是PromptMessage类型

        如果prompt_messages为空且prompt_template不为空，则返回包含单个元素（使用prompt_template创建的SystemPromptMessage对象）的列表。
        如果prompt_messages不为空，且第一个元素不是SystemPromptMessage类型，且prompt_template不为空，则在列表开头插入一个使用prompt_template创建的SystemPromptMessage对象。
        否则，直接返回传入的prompt_messages。
        """
        if not prompt_messages and prompt_template:
            # 如果prompt_messages为空，但提供了prompt_template，则返回包含单个SystemPromptMessage对象的列表
            return [
                SystemPromptMessage(content=prompt_template),
            ]
        
        if prompt_messages and not isinstance(prompt_messages[0], SystemPromptMessage) and prompt_template:
            # 如果prompt_messages不为空，但第一个元素不是SystemPromptMessage，且提供了prompt_template，则在列表开头插入一个SystemPromptMessage对象
            prompt_messages.insert(0, SystemPromptMessage(content=prompt_template))

        return prompt_messages

    def _organize_user_query(self, query,  prompt_messages: list[PromptMessage] = None) -> list[PromptMessage]:
        """
        组织用户查询

        :param query: 用户的查询内容
        :param prompt_messages: 提示消息列表，默认为None，用于存储整理后的提示消息
        :type prompt_messages: list[PromptMessage]
        :return: 整理后的提示消息列表
        :rtype: list[PromptMessage]
        """
        if self.files:
            # 如果存在文件对象，将查询内容和每个文件对象的提示消息内容组织成一个列表
            prompt_message_contents = [TextPromptMessageContent(data=query)]
            for file_obj in self.files:
                prompt_message_contents.append(file_obj.prompt_message_content)

            # 将上述内容作为一个用户提示消息添加到提示消息列表中
            prompt_messages.append(UserPromptMessage(content=prompt_message_contents))
        else:
            # 如果不存在文件对象，直接将查询内容作为一个用户提示消息添加到提示消息列表中
            prompt_messages.append(UserPromptMessage(content=query))

        return prompt_messages
    
    def _clear_user_prompt_image_messages(self, prompt_messages: list[PromptMessage]) -> list[PromptMessage]:
        """
        清除用户提示消息中的图片消息。
        
        由于目前GPT在第一轮迭代中同时支持fc和vision，我们需要在第一轮迭代中从提示消息中移除图片消息。
        
        参数:
        - prompt_messages: 提示消息列表，类型为`list[PromptMessage]`，其中包含了用户交互中的各种消息。
        
        返回值:
        - 清理后的提示消息列表，图片消息将被替换为'[image]'字符串。
        """
        prompt_messages = deepcopy(prompt_messages)  # 深拷贝提示消息列表，以避免修改原始列表

        for prompt_message in prompt_messages:
            if isinstance(prompt_message, UserPromptMessage):  # 判断是否为用户发出的提示消息
                if isinstance(prompt_message.content, list):  # 确认消息内容为列表形式
                    # 将列表中的每条消息内容处理后合并为字符串，图片消息会被替换为'[image]'字符串
                    prompt_message.content = '\n'.join([
                        content.data if content.type == PromptMessageContentType.TEXT else 
                        '[image]' if content.type == PromptMessageContentType.IMAGE else
                        '[file]' 
                        for content in prompt_message.content 
                    ])

        return prompt_messages

    def _organize_prompt_messages(self):
        prompt_template = self.app_config.prompt_template.simple_prompt_template or ''
        self.history_prompt_messages = self._init_system_message(prompt_template, self.history_prompt_messages)
        query_prompt_messages = self._organize_user_query(self.query, [])

        self.history_prompt_messages = AgentHistoryPromptTransform(
            model_config=self.model_config,
            prompt_messages=[*query_prompt_messages, *self._current_thoughts],
            history_messages=self.history_prompt_messages,
            memory=self.memory
        ).get_prompt()

        prompt_messages = [
            *self.history_prompt_messages,
            *query_prompt_messages,
            *self._current_thoughts
        ]
        if len(self._current_thoughts) != 0:
            # clear messages after the first iteration
            prompt_messages = self._clear_user_prompt_image_messages(prompt_messages)
        return prompt_messages
