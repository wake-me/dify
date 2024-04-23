import json
import re

from core.helper.code_executor.template_transformer import TemplateTransformer

PYTHON_RUNNER = """
import jinja2

# 初始化Jinja2模板
template = jinja2.Template('''{{code}}''')

# 定义主要的渲染函数
def main(**inputs):
    # 根据输入渲染模板
    return template.render(**inputs)

# 执行main函数，并返回结果
output = main(**{{inputs}})

# 将结果封装在特定格式中，便于提取
result = f'''<<RESULT>>{output}<<RESULT>>'''

print(result)

"""

JINJA2_PRELOAD_TEMPLATE = """{% set fruits = ['Apple'] %}
{{ 'a' }}
{% for fruit in fruits %}
    <li>{{ fruit }}</li>
{% endfor %}
{% if fruits|length > 1 %}
1
{% endif %}
{% for i in range(5) %}
    {% if i == 3 %}{{ i }}{% else %}{% endif %}
{% endfor %}
    {% for i in range(3) %}
        {{ i + 1 }}
    {% endfor %}
{% macro say_hello() %}a{{ 'b' }}{% endmacro %}
{{ s }}{{ say_hello() }}"""

JINJA2_PRELOAD = f"""
import jinja2

def _jinja2_preload_():
    # 预加载Jinja2环境，提前加载并渲染模板以避免沙箱问题
    template = jinja2.Template('''{JINJA2_PRELOAD_TEMPLATE}''')
    template.render(s='a')

if __name__ == '__main__':
    _jinja2_preload_()

"""

class Jinja2TemplateTransformer(TemplateTransformer):
    @classmethod
    def transform_caller(cls, code: str, inputs: dict) -> tuple[str, str]:
        """
        将代码转换为Python执行器
        :param code: 待转换的代码
        :param inputs: 输入参数
        :return: 转换后的Python执行代码和Jinja2预加载代码
        """

        # 将Jinja2模板转换为Python代码
        runner = PYTHON_RUNNER.replace('{{code}}', code)
        runner = runner.replace('{{inputs}}', json.dumps(inputs, indent=4, ensure_ascii=False))

        return runner, JINJA2_PRELOAD

    @classmethod
    def transform_response(cls, response: str) -> dict:
        """
        转换响应为字典格式
        :param response: 原始响应字符串
        :return: 包含结果的字典
        """
        # 提取结果字符串
        result = re.search(r'<<RESULT>>(.*)<<RESULT>>', response, re.DOTALL)
        if not result:
            raise ValueError('Failed to parse result')
        result = result.group(1)

        return {
            'result': result
        }