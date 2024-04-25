import re

REGEX = re.compile(r"\{\{([a-zA-Z_][a-zA-Z0-9_]{0,29}|#histories#|#query#|#context#)\}\}")
WITH_VARIABLE_TMPL_REGEX = re.compile(
    r"\{\{([a-zA-Z_][a-zA-Z0-9_]{0,29}|#[a-zA-Z0-9_]{1,50}\.[a-zA-Z0-9_\.]{1,100}#|#histories#|#query#|#context#)\}\}"
)


class PromptTemplateParser:
    """
    提示模板解析器，用于解析和格式化包含模板变量的字符串。

    规则:
    1. 模板变量必须用`{{}}`括起来。
    2. 模板变量键只能是：字母、数字、下划线，最大长度为16个字符，并且只能以字母和下划线开头。
    3. 模板变量键不能包含换行或空格，并且必须遵守规则2。
    4. 除了以上规则外，还接受3种特殊模板变量键：`{{#histories#}}` `{{#query#}}` `{{#context#}}`。不允许其他`{{##}}`模板变量。
    """

    def __init__(self, template: str, with_variable_tmpl: bool = False):
        """
        初始化提示模板解析器实例。

        :param template: 待解析的模板字符串。
        :param with_variable_tmpl: 是否包含复杂变量模板，默认为False。
        """
        self.template = template
        self.with_variable_tmpl = with_variable_tmpl
        self.regex = WITH_VARIABLE_TMPL_REGEX if with_variable_tmpl else REGEX
        self.variable_keys = self.extract()

    def extract(self) -> list:
        """
        从模板中提取所有变量键。

        :return: 包含所有变量键的列表。
        """
        # 根据模板规则匹配变量键
        return re.findall(self.regex, self.template)

    def format(self, inputs: dict, remove_template_variables: bool = True) -> str:
        """
        格式化模板字符串，用给定的值替换模板变量。

        :param inputs: 包含模板变量值的字典。
        :param remove_template_variables: 是否移除替换后的模板变量，默认为True。
        :return: 替换后的字符串。
        """
        def replacer(match):
            key = match.group(1)
            value = inputs.get(key, match.group(0))  # 如果未找到键，则返回原始匹配的字符串

            if remove_template_variables:
                return PromptTemplateParser.remove_template_variables(value, self.with_variable_tmpl)
            return value

        prompt = re.sub(self.regex, replacer, self.template)
        # 移除可能存在的额外标记
        return re.sub(r'<\|.*?\|>', '', prompt)

    @classmethod
    def remove_template_variables(cls, text: str, with_variable_tmpl: bool = False):
        """
        从文本中移除模板变量。

        :param text: 待处理的文本。
        :param with_variable_tmpl: 是否包含复杂变量模板，默认为False。
        :return: 移除模板变量后的文本。
        """
        return re.sub(WITH_VARIABLE_TMPL_REGEX if with_variable_tmpl else REGEX, r'{\1}', text)