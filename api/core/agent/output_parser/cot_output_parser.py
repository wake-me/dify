import json
import re
from collections.abc import Generator
from typing import Union

from core.agent.entities import AgentScratchpadUnit
from core.model_runtime.entities.llm_entities import LLMResultChunk


class CotAgentOutputParser:
    """
    用于解析CotAgent输出的类，能够识别并处理不同的数据类型，如动作、思考内容、代码块中的JSON数据等。
    """

    @classmethod
    def handle_react_stream_output(cls, llm_response: Generator[LLMResultChunk, None, None], usage_dict: dict) -> \
        Generator[Union[str, AgentScratchpadUnit.Action], None, None]:
        """
        处理LLM响应流中的输出，解析出动作、思考内容和代码块中的JSON数据。

        :param llm_response: LLM（大语言模型）响应的生成器，包含逐步产生的消息内容。
        :return: 解析后的输出生成器，可包含字符串或AgentScratchpadUnit.Action对象。
        """

        def parse_action(json_str):
            """
            解析JSON字符串为动作对象或返回原始字符串。

            :param json_str: 待解析的JSON字符串。
            :return: 动作对象或原始字符串。
            """
            try:
                # 尝试解析JSON字符串为动作
                action = json.loads(json_str)
                action_name = None
                action_input = None

                # 提取动作名称和输入
                for key, value in action.items():
                    if 'input' in key.lower():
                        action_input = value
                    else:
                        action_name = value

                # 如果名称和输入都存在，则返回动作对象，否则返回原始字符串
                if action_name is not None and action_input is not None:
                    return AgentScratchpadUnit.Action(
                        action_name=action_name,
                        action_input=action_input,
                    )
                else:
                    return json_str or ''
            except:
                # 解析失败时返回原始字符串
                return json_str or ''
            
        def extra_json_from_code_block(code_block) -> Generator[Union[dict, str], None, None]:
            """
            从代码块中提取额外的JSON数据。

            :param code_block: 待处理的代码块字符串。
            :return: 提取的JSON数据（作为字典或原始字符串）的生成器。
            """
            # 使用正则表达式查找所有代码块
            code_blocks = re.findall(r'```(.*?)```', code_block, re.DOTALL)
            if not code_blocks:
                return
            # 遍历每个代码块，尝试解析其中的JSON
            for block in code_blocks:
                # 去除代码块标记并尝试解析为动作
                json_text = re.sub(r'^[a-zA-Z]+\n', '', block.strip(), flags=re.MULTILINE)
                yield parse_action(json_text)
            
        # 初始化状态变量，用于处理流中的不同部分
        code_block_cache = ''
        code_block_delimiter_count = 0
        in_code_block = False
        json_cache = ''
        json_quote_count = 0
        in_json = False
        got_json = False

        action_cache = ''
        action_str = 'action:'
        action_idx = 0

        thought_cache = ''
        thought_str = 'thought:'
        thought_idx = 0

        # 遍历响应流
        for response in llm_response:
            if response.delta.usage:
                usage_dict['usage'] = response.delta.usage
            response = response.delta.message.content
            if not isinstance(response, str):
                continue

            # 主循环，处理每个字符
            index = 0
            while index < len(response):
                steps = 1
                delta = response[index:index+steps]
                last_character = response[index-1] if index > 0 else ''

                # 处理代码块
                if delta == '`':
                    code_block_cache += delta
                    code_block_delimiter_count += 1
                else:
                    if not in_code_block:
                        if code_block_delimiter_count > 0:
                            yield code_block_cache
                        code_block_cache = ''
                    else:
                        code_block_cache += delta
                    code_block_delimiter_count = 0

                # 处理动作和思考内容
                if not in_code_block and not in_json:
                    # 动作解析逻辑
                    if delta.lower() == action_str[action_idx] and action_idx == 0:
                        if last_character not in ['\n', ' ', '']:
                            index += steps
                            yield delta
                            continue

                        action_cache += delta
                        action_idx += 1
                        if action_idx == len(action_str):
                            action_cache = ''
                            action_idx = 0
                        index += steps
                        continue
                    elif delta.lower() == action_str[action_idx] and action_idx > 0:
                        action_cache += delta
                        action_idx += 1
                        if action_idx == len(action_str):
                            action_cache = ''
                            action_idx = 0
                        index += steps
                        continue
                    else:
                        if action_cache:
                            yield action_cache
                            action_cache = ''
                            action_idx = 0

                    # 思考内容解析逻辑
                    if delta.lower() == thought_str[thought_idx] and thought_idx == 0:
                        if last_character not in ['\n', ' ', '']:
                            index += steps
                            yield delta
                            continue

                        thought_cache += delta
                        thought_idx += 1
                        if thought_idx == len(thought_str):
                            thought_cache = ''
                            thought_idx = 0
                        index += steps
                        continue
                    elif delta.lower() == thought_str[thought_idx] and thought_idx > 0:
                        thought_cache += delta
                        thought_idx += 1
                        if thought_idx == len(thought_str):
                            thought_cache = ''
                            thought_idx = 0
                        index += steps
                        continue
                    else:
                        if thought_cache:
                            yield thought_cache
                            thought_cache = ''
                            thought_idx = 0

                # 代码块切换逻辑
                if code_block_delimiter_count == 3:
                    if in_code_block:
                        yield from extra_json_from_code_block(code_block_cache)
                        code_block_cache = ''
                        
                    in_code_block = not in_code_block
                    code_block_delimiter_count = 0

                # JSON处理逻辑
                if not in_code_block:
                    if delta == '{':
                        json_quote_count += 1
                        in_json = True
                        json_cache += delta
                    elif delta == '}':
                        json_cache += delta
                        if json_quote_count > 0:
                            json_quote_count -= 1
                            if json_quote_count == 0:
                                in_json = False
                                got_json = True
                                index += steps
                                continue
                    else:
                        if in_json:
                            json_cache += delta

                    if got_json:
                        got_json = False
                        yield parse_action(json_cache)
                        json_cache = ''
                        json_quote_count = 0
                        in_json = False
                    
                # 递增索引并处理替换
                if not in_code_block and not in_json:
                    yield delta.replace('`', '')

                index += steps

        # 提取并处理最后的代码块和JSON缓存
        if code_block_cache:
            yield code_block_cache

        if json_cache:
            yield parse_action(json_cache)

