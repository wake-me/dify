import json

from core.agent.cot_agent_runner import CotAgentRunner
from core.model_runtime.entities.message_entities import (
    AssistantPromptMessage,
    PromptMessage,
    SystemPromptMessage,
    TextPromptMessageContent,
    UserPromptMessage,
)
from core.model_runtime.utils.encoders import jsonable_encoder


class CotChatAgentRunner(CotAgentRunner):
    def _organize_system_prompt(self) -> SystemPromptMessage:
        """
        组织系统提示信息
        
        该方法用于根据应用配置和当前指令组织并生成一个系统的提示信息。它会将预定义的提示模板
        与当前指令、可用工具等信息相结合，生成一个完整的系统提示消息。

        返回值:
            SystemPromptMessage: 包含组织好的系统提示信息的对象
        """
        # 从应用配置中获取代理的提示信息实体
        prompt_entity = self.app_config.agent.prompt
        first_prompt = prompt_entity.first_prompt

        # 使用替换将模板中的占位符替换为实际的值
        system_prompt = first_prompt \
            .replace("{{instruction}}", self._instruction) \
            .replace("{{tools}}", json.dumps(jsonable_encoder(self._prompt_messages_tools))) \
            .replace("{{tool_names}}", ', '.join([tool.name for tool in self._prompt_messages_tools]))

        # 返回组织好的系统提示信息
        return SystemPromptMessage(content=system_prompt)

    def _organize_user_query(self, query,  prompt_messages: list[PromptMessage] = None) -> list[PromptMessage]:
        """
        Organize user query
        """
        if self.files:
            prompt_message_contents = [TextPromptMessageContent(data=query)]
            for file_obj in self.files:
                prompt_message_contents.append(file_obj.prompt_message_content)

            prompt_messages.append(UserPromptMessage(content=prompt_message_contents))
        else:
            prompt_messages.append(UserPromptMessage(content=query))

        return prompt_messages

    def _organize_prompt_messages(self) -> list[PromptMessage]:
        """
        组织并返回一个包含系统提示、历史对话、当前助手消息和用户查询的的消息列表。

        返回值:
            list[PromptMessage]: 一个包含多种类型消息的列表，每个元素都是PromptMessage的子类实例。
        """
        # 组织系统提示消息
        system_message = self._organize_system_prompt()

        # 组织当前助手的消息
        agent_scratchpad = self._agent_scratchpad
        if not agent_scratchpad:
            assistant_messages = []
        else:
            assistant_message = AssistantPromptMessage(content='')
            for unit in agent_scratchpad:
                if unit.is_final():
                    assistant_message.content += f"Final Answer: {unit.agent_response}"
                else:
                    assistant_message.content += f"Thought: {unit.thought}\n\n"
                    if unit.action_str:
                        assistant_message.content += f"Action: {unit.action_str}\n\n"
                    if unit.observation:
                        assistant_message.content += f"Observation: {unit.observation}\n\n"

            # 初始化助手回复消息列表
            assistant_messages = [assistant_message]

        # query messages
        query_messages = self._organize_user_query(self._query, [])

        # 根据是否存在助手回复消息，组织消息列表
        if assistant_messages:
            # organize historic prompt messages
            historic_messages = self._organize_historic_prompt_messages([
                system_message,
                *query_messages,
                *assistant_messages,
                UserPromptMessage(content='continue')
            ])
            messages = [
                system_message,
                *historic_messages,
                *query_messages,
                *assistant_messages,
                UserPromptMessage(content='continue')
            ]
        else:
            # organize historic prompt messages
            historic_messages = self._organize_historic_prompt_messages([system_message, *query_messages])
            messages = [system_message, *historic_messages, *query_messages]

        # 将所有消息合并并返回
        return messages
