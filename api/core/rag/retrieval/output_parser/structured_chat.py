import json
import re
from typing import Union

from core.rag.retrieval.output_parser.react_output import ReactAction, ReactFinish


class StructuredChatOutputParser:
    """
    用于解析结构化聊天输出的类。
    
    方法:
    parse: 根据输入文本解析出相应的ReactAction或ReactFinish对象。
    """
    
    def parse(self, text: str) -> Union[ReactAction, ReactFinish]:
        """
        解析输入文本，根据内容生成ReactAction或ReactFinish对象。
        
        参数:
        text: str - 需要解析的文本输入。
        
        返回值:
        Union[ReactAction, ReactFinish] - 根据文本内容解析出的ReactAction或ReactFinish对象。
        """
        try:
            # 使用正则表达式匹配可能的行动或结束标记
            action_match = re.search(r"```(\w*)\n?({.*?)```", text, re.DOTALL)
            if action_match is not None:
                # 尝试从匹配中加载JSON响应
                response = json.loads(action_match.group(2).strip(), strict=False)
                # 如果响应是一个列表，取第一个元素
                if isinstance(response, list):
                    response = response[0]
                # 如果行动为"Final Answer"，返回ReactFinish对象
                if response["action"] == "Final Answer":
                    return ReactFinish({"output": response["action_input"]}, text)
                else:
                    # 否则，返回一个ReactAction对象
                    return ReactAction(
                        response["action"], response.get("action_input", {}), text
                    )
            else:
                # 如果没有匹配到行动或结束标记，返回一个包含完整文本的ReactFinish对象
                return ReactFinish({"output": text}, text)
        except Exception as e:
            # 如果在解析过程中出现异常，抛出值错误
            raise ValueError(f"Could not parse LLM output: {text}")