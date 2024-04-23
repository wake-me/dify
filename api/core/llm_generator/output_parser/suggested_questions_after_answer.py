import json
import re
from typing import Any

from core.llm_generator.prompts import SUGGESTED_QUESTIONS_AFTER_ANSWER_INSTRUCTION_PROMPT


class SuggestedQuestionsAfterAnswerOutputParser:
    """
    用于解析回答后建议问题的输出解析器类。
    """

    def get_format_instructions(self) -> str:
        """
        获取格式化说明文本。

        返回:
            str: 返回建议问题的格式化说明文本。
        """
        return SUGGESTED_QUESTIONS_AFTER_ANSWER_INSTRUCTION_PROMPT

    def parse(self, text: str) -> Any:
        """
        解析输入文本以获取建议的问题。

        参数:
            text (str): 需要解析以提取建议问题的文本。

        返回:
            Any: 如果找到有效的动作匹配，则返回解析后的JSON对象；否则返回空列表，并打印解析错误信息。
        """
        # 尝试匹配文本中的动作部分
        action_match = re.search(r"\[.*?\]", text.strip(), re.DOTALL)
        if action_match is not None:
            # 如果找到匹配项，解析JSON字符串
            json_obj = json.loads(action_match.group(0).strip())
        else:
            # 如果没有找到匹配项，返回空列表并打印错误信息
            json_obj = []
            print(f"Could not parse LLM output: {text}")

        return json_obj
