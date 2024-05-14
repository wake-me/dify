import json
import re
from typing import Optional

from core.helper.code_executor.entities import CodeDependency
from core.helper.code_executor.template_transformer import TemplateTransformer

NODEJS_RUNNER = """// declare main function here
{{code}}

// execute main function, and return the result
// inputs is a dict, unstructured inputs
output = main({{inputs}})

// convert output to json and print
output = JSON.stringify(output)

result = `<<RESULT>>${output}<<RESULT>>`

console.log(result)
"""

NODEJS_PRELOAD = """"""

class NodeJsTemplateTransformer(TemplateTransformer):
    @classmethod
    def transform_caller(cls, code: str, inputs: dict, 
                         dependencies: Optional[list[CodeDependency]] = None) -> tuple[str, str, list[CodeDependency]]:
        """
        将代码转换为Python运行器可以执行的形式。
        :param code: 需要执行的JavaScript代码。
        :param inputs: 传递给JavaScript代码的输入参数，字典形式。
        :return: 返回一个元组，包含转换后的执行代码和预加载代码。
        """
        # 将输入参数转换为JSON字符串
        inputs_str = json.dumps(inputs, indent=4, ensure_ascii=False)

        # 替换代码模板中的代码和输入参数部分
        runner = NODEJS_RUNNER.replace('{{code}}', code)
        runner = runner.replace('{{inputs}}', inputs_str)

        return runner, NODEJS_PRELOAD, []

    @classmethod
    def transform_response(cls, response: str) -> dict:
        """
        将响应转换为字典形式。
        :param response: 从JavaScript代码执行中得到的原始响应。
        :return: 转换后的结果，字典形式。
        """
        # 提取结果部分
        result = re.search(r'<<RESULT>>(.*)<<RESULT>>', response, re.DOTALL)
        if not result:
            raise ValueError('Failed to parse result')
        result = result.group(1)
        return json.loads(result)