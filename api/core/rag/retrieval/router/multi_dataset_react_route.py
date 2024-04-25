from collections.abc import Generator, Sequence
from typing import Union

from core.app.entities.app_invoke_entities import ModelConfigWithCredentialsEntity
from core.model_manager import ModelInstance
from core.model_runtime.entities.llm_entities import LLMUsage
from core.model_runtime.entities.message_entities import PromptMessage, PromptMessageRole, PromptMessageTool
from core.prompt.advanced_prompt_transform import AdvancedPromptTransform
from core.prompt.entities.advanced_prompt_entities import ChatModelMessage, CompletionModelPromptTemplate
from core.rag.retrieval.output_parser.react_output import ReactAction
from core.rag.retrieval.output_parser.structured_chat import StructuredChatOutputParser
from core.workflow.nodes.llm.llm_node import LLMNode

PREFIX = """Respond to the human as helpfully and accurately as possible. You have access to the following tools:"""

SUFFIX = """Begin! Reminder to ALWAYS respond with a valid json blob of a single action. Use tools if necessary. Respond directly if appropriate. Format is Action:```$JSON_BLOB```then Observation:.
Thought:"""

FORMAT_INSTRUCTIONS = """Use a json blob to specify a tool by providing an action key (tool name) and an action_input key (tool input).
The nouns in the format of "Thought", "Action", "Action Input", "Final Answer" must be expressed in English.
Valid "action" values: "Final Answer" or {tool_names}

Provide only ONE action per $JSON_BLOB, as shown:

```
{{
  "action": $TOOL_NAME,
  "action_input": $INPUT
}}
```

Follow this format:

Question: input question to answer
Thought: consider previous and subsequent steps
Action:
```
$JSON_BLOB
```
Observation: action result
... (repeat Thought/Action/Observation N times)
Thought: I know what to respond
Action:
```
{{
  "action": "Final Answer",
  "action_input": "Final response to human"
}}
```"""


