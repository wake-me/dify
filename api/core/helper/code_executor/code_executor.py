from enum import Enum
from typing import Literal, Optional

from httpx import post
from pydantic import BaseModel
from yarl import URL

from config import get_env
from core.helper.code_executor.javascript_transformer import NodeJsTemplateTransformer
from core.helper.code_executor.jinja2_transformer import Jinja2TemplateTransformer
from core.helper.code_executor.python_transformer import PythonTemplateTransformer

# 代码执行器配置
CODE_EXECUTION_ENDPOINT = get_env('CODE_EXECUTION_ENDPOINT')  # 代码执行的端点URL，从环境变量中获取
CODE_EXECUTION_API_KEY = get_env('CODE_EXECUTION_API_KEY')  # 用于代码执行的API密钥，从环境变量中获取

CODE_EXECUTION_TIMEOUT= (10, 60)  # 定义代码执行的超时时间，元组中第一个值为尝试次数，第二个值为每次尝试的间隔秒数

class CodeExecutionException(Exception):
    pass  # 定义一个自定义异常，用于处理代码执行过程中的异常

class CodeExecutionResponse(BaseModel):
    class Data(BaseModel):
        stdout: Optional[str]  # 标准输出，如果有的话
        error: Optional[str]  # 错误信息，如果执行过程中有错误的话

    code: int
    message: str
    data: Data


class CodeLanguage(str, Enum):
    PYTHON3 = 'python3'
    JINJA2 = 'jinja2'
    JAVASCRIPT = 'javascript'


class CodeExecutor:
    code_template_transformers = {
        CodeLanguage.PYTHON3: PythonTemplateTransformer,
        CodeLanguage.JINJA2: Jinja2TemplateTransformer,
        CodeLanguage.JAVASCRIPT: NodeJsTemplateTransformer,
    }

    code_language_to_running_language = {
        CodeLanguage.JAVASCRIPT: 'nodejs',
        CodeLanguage.JINJA2: CodeLanguage.PYTHON3,
        CodeLanguage.PYTHON3: CodeLanguage.PYTHON3,
    }

    @classmethod
    def execute_code(cls, language: Literal['python3', 'javascript', 'jinja2'], preload: str, code: str) -> str:
        """
        执行代码片段
        
        :param language: 代码语言，支持 python3、javascript、jinja2
        :param preload: 预加载代码（如果需要）
        :param code: 待执行的代码片段
        :return: 执行结果的标准输出
        """
        # 构建请求URL和头部
        url = URL(CODE_EXECUTION_ENDPOINT) / 'v1' / 'sandbox' / 'run'
        headers = {
            'X-Api-Key': CODE_EXECUTION_API_KEY
        }

        # 根据不同的语言代码设置执行环境
        data = {
            'language': cls.code_language_to_running_language.get(language),
            'code': code,
            'preload': preload
        }

        # 发送代码执行请求
        try:
            response = post(str(url), json=data, headers=headers, timeout=CODE_EXECUTION_TIMEOUT)
            # 处理服务不可用或其他非200状态码的情况
            if response.status_code == 503:
                raise CodeExecutionException('Code execution service is unavailable')
            elif response.status_code != 200:
                raise Exception(f'Failed to execute code, got status code {response.status_code}, please check if the sandbox service is running')
        except CodeExecutionException as e:
            raise e
        except Exception as e:
            raise CodeExecutionException('Failed to execute code, this is likely a network issue, please check if the sandbox service is running')
        
        # 解析响应结果
        try:
            response = response.json()
        except:
            raise CodeExecutionException('Failed to parse response')
        
        response = CodeExecutionResponse(**response)

        # 检查代码执行结果状态
        if response.code != 0:
            raise CodeExecutionException(response.message)
        
        # 检查执行结果中是否有错误信息
        if response.data.error:
            raise CodeExecutionException(response.data.error)
        
        return response.data.stdout

    @classmethod
    def execute_workflow_code_template(cls, language: Literal['python3', 'javascript', 'jinja2'], code: str, inputs: dict) -> dict:
        """
        执行工作流代码模板
        
        :param language: 代码语言，支持 python3、javascript、jinja2
        :param code: 工作流代码模板
        :param inputs: 输入参数
        :return: 模板处理后的结果
        """
        template_transformer = cls.code_template_transformers.get(language)
        if not template_transformer:
            raise CodeExecutionException(f'Unsupported language {language}')

        # 转换代码和预加载信息以适应执行环境
        runner, preload = template_transformer.transform_caller(code, inputs)

        # 执行转换后的代码
        try:
            response = cls.execute_code(language, preload, runner)
        except CodeExecutionException as e:
            raise e

        # 将执行结果转换为预期的输出格式
        return template_transformer.transform_response(response)