from typing import Optional

from core.app.entities.app_invoke_entities import ModelConfigWithCredentialsEntity
from core.memory.token_buffer_memory import TokenBufferMemory
from core.model_manager import ModelInstance
from core.model_runtime.entities.message_entities import PromptMessage
from core.model_runtime.entities.model_entities import ModelPropertyKey
from core.prompt.entities.advanced_prompt_entities import MemoryConfig


class PromptTransform:
    def _append_chat_histories(self, memory: TokenBufferMemory,
                               memory_config: MemoryConfig,
                               prompt_messages: list[PromptMessage],
                               model_config: ModelConfigWithCredentialsEntity) -> list[PromptMessage]:
        """
        向提示消息列表中追加聊天历史记录。

        :param memory: 令牌缓冲区记忆体，用于存储聊天历史记录。
        :param memory_config: 记忆体配置，定义了如何处理和访问记忆体。
        :param prompt_messages: 当前的提示消息列表。
        :param model_config: 包含模型配置和凭证的信息。
        :return: 更新后的提示消息列表，包含了追加的聊天历史记录。
        """
        # 计算剩余令牌数
        rest_tokens = self._calculate_rest_token(prompt_messages, model_config)
        # 从记忆体中获取历史消息
        histories = self._get_history_messages_list_from_memory(memory, memory_config, rest_tokens)
        # 将历史消息扩展到提示消息列表中
        prompt_messages.extend(histories)

        return prompt_messages

    def _calculate_rest_token(self, prompt_messages: list[PromptMessage],
                              model_config: ModelConfigWithCredentialsEntity) -> int:
        """
        计算剩余令牌数。

        :param prompt_messages: 当前的提示消息列表。
        :param model_config: 包含模型配置和凭证的信息。
        :return: 剩余令牌数。
        """
        rest_tokens = 2000  # 默认剩余令牌数

        # 获取模型上下文大小并计算剩余令牌数
        model_context_tokens = model_config.model_schema.model_properties.get(ModelPropertyKey.CONTEXT_SIZE)
        if model_context_tokens:
            model_instance = ModelInstance(
                provider_model_bundle=model_config.provider_model_bundle,
                model=model_config.model
            )

            curr_message_tokens = model_instance.get_llm_num_tokens(
                prompt_messages
            )

            max_tokens = 0
            for parameter_rule in model_config.model_schema.parameter_rules:
                if (parameter_rule.name == 'max_tokens'
                        or (parameter_rule.use_template and parameter_rule.use_template == 'max_tokens')):
                    max_tokens = (model_config.parameters.get(parameter_rule.name)
                                  or model_config.parameters.get(parameter_rule.use_template)) or 0

            rest_tokens = model_context_tokens - max_tokens - curr_message_tokens
            rest_tokens = max(rest_tokens, 0)  # 确保剩余令牌数不为负

        return rest_tokens

    def _get_history_messages_from_memory(self, memory: TokenBufferMemory,
                                          memory_config: MemoryConfig,
                                          max_token_limit: int,
                                          human_prefix: Optional[str] = None,
                                          ai_prefix: Optional[str] = None) -> str:
        """
        从记忆体中获取记忆消息文本。

        :param memory: 令牌缓冲区记忆体。
        :param memory_config: 记忆体配置。
        :param max_token_limit: 最大令牌限制。
        :param human_prefix: 人类消息前缀。
        :param ai_prefix: AI消息前缀。
        :return: 记忆消息的文本字符串。
        """
        # 构建传递给get_history_prompt_text的参数
        kwargs = {
            "max_token_limit": max_token_limit
        }

        if human_prefix:
            kwargs['human_prefix'] = human_prefix

        if ai_prefix:
            kwargs['ai_prefix'] = ai_prefix

        # 如果窗口配置启用且大小有效，则设置消息限制
        if memory_config.window.enabled and memory_config.window.size is not None and memory_config.window.size > 0:
            kwargs['message_limit'] = memory_config.window.size

        return memory.get_history_prompt_text(
            **kwargs
        )

    def _get_history_messages_list_from_memory(self, memory: TokenBufferMemory,
                                               memory_config: MemoryConfig,
                                               max_token_limit: int) -> list[PromptMessage]:
        """
        从记忆体中获取记忆消息列表。

        :param memory: 令牌缓冲区记忆体。
        :param memory_config: 记忆体配置。
        :param max_token_limit: 最大令牌限制。
        :return: 记忆消息列表。
        """
        # 获取历史提示消息，应用最大令牌限制和可能的消息限制
        return memory.get_history_prompt_messages(
            max_token_limit=max_token_limit,
            message_limit=memory_config.window.size
            if (memory_config.window.enabled
                and memory_config.window.size is not None
                and memory_config.window.size > 0)
            else None
        )