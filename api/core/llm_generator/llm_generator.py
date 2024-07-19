import json
import logging
import re
from typing import Optional

from core.llm_generator.output_parser.errors import OutputParserException
from core.llm_generator.output_parser.rule_config_generator import RuleConfigGeneratorOutputParser
from core.llm_generator.output_parser.suggested_questions_after_answer import SuggestedQuestionsAfterAnswerOutputParser
from core.llm_generator.prompts import CONVERSATION_TITLE_PROMPT, GENERATOR_QA_PROMPT
from core.model_manager import ModelManager
from core.model_runtime.entities.message_entities import SystemPromptMessage, UserPromptMessage
from core.model_runtime.entities.model_entities import ModelType
from core.model_runtime.errors.invoke import InvokeAuthorizationError, InvokeError
from core.ops.ops_trace_manager import TraceQueueManager, TraceTask, TraceTaskName
from core.ops.utils import measure_time
from core.prompt.utils.prompt_template_parser import PromptTemplateParser


class LLMGenerator:
    @classmethod
    def generate_conversation_name(
        cls, tenant_id: str, query, conversation_id: Optional[str] = None, app_id: Optional[str] = None
    ):
        prompt = CONVERSATION_TITLE_PROMPT

        # 如果查询字符串过长，则截取并添加省略号
        if len(query) > 2000:
            query = query[:300] + "...[TRUNCATED]..." + query[-300:]

        # 替换换行符为空格，确保查询字符串是一行文本
        query = query.replace("\n", " ")

        prompt += query + "\n"

        # 获取默认的LLM模型实例
        model_manager = ModelManager()
        model_instance = model_manager.get_default_model_instance(
            tenant_id=tenant_id,
            model_type=ModelType.LLM,
        )
        prompts = [UserPromptMessage(content=prompt)]

        with measure_time() as timer:
            response = model_instance.invoke_llm(
                prompt_messages=prompts,
                model_parameters={
                    "max_tokens": 100,
                    "temperature": 1
                },
                stream=False
            )
        answer = response.message.content
        cleaned_answer = re.sub(r'^.*(\{.*\}).*$', r'\1', answer, flags=re.DOTALL)
        result_dict = json.loads(cleaned_answer)
        answer = result_dict['Your Output']
        name = answer.strip()

        # 如果生成的名称超过75个字符，截取并添加省略号
        if len(name) > 75:
            name = name[:75] + '...'

        # get tracing instance
        trace_manager = TraceQueueManager(app_id=app_id)
        trace_manager.add_trace_task(
            TraceTask(
                TraceTaskName.GENERATE_NAME_TRACE,
                conversation_id=conversation_id,
                generate_conversation_name=name,
                inputs=prompt,
                timer=timer,
                tenant_id=tenant_id,
            )
        )

        return name

    @classmethod
    def generate_suggested_questions_after_answer(cls, tenant_id: str, histories: str):
        """
        根据提供的答案生成建议的问题列表。

        :param cls: 类名，用于调用生成建议问题的类方法。
        :param tenant_id: 租户ID，用于获取特定租户的模型实例。
        :param histories: 历史记录字符串，包含之前的对话历史。
        :return: 建议问题列表。如果无法获取建议问题或发生异常，则返回空列表。
        """
        # 初始化输出解析器，用于解析模型响应生成建议问题
        output_parser = SuggestedQuestionsAfterAnswerOutputParser()
        format_instructions = output_parser.get_format_instructions()  # 获取格式化指令

        # 使用模板解析器设置提示模板
        prompt_template = PromptTemplateParser(
            template="{{histories}}\n{{format_instructions}}\nquestions:\n"
        )

        # 根据提供的历史记录和格式化指令填充模板
        prompt = prompt_template.format({
            "histories": histories,
            "format_instructions": format_instructions
        })

        try:
            # 尝试获取默认的LLM（Large Language Model）模型实例
            model_manager = ModelManager()
            model_instance = model_manager.get_default_model_instance(
                tenant_id=tenant_id,
                model_type=ModelType.LLM,
            )
        except InvokeAuthorizationError:
            # 如果授权错误，则直接返回空列表
            return []

        # 准备模型提示消息
        prompt_messages = [UserPromptMessage(content=prompt)]

        try:
            # 调用LLM模型，传入提示消息和模型参数
            response = model_instance.invoke_llm(
                prompt_messages=prompt_messages,
                model_parameters={
                    "max_tokens": 256,  # 最大令牌数
                    "temperature": 0  # 生成结果的温度，0表示确定性最高
                },
                stream=False
            )

            # 解析模型响应生成建议问题列表
            questions = output_parser.parse(response.message.content)
        except InvokeError:
            # 如果调用模型失败，则返回空列表
            questions = []
        except Exception as e:
            # 记录未预期的异常，并返回空列表
            logging.exception(e)
            questions = []

        return questions

    @classmethod
    def generate_rule_config(cls, tenant_id: str, audiences: str, hoping_to_solve: str) -> dict:
        """
        生成规则配置。

        参数:
        - tenant_id: 租户ID，类型为字符串。
        - audiences: 目标受众，类型为字符串。
        - hoping_to_solve: 期望解决的问题，类型为字符串。

        返回值:
        - 一个字典，包含规则配置信息。
        """

        # 初始化输出解析器
        output_parser = RuleConfigGeneratorOutputParser()

        # 解析提示模板
        prompt_template = PromptTemplateParser(
            template=output_parser.get_format_instructions()
        )

        # 格式化提示信息
        prompt = prompt_template.format(
            inputs={
                "audiences": audiences,
                "hoping_to_solve": hoping_to_solve,
                "variable": "{{variable}}",
                "lanA": "{{lanA}}",
                "lanB": "{{lanB}}",
                "topic": "{{topic}}"
            },
            remove_template_variables=False
        )

        # 管理模型实例
        model_manager = ModelManager()
        model_instance = model_manager.get_default_model_instance(
            tenant_id=tenant_id,
            model_type=ModelType.LLM,
        )

        # 准备用户提示消息
        prompt_messages = [UserPromptMessage(content=prompt)]

        try:
            # 调用LLM模型
            response = model_instance.invoke_llm(
                prompt_messages=prompt_messages,
                model_parameters={
                    "max_tokens": 512,
                    "temperature": 0
                },
                stream=False
            )

            # 解析规则配置
            rule_config = output_parser.parse(response.message.content)
        except InvokeError as e:
            raise e
        except OutputParserException:
            raise ValueError('Please give a valid input for intended audience or hoping to solve problems.')
        except Exception as e:
            logging.exception(e)
            # 默认规则配置
            rule_config = {
                "prompt": "",
                "variables": [],
                "opening_statement": ""
            }

        return rule_config

    @classmethod
    def generate_qa_document(cls, tenant_id: str, query, document_language: str):
        """
        生成问题与答案文档。

        参数:
        - tenant_id: 租户ID，字符串类型，用于标识不同的租户。
        - query: 查询内容，字符串类型，表示用户提出的问题。
        - document_language: 文档语言，字符串类型，用于指定生成文档的语言。

        返回值:
        - 返回问题的答案，字符串类型，经过处理后可能去除首尾空白。
        """
        # 使用指定语言格式化生成问题的提示信息
        prompt = GENERATOR_QA_PROMPT.format(language=document_language)

        # 获取模型管理器实例，并通过租户ID和模型类型获取默认的模型实例
        model_manager = ModelManager()
        model_instance = model_manager.get_default_model_instance(
            tenant_id=tenant_id,
            model_type=ModelType.LLM,
        )

        # 准备提示信息，包括系统提示和用户提问
        prompt_messages = [
            SystemPromptMessage(content=prompt),
            UserPromptMessage(content=query)
        ]

        # 调用模型，传入提示信息和模型参数，获取响应结果
        response = model_instance.invoke_llm(
            prompt_messages=prompt_messages,
            model_parameters={
                'temperature': 0.01,  # 模型生成答案的随机性程度
                "max_tokens": 2000  # 最大生成token数量
            },
            stream=False
        )

        # 从响应中提取答案，并去除首尾空白后返回
        answer = response.message.content
        return answer.strip()
