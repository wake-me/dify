from typing import Any

from core.llm_generator.output_parser.errors import OutputParserException
from core.llm_generator.prompts import RULE_CONFIG_GENERATE_TEMPLATE
from libs.json_in_md_parser import parse_and_check_json_markdown


class RuleConfigGeneratorOutputParser:
    """
    规则配置生成器输出解析器类。
    用于解析并验证规则配置生成器的输出，确保其格式正确无误。
    """

    def get_format_instructions(self) -> str:
        """
        获取格式说明文本。
        
        返回：
            str: 返回规则配置生成的模板格式说明。
        """
        return RULE_CONFIG_GENERATE_TEMPLATE

    def parse(self, text: str) -> Any:
        """
        解析给定的文本，验证其是否符合预期的JSON或Markdown格式，并提取关键信息。
        
        参数：
            text (str): 需要解析的文本。
            
        返回：
            Any: 解析后得到的数据结构，通常为字典，包含"prompt", "variables", "opening_statement"等键值。
        
        异常：
            OutputParserException: 当解析失败或文本格式不符合预期时抛出。
        """
        try:
            # 预期的键列表，用于验证解析结果是否完整
            expected_keys = ["prompt", "variables", "opening_statement"]
            # 解析并验证文本，确保它包含预期的键
            parsed = parse_and_check_json_markdown(text, expected_keys)
            
            # 验证解析结果中特定键的类型
            if not isinstance(parsed["prompt"], str):
                raise ValueError("Expected 'prompt' to be a string.")
            if not isinstance(parsed["variables"], list):
                raise ValueError(
                    "Expected 'variables' to be a list."
                )
            if not isinstance(parsed["opening_statement"], str):
                raise ValueError(
                    "Expected 'opening_statement' to be a str."
                )
            
            return parsed
        except Exception as e:
            # 当解析过程中发生任何异常时，将其封装并抛出
            raise OutputParserException(
                f"Parsing text\n{text}\n of rule config generator raised following error:\n{e}"
            )
