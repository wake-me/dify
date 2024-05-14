from typing import Optional, Union

from core.app.entities.app_invoke_entities import ModelConfigWithCredentialsEntity
from core.file.file_obj import FileVar
from core.helper.code_executor.jinja2_formatter import Jinja2Formatter
from core.memory.token_buffer_memory import TokenBufferMemory
from core.model_runtime.entities.message_entities import (
    AssistantPromptMessage,
    PromptMessage,
    PromptMessageRole,
    SystemPromptMessage,
    TextPromptMessageContent,
    UserPromptMessage,
)
from core.prompt.entities.advanced_prompt_entities import ChatModelMessage, CompletionModelPromptTemplate, MemoryConfig
from core.prompt.prompt_transform import PromptTransform
from core.prompt.simple_prompt_transform import ModelMode
from core.prompt.utils.prompt_template_parser import PromptTemplateParser


class AdvancedPromptTransform(PromptTransform):
    """
    用于工作流LLM节点的高级提示转换。
    """

    def __init__(self, with_variable_tmpl: bool = False) -> None:
        """
        初始化AdvancedPromptTransform对象。

        参数:
        with_variable_tmpl (bool): 是否使用变量模板，默认为False。
        """
        self.with_variable_tmpl = with_variable_tmpl

    def get_prompt(self, prompt_template: Union[list[ChatModelMessage], CompletionModelPromptTemplate],
                   inputs: dict,
                   query: str,
                   files: list[FileVar],
                   context: Optional[str],
                   memory_config: Optional[MemoryConfig],
                   memory: Optional[TokenBufferMemory],
                   model_config: ModelConfigWithCredentialsEntity,
                   query_prompt_template: Optional[str] = None) -> list[PromptMessage]:
        inputs = {key: str(value) for key, value in inputs.items()}

        prompt_messages = []

        model_mode = ModelMode.value_of(model_config.mode)
        if model_mode == ModelMode.COMPLETION:
            # 处理完成模型的提示消息
            prompt_messages = self._get_completion_model_prompt_messages(
                prompt_template=prompt_template,
                inputs=inputs,
                query=query,
                files=files,
                context=context,
                memory_config=memory_config,
                memory=memory,
                model_config=model_config
            )
        elif model_mode == ModelMode.CHAT:
            # 处理聊天模型的提示消息
            prompt_messages = self._get_chat_model_prompt_messages(
                prompt_template=prompt_template,
                inputs=inputs,
                query=query,
                query_prompt_template=query_prompt_template,
                files=files,
                context=context,
                memory_config=memory_config,
                memory=memory,
                model_config=model_config
            )

        return prompt_messages

    def _get_completion_model_prompt_messages(self,
                                            prompt_template: CompletionModelPromptTemplate,
                                            inputs: dict,
                                            query: Optional[str],
                                            files: list[FileVar],
                                            context: Optional[str],
                                            memory_config: Optional[MemoryConfig],
                                            memory: Optional[TokenBufferMemory],
                                            model_config: ModelConfigWithCredentialsEntity) -> list[PromptMessage]:
        """
        获取完成模型的提示消息。
        
        参数:
        - prompt_template: CompletionModelPromptTemplate，提示模板对象，包含模板文本。
        - inputs: dict，输入字典，包含模板中需要的变量键值对。
        - query: Optional[str]，查询字符串，如果提供，则将其纳入提示信息中。
        - files: list[FileVar]，文件变量列表，如果有文件需要包含在提示中，则提供。
        - context: Optional[str]，上下文字符串，用于设置模板中的上下文变量。
        - memory_config: Optional[MemoryConfig]，内存配置对象，用于配置记忆功能。
        - memory: Optional[TokenBufferMemory]，令牌缓冲区内存对象，用于存储和检索历史输入。
        - model_config: ModelConfigWithCredentialsEntity，模型配置对象，包含模型的配置信息和认证信息。
        
        返回值:
        - list[PromptMessage]，提示消息列表，每个消息可以包含文本和文件内容。
        """
        
        # 初始化原始提示文本
        raw_prompt = prompt_template.text

        prompt_messages = []

        if prompt_template.edition_type == 'basic' or not prompt_template.edition_type:
            prompt_template = PromptTemplateParser(template=raw_prompt, with_variable_tmpl=self.with_variable_tmpl)
            prompt_inputs = {k: inputs[k] for k in prompt_template.variable_keys if k in inputs}

            prompt_inputs = self._set_context_variable(context, prompt_template, prompt_inputs)

            if memory and memory_config:
                role_prefix = memory_config.role_prefix
                prompt_inputs = self._set_histories_variable(
                    memory=memory,
                    memory_config=memory_config,
                    raw_prompt=raw_prompt,
                    role_prefix=role_prefix,
                    prompt_template=prompt_template,
                    prompt_inputs=prompt_inputs,
                    model_config=model_config
                )

            if query:
                prompt_inputs = self._set_query_variable(query, prompt_template, prompt_inputs)

            prompt = prompt_template.format(
                prompt_inputs
            )
        else:
            prompt = raw_prompt
            prompt_inputs = inputs

            prompt = Jinja2Formatter.format(prompt, prompt_inputs)

        # 如果有文件，将文件内容和提示信息一起封装成消息
        if files:
            prompt_message_contents = [TextPromptMessageContent(data=prompt)]
            for file in files:
                prompt_message_contents.append(file.prompt_message_content)

            prompt_messages.append(UserPromptMessage(content=prompt_message_contents))
        else:
            # 如果没有文件，直接将提示信息封装成消息
            prompt_messages.append(UserPromptMessage(content=prompt))

        return prompt_messages

    def _get_chat_model_prompt_messages(self,
                                        prompt_template: list[ChatModelMessage],
                                        inputs: dict,
                                        query: Optional[str],
                                        files: list[FileVar],
                                        context: Optional[str],
                                        memory_config: Optional[MemoryConfig],
                                        memory: Optional[TokenBufferMemory],
                                        model_config: ModelConfigWithCredentialsEntity,
                                        query_prompt_template: Optional[str] = None) -> list[PromptMessage]:
        """
        获取聊天模型的提示消息。
        
        参数:
        - prompt_template: 提示模板列表，每个模板包含要发出的消息文本。
        - inputs: 输入字典，包含用于填充模板的变量。
        - query: 查询字符串，可能为空，用于提供用户查询。
        - files: 文件列表，可能为空，表示要附加的文件。
        - context: 上下文字符串，可能为空，用于提供对话上下文。
        - memory_config: 内存配置，用于管理对话状态。
        - memory: 令牌缓冲区内存，用于存储对话历史等信息。
        - model_config: 模型配置，包含模型的认证信息和配置。
        
        返回值:
        - 提示消息列表，每个消息可以是用户、系统或助手角色。
        """
        
        # 初始化原始提示列表和处理后的提示消息列表
        raw_prompt_list = prompt_template
        prompt_messages = []

        # 遍历原始提示列表，生成具体的提示消息
        for prompt_item in raw_prompt_list:
            raw_prompt = prompt_item.text

            if prompt_item.edition_type == 'basic' or not prompt_item.edition_type:
                prompt_template = PromptTemplateParser(template=raw_prompt, with_variable_tmpl=self.with_variable_tmpl)
                prompt_inputs = {k: inputs[k] for k in prompt_template.variable_keys if k in inputs}

                prompt_inputs = self._set_context_variable(context, prompt_template, prompt_inputs)

                prompt = prompt_template.format(
                    prompt_inputs
                )
            elif prompt_item.edition_type == 'jinja2':
                prompt = raw_prompt
                prompt_inputs = inputs

                prompt = Jinja2Formatter.format(prompt, prompt_inputs)
            else:
                raise ValueError(f'Invalid edition type: {prompt_item.edition_type}')

            # 根据角色生成具体的提示消息对象
            if prompt_item.role == PromptMessageRole.USER:
                prompt_messages.append(UserPromptMessage(content=prompt))
            elif prompt_item.role == PromptMessageRole.SYSTEM and prompt:
                prompt_messages.append(SystemPromptMessage(content=prompt))
            elif prompt_item.role == PromptMessageRole.ASSISTANT:
                prompt_messages.append(AssistantPromptMessage(content=prompt))

        if query and query_prompt_template:
            prompt_template = PromptTemplateParser(
                template=query_prompt_template,
                with_variable_tmpl=self.with_variable_tmpl
            )
            prompt_inputs = {k: inputs[k] for k in prompt_template.variable_keys if k in inputs}
            prompt_inputs['#sys.query#'] = query

            prompt_inputs = self._set_context_variable(context, prompt_template, prompt_inputs)

            query = prompt_template.format(
                prompt_inputs
            )

        if memory and memory_config:
            prompt_messages = self._append_chat_histories(memory, memory_config, prompt_messages, model_config)

            # 处理附加文件的情况
            if files:
                prompt_message_contents = [TextPromptMessageContent(data=query)]
                for file in files:
                    prompt_message_contents.append(file.prompt_message_content)

                prompt_messages.append(UserPromptMessage(content=prompt_message_contents))
            else:
                prompt_messages.append(UserPromptMessage(content=query))
        elif files:
            # 处理只有文件而没有查询字符串的情况
            if not query:
                # 获取最后一条消息并添加文件
                last_message = prompt_messages[-1] if prompt_messages else None
                if last_message and last_message.role == PromptMessageRole.USER:
                    prompt_message_contents = [TextPromptMessageContent(data=last_message.content)]
                    for file in files:
                        prompt_message_contents.append(file.prompt_message_content)

                    last_message.content = prompt_message_contents
                else:
                    prompt_message_contents = [TextPromptMessageContent(data='')]  # 为空的查询字符串
                    for file in files:
                        prompt_message_contents.append(file.prompt_message_content)

                    prompt_messages.append(UserPromptMessage(content=prompt_message_contents))
            else:
                # 为查询字符串添加文件
                prompt_message_contents = [TextPromptMessageContent(data=query)]
                for file in files:
                    prompt_message_contents.append(file.prompt_message_content)

                prompt_messages.append(UserPromptMessage(content=prompt_message_contents))
        elif query:
            # 如果只有查询字符串而没有文件，添加到消息列表
            prompt_messages.append(UserPromptMessage(content=query))

        return prompt_messages

    def _set_context_variable(self, context: str, prompt_template: PromptTemplateParser, prompt_inputs: dict) -> dict:
        """
        设置上下文变量。
        
        :param context: 上下文字符串。
        :param prompt_template: 提示模板解析器实例。
        :param prompt_inputs: 包含提示输入的字典。
        :return: 更新后的提示输入字典。
        """
        if '#context#' in prompt_template.variable_keys:
            # 如果模板中包含#context#变量，根据context是否有值设置相应的值
            if context:
                prompt_inputs['#context#'] = context
            else:
                prompt_inputs['#context#'] = ''

        return prompt_inputs

    def _set_query_variable(self, query: str, prompt_template: PromptTemplateParser, prompt_inputs: dict) -> dict:
        """
        设置查询变量。
        
        :param query: 查询字符串。
        :param prompt_template: 提示模板解析器实例。
        :param prompt_inputs: 包含提示输入的字典。
        :return: 更新后的提示输入字典。
        """
        if '#query#' in prompt_template.variable_keys:
            # 如果模板中包含#query#变量，根据query是否有值设置相应的值
            if query:
                prompt_inputs['#query#'] = query
            else:
                prompt_inputs['#query#'] = ''

        return prompt_inputs

    def _set_histories_variable(self, memory: TokenBufferMemory,
                                memory_config: MemoryConfig,
                                raw_prompt: str,
                                role_prefix: MemoryConfig.RolePrefix,
                                prompt_template: PromptTemplateParser,
                                prompt_inputs: dict,
                                model_config: ModelConfigWithCredentialsEntity) -> dict:
        """
        设置历史记录变量。
        
        :param memory: 用于存储对话历史的TokenBufferMemory实例。
        :param memory_config: 内存配置。
        :param raw_prompt: 原始提示字符串。
        :param role_prefix: 角色前缀配置。
        :param prompt_template: 提示模板解析器实例。
        :param prompt_inputs: 包含提示输入的字典。
        :param model_config: 模型配置，包含认证信息。
        :return: 更新后的提示输入字典。
        """
        if '#histories#' in prompt_template.variable_keys:
            # 如果模板中包含#histories#变量，根据memory是否有值设置历史记录
            if memory:
                inputs = {'#histories#': '', **prompt_inputs}
                # 重新解析模板，更新prompt_inputs
                prompt_template = PromptTemplateParser(template=raw_prompt, with_variable_tmpl=self.with_variable_tmpl)
                prompt_inputs = {k: inputs[k] for k in prompt_template.variable_keys if k in inputs}
                # 计算剩余token数量
                tmp_human_message = UserPromptMessage(
                    content=prompt_template.format(prompt_inputs)
                )

                rest_tokens = self._calculate_rest_token([tmp_human_message], model_config)

                # 从内存中获取历史消息
                histories = self._get_history_messages_from_memory(
                    memory=memory,
                    memory_config=memory_config,
                    max_token_limit=rest_tokens,
                    human_prefix=role_prefix.user,
                    ai_prefix=role_prefix.assistant
                )
                prompt_inputs['#histories#'] = histories
            else:
                prompt_inputs['#histories#'] = ''

        return prompt_inputs