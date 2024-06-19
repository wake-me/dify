import logging
import time
from enum import Enum
from threading import Lock
from typing import Literal, Optional

from httpx import get, post
from pydantic import BaseModel
from yarl import URL

from config import get_env
from core.helper.code_executor.entities import CodeDependency
from core.helper.code_executor.javascript.javascript_transformer import NodeJsTemplateTransformer
from core.helper.code_executor.jinja2.jinja2_transformer import Jinja2TemplateTransformer
from core.helper.code_executor.python3.python3_transformer import Python3TemplateTransformer
from core.helper.code_executor.template_transformer import TemplateTransformer

logger = logging.getLogger(__name__)

# Code Executor
CODE_EXECUTION_ENDPOINT = get_env('CODE_EXECUTION_ENDPOINT')
CODE_EXECUTION_API_KEY = get_env('CODE_EXECUTION_API_KEY')

CODE_EXECUTION_TIMEOUT= (10, 60)  # 定义代码执行的超时时间，元组中第一个值为尝试次数，第二个值为每次尝试的间隔秒数

class CodeExecutionException(Exception):
    pass  # 定义一个自定义异常，用于处理代码执行过程中的异常

class CodeExecutionResponse(BaseModel):
    class Data(BaseModel):
        stdout: Optional[str] = None
        error: Optional[str] = None

    code: int
    message: str
    data: Data


class CodeLanguage(str, Enum):
    PYTHON3 = 'python3'
    JINJA2 = 'jinja2'
    JAVASCRIPT = 'javascript'


class CodeExecutor:
    dependencies_cache = {}
    dependencies_cache_lock = Lock()

    code_template_transformers: dict[CodeLanguage, type[TemplateTransformer]] = {
        CodeLanguage.PYTHON3: Python3TemplateTransformer,
        CodeLanguage.JINJA2: Jinja2TemplateTransformer,
        CodeLanguage.JAVASCRIPT: NodeJsTemplateTransformer,
    }

    code_language_to_running_language = {
        CodeLanguage.JAVASCRIPT: 'nodejs',
        CodeLanguage.JINJA2: CodeLanguage.PYTHON3,
        CodeLanguage.PYTHON3: CodeLanguage.PYTHON3,
    }

    supported_dependencies_languages: set[CodeLanguage] = {
        CodeLanguage.PYTHON3
    }

    @classmethod
    def execute_code(cls, 
                     language: Literal['python3', 'javascript', 'jinja2'], 
                     preload: str, 
                     code: str, 
                     dependencies: Optional[list[CodeDependency]] = None) -> str:
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
            'preload': preload,
            'enable_network': True
        }

        if dependencies:
            data['dependencies'] = [dependency.model_dump() for dependency in dependencies]

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
            raise CodeExecutionException('Failed to execute code, which is likely a network issue,'
                                         ' please check if the sandbox service is running.'
                                         f' ( Error: {str(e)} )')
        
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
    def execute_workflow_code_template(cls, language: Literal['python3', 'javascript', 'jinja2'], code: str, inputs: dict, dependencies: Optional[list[CodeDependency]] = None) -> dict:
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

        runner, preload, dependencies = template_transformer.transform_caller(code, inputs, dependencies)

        # 执行转换后的代码
        try:
            response = cls.execute_code(language, preload, runner, dependencies)
        except CodeExecutionException as e:
            raise e

        # 将执行结果转换为预期的输出格式
        return template_transformer.transform_response(response)
    
    @classmethod
    def list_dependencies(cls, language: str) -> list[CodeDependency]:
        if language not in cls.supported_dependencies_languages:
            return []

        with cls.dependencies_cache_lock:
            if language in cls.dependencies_cache:
                # check expiration
                dependencies = cls.dependencies_cache[language]
                if dependencies['expiration'] > time.time():
                    return dependencies['data']
                # remove expired cache
                del cls.dependencies_cache[language]
        
        dependencies = cls._get_dependencies(language)
        with cls.dependencies_cache_lock:
            cls.dependencies_cache[language] = {
                'data': dependencies,
                'expiration': time.time() + 60
            }
        
        return dependencies
        
    @classmethod
    def _get_dependencies(cls, language: Literal['python3']) -> list[CodeDependency]:
        """
        List dependencies
        """
        url = URL(CODE_EXECUTION_ENDPOINT) / 'v1' / 'sandbox' / 'dependencies'

        headers = {
            'X-Api-Key': CODE_EXECUTION_API_KEY
        }

        running_language = cls.code_language_to_running_language.get(language)
        if isinstance(running_language, Enum):
            running_language = running_language.value

        data = {
            'language': running_language,
        }

        try:
            response = get(str(url), params=data, headers=headers, timeout=CODE_EXECUTION_TIMEOUT)
            if response.status_code != 200:
                raise Exception(f'Failed to list dependencies, got status code {response.status_code}, please check if the sandbox service is running')
            response = response.json()
            dependencies = response.get('data', {}).get('dependencies', [])
            return [
                CodeDependency(**dependency) for dependency in dependencies
                if dependency.get('name') not in Python3TemplateTransformer.get_standard_packages()
            ]
        except Exception as e:
            logger.exception(f'Failed to list dependencies: {e}')
            return []