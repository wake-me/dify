import enum
import json
import os
from typing import Optional

from core.app.app_config.entities import PromptTemplateEntity
from core.app.entities.app_invoke_entities import ModelConfigWithCredentialsEntity
from core.file.file_obj import FileVar
from core.memory.token_buffer_memory import TokenBufferMemory
from core.model_runtime.entities.message_entities import (
    PromptMessage,
    SystemPromptMessage,
    TextPromptMessageContent,
    UserPromptMessage,
)
from core.prompt.entities.advanced_prompt_entities import MemoryConfig
from core.prompt.prompt_transform import PromptTransform
from core.prompt.utils.prompt_template_parser import PromptTemplateParser
from models.model import AppMode


class ModelMode(enum.Enum):
    # 定义模型模式的枚举类
    COMPLETION = 'completion'  # 完成模式
    CHAT = 'chat'  # 聊天模式

    @classmethod
    def value_of(cls, value: str) -> 'ModelMode':
        """
        根据字符串值获取枚举实例。

        :param value: 模式对应的字符串值。
        :return: 对应的模式枚举实例。
        """
        for mode in cls:
            if mode.value == value:
                return mode
        # 如果给定的值没有对应的枚举实例，则抛出异常
        raise ValueError(f'invalid mode value {value}')

# 这里是一个空字典，似乎用于存储提示文件的内容。
# 具体用途可能依赖于后续代码，该字典key为文件名，value为文件内容。
prompt_file_contents = {}


