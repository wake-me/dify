import json

from core.agent.cot_agent_runner import CotAgentRunner
from core.model_runtime.entities.message_entities import AssistantPromptMessage, PromptMessage, UserPromptMessage
from core.model_runtime.utils.encoders import jsonable_encoder


class CotCompletionAgentRunner(CotAgentRunner):
    def _organize_instruction_prompt(self) -> str:
        """
        组织指令提示信息
        
        该方法用于根据应用配置和当前指令，生成一个定制的系统提示信息。
        
        返回值:
            str: 组织好的系统提示信息字符串。
        """
        # 从应用配置中获取提示实体
        prompt_entity = self.app_config.agent.prompt
        first_prompt = prompt_entity.first_prompt

        # 使用当前指令、工具信息，替换模板中的占位符
        system_prompt = first_prompt.replace("{{instruction}}", self._instruction) \
            .replace("{{tools}}", json.dumps(jsonable_encoder(self._prompt_messages_tools))) \
            .replace("{{tool_names}}", ', '.join([tool.name for tool in self._prompt_messages_tools]))
        
        return system_prompt

    def _organize_historic_prompt(self) -> str:
        """
        组织历史提示信息
        
        该方法会将之前记录的历史提示信息（包括用户提问和助手回答）整理成字符串，每个问题或回答之间用两行空格分隔。
        
        返回值:
            str: 组织好的历史提示信息字符串
        """
        # 获取历史提示信息列表
        historic_prompt_messages = self._historic_prompt_messages
        historic_prompt = ""

        # 遍历每条历史提示信息，区分用户提问和助手回答，并整理到historic_prompt字符串中
        for message in historic_prompt_messages:
            if isinstance(message, UserPromptMessage):
                # 如果是用户提问，则格式化为"Question: 提问内容"的形式，并添加到historic_prompt中
                historic_prompt += f"Question: {message.content}\n\n"
            elif isinstance(message, AssistantPromptMessage):
                # 如果是助手回答，则直接添加到historic_prompt中
                historic_prompt += message.content + "\n\n"

        return historic_prompt

    def _organize_prompt_messages(self) -> list[PromptMessage]:
        """
        组织提示信息
        
        该方法用于将系统的提示信息、历史提示信息、当前助手信息以及查询信息组织成一个统一的格式。
        
        返回值:
        - list[PromptMessage]: 包含整理后的提示信息的列表。
        """
        # 组织系统提示信息
        system_prompt = self._organize_instruction_prompt()

        # 组织历史提示信息
        historic_prompt = self._organize_historic_prompt()

        # 组织当前助手的信息，包括最终回答、思考过程、采取的行动及观察结果
        agent_scratchpad = self._agent_scratchpad
        assistant_prompt = ''
        for unit in agent_scratchpad:
            if unit.is_final():
                assistant_prompt += f"Final Answer: {unit.agent_response}"
            else:
                assistant_prompt += f"Thought: {unit.thought}\n\n"
                if unit.action_str:
                    assistant_prompt += f"Action: {unit.action_str}\n\n"
                if unit.observation:
                    assistant_prompt += f"Observation: {unit.observation}\n\n"

        # 构造查询提示信息
        query_prompt = f"Question: {self._query}"

        # 使用预定义模板和替换字段构造最终提示信息
        prompt = system_prompt \
            .replace("{{historic_messages}}", historic_prompt) \
            .replace("{{agent_scratchpad}}", assistant_prompt) \
            .replace("{{query}}", query_prompt)

        return [UserPromptMessage(content=prompt)]