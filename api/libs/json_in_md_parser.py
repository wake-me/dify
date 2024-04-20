import json

from core.llm_generator.output_parser.errors import OutputParserException


def parse_json_markdown(json_string: str) -> dict:
    """
    从包含JSON数据的Markdown字符串中提取并解析JSON数据。
    
    参数:
    json_string: str - 包含JSON数据的Markdown字符串。
    
    返回值:
    dict - 解析后的JSON数据。
    """
    # 移除可能存在的三引号
    json_string = json_string.strip()
    # 查找```json开始和结束的标记
    start_index = json_string.find("```json")
    end_index = json_string.find("```", start_index + len("```json"))

    if start_index != -1 and end_index != -1:
        # 从Markdown格式中提取JSON字符串
        extracted_content = json_string[start_index + len("```json"):end_index].strip()
        # 解析JSON字符串为Python字典
        parsed = json.loads(extracted_content)
    elif start_index != -1 and end_index == -1 and json_string.endswith("``"):
        # 处理仅有一侧```标记的情况
        end_index = json_string.find("``", start_index + len("```json"))
        extracted_content = json_string[start_index + len("```json"):end_index].strip()
        # 解析JSON字符串为Python字典
        parsed = json.loads(extracted_content)
    elif json_string.startswith("{"):
        # 直接处理以{开始的JSON字符串
        parsed = json.loads(json_string)
    else:
        # 如果无法找到JSON块，则抛出异常
        raise Exception("Could not find JSON block in the output.")

    return parsed


def parse_and_check_json_markdown(text: str, expected_keys: list[str]) -> dict:
    """
    解析并校验 Markdown 文本中的 JSON 对象。
    
    参数:
    - text: str，包含 JSON 数据的 Markdown 文本。
    - expected_keys: list[str]，预期 JSON 对象中应包含的键列表。
    
    返回:
    - dict，解析并校验通过的 JSON 对象。
    
    抛出:
    - OutputParserException，当遇到无效的 JSON 对象或缺少预期键时抛出。
    """
    try:
        json_obj = parse_json_markdown(text)  # 尝试从 Markdown 文本解析 JSON 对象
    except json.JSONDecodeError as e:
        raise OutputParserException(f"Got invalid JSON object. Error: {e}")  # 解析失败时抛出异常
    for key in expected_keys:  # 遍历预期的键列表
        if key not in json_obj:  # 如果 JSON 对象中缺少某个预期键
            raise OutputParserException(
                f"Got invalid return object. Expected key `{key}` "
                f"to be present, but got {json_obj}"
            )
    return json_obj