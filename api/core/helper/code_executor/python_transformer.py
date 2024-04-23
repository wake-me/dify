import json
import re

from core.helper.code_executor.template_transformer import TemplateTransformer

PYTHON_RUNNER = """# declare main function here
{{code}}

# execute main function, and return the result
# inputs is a dict, and it
output = main(**{{inputs}})

# convert output to json and print
output = json.dumps(output, indent=4)

result = f'''<<RESULT>>
{output}
<<RESULT>>'''

print(result)
"""

PYTHON_PRELOAD = """
# prepare general imports
import json
import datetime
import math
import random
import re
import string
import sys
import time
import traceback
import uuid
import os
import base64
import hashlib
import hmac
import binascii
import collections
import functools
import operator
import itertools
"""

class PythonTemplateTransformer(TemplateTransformer):
    @classmethod
    def transform_caller(cls, code: str, inputs: dict) -> tuple[str, str]:
        """
        将代码转换为Python运行器格式。
        :param code: 需要执行的代码。
        :param inputs: 传递给代码的输入参数，字典格式。
        :return: 返回一个元组，包含转换后的Python运行器代码和预加载代码。
        """
        
        # 将输入参数转换为JSON字符串
        inputs_str = json.dumps(inputs, indent=4, ensure_ascii=False)

        # 替换代码中的占位符以插入代码和输入参数
        runner = PYTHON_RUNNER.replace('{{code}}', code)
        runner = runner.replace('{{inputs}}', inputs_str)

        return runner, PYTHON_PRELOAD
    
    @classmethod
    def transform_response(cls, response: str) -> dict:
        """
        将响应转换为字典格式。
        :param response: 从Python运行器接收的响应。
        :return: 返回解析后的结果，字典格式。
        """
        # 提取结果部分的JSON字符串
        result = re.search(r'<<RESULT>>(.*?)<<RESULT>>', response, re.DOTALL)
        if not result:
            raise ValueError('Failed to parse result')
        result = result.group(1)
        return json.loads(result)