class ReactMultiDatasetRouter:

    def invoke(
            self,
            query: str,  # 查询字符串
            dataset_tools: list[PromptMessageTool],  # 数据集工具列表
            model_config: ModelConfigWithCredentialsEntity,  # 带有凭证的模型配置实体
            model_instance: ModelInstance,  # 模型实例
            user_id: str,  # 用户ID
            tenant_id: str  # 租户ID
    ) -> Union[str, None]:
        """
        根据输入决定执行什么操作。
        返回值：
            指定使用哪个工具的动作。
        """
        if len(dataset_tools) == 0:
            return None  # 如果数据集工具列表为空，则返回None
        elif len(dataset_tools) == 1:
            return dataset_tools[0].name  # 如果只有一个数据集工具，则返回该工具的名称

        try:
            # 尝试使用_react_invoke方法根据查询、模型配置、模型实例、工具列表、用户ID和租户ID进行调用
            return self._react_invoke(query=query, model_config=model_config,
                                    model_instance=model_instance,
                                    tools=dataset_tools, user_id=user_id, tenant_id=tenant_id)
        except Exception as e:
            return None  # 如果发生异常，则返回None

    def _react_invoke(
            self,
            query: str,  # 用户的查询字符串
            model_config: ModelConfigWithCredentialsEntity,  # 模型配置，包含认证信息
            model_instance: ModelInstance,  # 模型实例
            tools: Sequence[PromptMessageTool],  # 辅助工具列表
            user_id: str,  # 用户ID
            tenant_id: str,  # 租户ID
            prefix: str = PREFIX,  # 提示信息前缀
            suffix: str = SUFFIX,  # 提示信息后缀
            format_instructions: str = FORMAT_INSTRUCTIONS,  # 格式化指令
    ) -> Union[str, None]:
        """
        调用模型进行反应，并返回相应的工具。

        根据模型配置（chat模式或非chat模式），创建相应的提示信息，然后调用模型实例来处理这个提示信息，
        并解析模型的输出，以决定是否需要采取某个辅助工具的动作。

        :param query: 用户的查询字符串。
        :param model_config: 包含模型配置和认证信息的实体。
        :param model_instance: 模型实例，用于处理提示信息。
        :param tools: 用于辅助响应的工具列表。
        :param user_id: 用户的唯一标识。
        :param tenant_id: 租户的唯一标识。
        :param prefix: 提示信息的前缀，默认为PREFIX常量。
        :param suffix: 提示信息的后缀，默认为SUFFIX常量。
        :param format_instructions: 格式化指令，默认为FORMAT_INSTRUCTIONS常量。
        :return: 如果决定采取某个辅助工具的动作，则返回该工具的标识；否则返回None。
        """
        if model_config.mode == "chat":
            # 如果是chat模式，创建chat风格的提示信息
            prompt = self.create_chat_prompt(
                query=query,
                tools=tools,
                prefix=prefix,
                suffix=suffix,
                format_instructions=format_instructions,
            )
        else:
            # 非chat模式，创建完成风格的提示信息
            prompt = self.create_completion_prompt(
                tools=tools,
                prefix=prefix,
                format_instructions=format_instructions,
            )
        stop = ['Observation:']
        # 初始化高级提示转换器
        prompt_transform = AdvancedPromptTransform()
        # 根据提供的参数获取提示信息
        prompt_messages = prompt_transform.get_prompt(
            prompt_template=prompt,
            inputs={},
            query='',
            files=[],
            context='',
            memory_config=None,
            memory=None,
            model_config=model_config
        )
        # 调用LLM（Large Language Model），并获取结果文本和使用情况
        result_text, usage = self._invoke_llm(
            completion_param=model_config.parameters,
            model_instance=model_instance,
            prompt_messages=prompt_messages,
            stop=stop,
            user_id=user_id,
            tenant_id=tenant_id
        )
        # 初始化结构化聊天输出解析器
        output_parser = StructuredChatOutputParser()
        # 解析结果文本，获取反应决策
        react_decision = output_parser.parse(result_text)
        # 判断解析结果类型，并返回相应的工具
        if isinstance(react_decision, ReactAction):
            return react_decision.tool
        return None

    def _invoke_llm(self, completion_param: dict,
                    model_instance: ModelInstance,
                    prompt_messages: list[PromptMessage],
                    stop: list[str], user_id: str, tenant_id: str
                    ) -> tuple[str, LLMUsage]:
        """
        调用大型语言模型
        :param model_instance: 模型实例
        :param prompt_messages: 提示信息列表
        :param stop: 停止条件列表
        :param user_id: 用户ID
        :param tenant_id: 租户ID
        :return: 返回一个元组，包含生成的文本和LLM使用情况
        """
        # 调用大型语言模型，传入相关参数
        invoke_result = model_instance.invoke_llm(
            prompt_messages=prompt_messages,
            model_parameters=completion_param,
            stop=stop,
            stream=True,
            user=user_id,
        )

        # 处理调用结果
        text, usage = self._handle_invoke_result(
            invoke_result=invoke_result
        )

        # 扣除配额
        LLMNode.deduct_llm_quota(tenant_id=tenant_id, model_instance=model_instance, usage=usage)

        return text, usage

    def _handle_invoke_result(self, invoke_result: Generator) -> tuple[str, LLMUsage]:
        """
        处理调用结果
        :param invoke_result: 调用结果，是一个生成器对象
        :return: 返回一个元组，包含完整的文本内容和LLMUsage使用情况对象
        """
        # 初始化变量
        model = None
        prompt_messages = []
        full_text = ''
        usage = None

        # 遍历调用结果中的每一个结果项
        for result in invoke_result:
            text = result.delta.message.content  # 提取文本内容
            full_text += text  # 累加完整文本

            # 初始化或更新model、prompt_messages和usage信息
            if not model:
                model = result.model
            if not prompt_messages:
                prompt_messages = result.prompt_messages
            if not usage and result.delta.usage:
                usage = result.delta.usage

        # 如果没有获取到usage信息，则创建一个空的LLMUsage对象
        if not usage:
            usage = LLMUsage.empty_usage()

        # 返回完整文本和usage信息
        return full_text, usage

    def create_chat_prompt(
            self,
            query: str,
            tools: Sequence[PromptMessageTool],
            prefix: str = PREFIX,
            suffix: str = SUFFIX,
            format_instructions: str = FORMAT_INSTRUCTIONS,
    ) -> list[ChatModelMessage]:
        """
        创建聊天提示信息。
        
        参数:
        - query: str，用户查询的内容。
        - tools: Sequence[PromptMessageTool]，一系列可用于查询的工具。
        - prefix: str = PREFIX，默认前缀。
        - suffix: str = SUFFIX，默认后缀。
        - format_instructions: str = FORMAT_INSTRUCTIONS，默认格式化说明。
        
        返回值:
        - list[ChatModelMessage]，包含系统和用户提示信息的消息列表。
        """
        # 为每个工具生成字符串信息
        tool_strings = []
        for tool in tools:
            tool_strings.append(
                f"{tool.name}: {tool.description}, args: {{'query': {{'title': 'Query', 'description': 'Query for the dataset to be used to retrieve the dataset.', 'type': 'string'}}}}")
        # 将工具字符串格式化为一个段落
        formatted_tools = "\n".join(tool_strings)
        # 获取唯一的工具名称集合
        unique_tool_names = set(tool.name for tool in tools)
        # 将唯一工具名称格式化为字符串，用于指令中
        tool_names = ", ".join('"' + name + '"' for name in unique_tool_names)
        # 使用工具名称更新格式化说明
        format_instructions = format_instructions.format(tool_names=tool_names)
        # 将前缀、工具信息、格式化说明和后缀组合成最终模板
        template = "\n\n".join([prefix, formatted_tools, format_instructions, suffix])
        # 创建提示消息列表
        prompt_messages = []
        # 添加系统提示消息
        system_prompt_messages = ChatModelMessage(
            role=PromptMessageRole.SYSTEM,
            text=template
        )
        prompt_messages.append(system_prompt_messages)
        # 添加用户提示消息
        user_prompt_message = ChatModelMessage(
            role=PromptMessageRole.USER,
            text=query
        )
        prompt_messages.append(user_prompt_message)
        return prompt_messages

    def create_completion_prompt(
            self,
            tools: Sequence[PromptMessageTool],
            prefix: str = PREFIX,
            format_instructions: str = FORMAT_INSTRUCTIONS,
    ) -> CompletionModelPromptTemplate:
        """
        创建一个类似于零样本代理的提示。

        参数:
            tools: 代理将能访问的工具列表，用于格式化提示信息。
            prefix: 在工具列表之前要放置的字符串。
        返回:
            一个PromptTemplate对象，其模板从这里拼接而成。
        """
        # 准备提示信息的后缀，包括开始提示、回应格式说明和问题、思考与回答的格式
        suffix = """Begin! Reminder to ALWAYS respond with a valid json blob of a single action. Use tools if necessary. Respond directly if appropriate. Format is Action:```$JSON_BLOB```then Observation:.
Question: {input}
Thought: {agent_scratchpad}
"""

        # 将工具列表格式化为字符串，每个工具一行，包含名称和描述
        tool_strings = "\n".join([f"{tool.name}: {tool.description}" for tool in tools])
        # 将工具名称列表格式化为一个逗号分隔的字符串，用于指令格式化
        tool_names = ", ".join([tool.name for tool in tools])
        # 使用工具名称列表格式化指令字符串
        format_instructions = format_instructions.format(tool_names=tool_names)
        # 将前缀、工具字符串、格式化指令和后缀拼接成最终的模板
        template = "\n\n".join([prefix, tool_strings, format_instructions, suffix])
        # 返回构建的模板
        return CompletionModelPromptTemplate(text=template)