class SimplePromptTransform(PromptTransform):
    """
    用于聊天应用基础模式的简单提示转换。
    """

    def get_prompt(self,
                   app_mode: AppMode,
                   prompt_template_entity: PromptTemplateEntity,
                   inputs: dict,
                   query: str,
                   files: list[FileVar],
                   context: Optional[str],
                   memory: Optional[TokenBufferMemory],
                   model_config: ModelConfigWithCredentialsEntity) -> \
            tuple[list[PromptMessage], Optional[list[str]]]:
        """
        根据应用模式、模型配置和输入获取提示消息。

        :param app_mode: 应用模式。
        :param prompt_template_entity: 提示模板实体，包含简单提示模板。
        :param inputs: 输入参数字典。
        :param query: 查询字符串。
        :param files: 文件列表。
        :param context: 上下文字符串。
        :param memory: 令牌缓冲区内存，用于存储会话历史等。
        :param model_config: 带有凭证的模型配置实体。
        :return: 提示消息列表和停止标志列表的元组。
        """
        model_mode = ModelMode.value_of(model_config.mode)
        if model_mode == ModelMode.CHAT:
            # 如果是聊天模式，获取聊天模型的提示消息
            prompt_messages, stops = self._get_chat_model_prompt_messages(
                app_mode=app_mode,
                pre_prompt=prompt_template_entity.simple_prompt_template,
                inputs=inputs,
                query=query,
                files=files,
                context=context,
                memory=memory,
                model_config=model_config
            )
        else:
            # 否则，获取完成模型的提示消息
            prompt_messages, stops = self._get_completion_model_prompt_messages(
                app_mode=app_mode,
                pre_prompt=prompt_template_entity.simple_prompt_template,
                inputs=inputs,
                query=query,
                files=files,
                context=context,
                memory=memory,
                model_config=model_config
            )

        return prompt_messages, stops

    def get_prompt_str_and_rules(self, app_mode: AppMode,
                                 model_config: ModelConfigWithCredentialsEntity,
                                 pre_prompt: str,
                                 inputs: dict,
                                 query: Optional[str] = None,
                                 context: Optional[str] = None,
                                 histories: Optional[str] = None,
                                 ) -> tuple[str, dict]:
        """
        根据给定的参数获取格式化后的提示字符串和规则。

        :param app_mode: 应用模式。
        :param model_config: 带有凭证的模型配置实体。
        :param pre_prompt: 前置提示模板。
        :param inputs: 输入参数字典。
        :param query: 查询字符串（可选）。
        :param context: 上下文字符串（可选）。
        :param histories: 会话历史字符串（可选）。
        :return: 提示字符串和提示规则的元组。
        """
        # 获取提示模板配置
        prompt_template_config = self.get_prompt_template(
            app_mode=app_mode,
            provider=model_config.provider,
            model=model_config.model,
            pre_prompt=pre_prompt,
            has_context=context is not None,
            query_in_prompt=query is not None,
            with_memory_prompt=histories is not None
        )

        # 从输入中筛选出提示模板所需的变量
        variables = {k: inputs[k] for k in prompt_template_config['custom_variable_keys'] if k in inputs}

        # 处理特殊的变量替换
        for v in prompt_template_config['special_variable_keys']:
            if v == '#context#':
                variables['#context#'] = context if context else ''
            elif v == '#query#':
                variables['#query#'] = query if query else ''
            elif v == '#histories#':
                variables['#histories#'] = histories if histories else ''

        # 格式化提示模板并返回
        prompt_template = prompt_template_config['prompt_template']
        prompt = prompt_template.format(variables)

        return prompt, prompt_template_config['prompt_rules']

    def get_prompt_template(self, app_mode: AppMode,
                            provider: str,
                            model: str,
                            pre_prompt: str,
                            has_context: bool,
                            query_in_prompt: bool,
                            with_memory_prompt: bool = False) -> dict:
        """
        根据给定的参数生成一个提示模板。

        参数:
        app_mode: AppMode 类型，应用模式。
        provider: 字符串，提供者名称。
        model: 字符串，模型名称。
        pre_prompt: 字符串，前置提示文本。
        has_context: 布尔值，是否有上下文。
        query_in_prompt: 布尔值，是否在提示中包含查询。
        with_memory_prompt: 布尔值，是否包含记忆中的提示，默认为 False。

        返回值:
        一个字典，包含提示模板的解析结果，包括定制变量键、特殊变量键和提示规则。

        """

        # 获取基于应用模式、提供者和模型的提示规则
        prompt_rules = self._get_prompt_rule(
            app_mode=app_mode,
            provider=provider,
            model=model
        )

        custom_variable_keys = []  # 定制变量键列表
        special_variable_keys = []  # 特殊变量键列表

        prompt = ''  # 初始化提示文本
        # 根据系统提示顺序生成提示文本
        for order in prompt_rules['system_prompt_orders']:
            if order == 'context_prompt' and has_context:
                prompt += prompt_rules['context_prompt']
                special_variable_keys.append('#context#')
            elif order == 'pre_prompt' and pre_prompt:
                prompt += pre_prompt + '\n'
                # 解析前置提示模板，获取定制变量键
                pre_prompt_template = PromptTemplateParser(template=pre_prompt)
                custom_variable_keys = pre_prompt_template.variable_keys
            elif order == 'histories_prompt' and with_memory_prompt:
                prompt += prompt_rules['histories_prompt']
                special_variable_keys.append('#histories#')

        # 如果需要，在提示中添加查询
        if query_in_prompt:
            prompt += prompt_rules['query_prompt'] if 'query_prompt' in prompt_rules else '{{#query#}}'
            special_variable_keys.append('#query#')

        return {
            "prompt_template": PromptTemplateParser(template=prompt),
            "custom_variable_keys": custom_variable_keys,
            "special_variable_keys": special_variable_keys,
            "prompt_rules": prompt_rules
        }

    def _get_chat_model_prompt_messages(self, app_mode: AppMode,
                                            pre_prompt: str,
                                            inputs: dict,
                                            query: str,
                                            context: Optional[str],
                                            files: list[FileVar],
                                            memory: Optional[TokenBufferMemory],
                                            model_config: ModelConfigWithCredentialsEntity) \
                -> tuple[list[PromptMessage], Optional[list[str]]]:
            """
            获取聊天模型的提示消息。

            参数:
            app_mode - 应用模式。
            pre_prompt - 预提示文本。
            inputs - 输入字典。
            query - 查询字符串。
            context - 上下文信息，可选。
            files - 文件列表。
            memory - 令牌缓冲区记忆，可选。
            model_config - 带有凭证的模型配置实体。

            返回值:
            返回一个包含提示消息的元组，以及一个可选的字符串列表。
            """

            prompt_messages = []

            # 获取提示信息
            prompt, _ = self.get_prompt_str_and_rules(
                app_mode=app_mode,
                model_config=model_config,
                pre_prompt=pre_prompt,
                inputs=inputs,
                query=None,
                context=context
            )

            if prompt and query:
                prompt_messages.append(SystemPromptMessage(content=prompt))

            # 如果存在记忆体，则追加聊天历史
            if memory:
                prompt_messages = self._append_chat_histories(
                    memory=memory,
                    memory_config=MemoryConfig(
                        window=MemoryConfig.WindowConfig(
                            enabled=False,
                        )
                    ),
                    prompt_messages=prompt_messages,
                    model_config=model_config
                )

            # 根据查询条件添加用户消息
            if query:
                prompt_messages.append(self.get_last_user_message(query, files))
            else:
                prompt_messages.append(self.get_last_user_message(prompt, files))

            return prompt_messages, None

    def _get_completion_model_prompt_messages(self, app_mode: AppMode,
                                                pre_prompt: str,
                                                inputs: dict,
                                                query: str,
                                                context: Optional[str],
                                                files: list[FileVar],
                                                memory: Optional[TokenBufferMemory],
                                                model_config: ModelConfigWithCredentialsEntity) \
                -> tuple[list[PromptMessage], Optional[list[str]]]:
            """
            获取完成模型的提示信息和停止符。

            参数:
            app_mode: 应用模式。
            pre_prompt: 预提示文本。
            inputs: 输入字典。
            query: 查询字符串。
            context: 上下文信息，可选。
            files: 文件列表。
            memory: 令牌缓冲区记忆，可选。
            model_config: 带有凭证的模型配置实体。

            返回值:
            提示信息列表和可选的停止符列表的元组。
            """
            # 获取初始提示和规则
            prompt, prompt_rules = self.get_prompt_str_and_rules(
                app_mode=app_mode,
                model_config=model_config,
                pre_prompt=pre_prompt,
                inputs=inputs,
                query=query,
                context=context
            )

            if memory:
                # 利用记忆来调整提示信息
                tmp_human_message = UserPromptMessage(
                    content=prompt
                )

                rest_tokens = self._calculate_rest_token([tmp_human_message], model_config)
                # 从记忆中获取历史消息
                histories = self._get_history_messages_from_memory(
                    memory=memory,
                    memory_config=MemoryConfig(
                        window=MemoryConfig.WindowConfig(
                            enabled=False,
                        )
                    ),
                    max_token_limit=rest_tokens,
                    human_prefix=prompt_rules['human_prefix'] if 'human_prefix' in prompt_rules else 'Human',
                    ai_prefix=prompt_rules['assistant_prefix'] if 'assistant_prefix' in prompt_rules else 'Assistant'
                )

                # 基于历史消息重新获取提示和规则
                prompt, prompt_rules = self.get_prompt_str_and_rules(
                    app_mode=app_mode,
                    model_config=model_config,
                    pre_prompt=pre_prompt,
                    inputs=inputs,
                    query=query,
                    context=context,
                    histories=histories
                )

            # 处理停止符
            stops = prompt_rules.get('stops')
            if stops is not None and len(stops) == 0:
                stops = None

            return [self.get_last_user_message(prompt, files)], stops

    def get_last_user_message(self, prompt: str, files: list[FileVar]) -> UserPromptMessage:
        """
        根据提供的提示信息和文件列表，获取最后一个用户消息。
        
        参数:
        - prompt: str，给用户的提示信息。
        - files: list[FileVar]，包含文件变量的列表，每个文件变量应提供一个提示消息内容。
        
        返回值:
        - UserPromptMessage，包含用户提示消息的对象。
        """
        if files:
            # 如果有文件，构建包含提示信息和每个文件的提示内容的消息列表
            prompt_message_contents = [TextPromptMessageContent(data=prompt)]
            for file in files:
                prompt_message_contents.append(file.prompt_message_content)

            prompt_message = UserPromptMessage(content=prompt_message_contents)
        else:
            # 如果没有文件，直接使用提供的提示信息创建用户消息
            prompt_message = UserPromptMessage(content=prompt)

        return prompt_message

    def _get_prompt_rule(self, app_mode: AppMode, provider: str, model: str) -> dict:
        """
        获取简单的提示规则。
        :param app_mode: 应用模式
        :param provider: 模型提供者
        :param model: 模型名称
        :return: 返回提示规则的字典
        """
        # 生成提示文件的名称
        prompt_file_name = self._prompt_file_name(
            app_mode=app_mode,
            provider=provider,
            model=model
        )

        # 检查提示文件是否已经加载
        if prompt_file_name in prompt_file_contents:
            return prompt_file_contents[prompt_file_name]

        # 获取子目录的绝对路径
        prompt_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'prompt_templates')
        json_file_path = os.path.join(prompt_path, f'{prompt_file_name}.json')

        # 打开JSON文件并读取其内容
        with open(json_file_path, encoding='utf-8') as json_file:
            content = json.load(json_file)

            # 存储提示文件的内容
            prompt_file_contents[prompt_file_name] = content

            return content

    def _prompt_file_name(self, app_mode: AppMode, provider: str, model: str) -> str:
        """
        根据应用模式、服务提供商和模型名称生成相应的文件名前缀。

        参数:
        app_mode: AppMode 类型，表示应用的模式，如完成功能或聊天模式。
        provider: 字符串，表示服务提供商的名称。
        model: 字符串，表示模型的名称。

        返回值:
        返回一个字符串，作为生成的文件名前缀。
        """

        # 判断是否为百川模型
        is_baichuan = False
        if provider == 'baichuan':
            is_baichuan = True
        else:
            baichuan_supported_providers = ["huggingface_hub", "openllm", "xinference"]
            if provider in baichuan_supported_providers and 'baichuan' in model.lower():
                is_baichuan = True

        # 根据是否为百川模型及应用模式，返回相应的文件名前缀
        if is_baichuan:
            if app_mode == AppMode.COMPLETION:
                return 'baichuan_completion'
            else:
                return 'baichuan_chat'

        # 对于非百川模型，根据应用模式返回相应的文件名前缀
        if app_mode == AppMode.COMPLETION:
            return 'common_completion'
        else:
            return 'common_chat'
