import os

from flask_login import current_user
from flask_restful import Resource, reqparse

from controllers.console import api
from controllers.console.app.error import (
    CompletionRequestError,
    ProviderModelCurrentlyNotSupportError,
    ProviderNotInitializeError,
    ProviderQuotaExceededError,
)
from controllers.console.setup import setup_required
from controllers.console.wraps import account_initialization_required
from core.errors.error import ModelCurrentlyNotSupportError, ProviderTokenNotInitError, QuotaExceededError
from core.llm_generator.llm_generator import LLMGenerator
from core.model_runtime.errors.invoke import InvokeError
from libs.login import login_required


class RuleGenerateApi(Resource):
    """
    规则生成API，用于根据用户提供的参数生成规则配置。
    
    方法:
    - post: 根据用户提供的受众和期望解决的问题生成规则配置。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    def post(self):
        """
        生成规则配置的接口方法。
        
        要求用户已登录、账号已初始化且系统设置已完成。
        
        参数:
        - audiences: 受众字符串，必填，通过JSON传递。
        - hoping_to_solve: 期望解决的问题字符串，必填，通过JSON传递。
        
        返回值:
        - 生成的规则配置。
        
        抛出异常:
        - ProviderNotInitializeError: 提供者未初始化错误。
        - ProviderQuotaExceededError: 提供者配额超出错误。
        - ProviderModelCurrentlyNotSupportError: 提供者当前不支持的模型错误。
        - CompletionRequestError: 完成请求错误。
        """
        
        parser = reqparse.RequestParser()
        parser.add_argument("instruction", type=str, required=True, nullable=False, location="json")
        parser.add_argument("model_config", type=dict, required=True, nullable=False, location="json")
        parser.add_argument("no_variable", type=bool, required=True, default=False, location="json")
        args = parser.parse_args()

        account = current_user
        PROMPT_GENERATION_MAX_TOKENS = int(os.getenv("PROMPT_GENERATION_MAX_TOKENS", "512"))

        try:
            # 尝试根据提供的参数生成规则配置
            rules = LLMGenerator.generate_rule_config(
                tenant_id=account.current_tenant_id,
                instruction=args["instruction"],
                model_config=args["model_config"],
                no_variable=args["no_variable"],
                rule_config_max_tokens=PROMPT_GENERATION_MAX_TOKENS,
            )
        except ProviderTokenNotInitError as ex:
            # 处理提供者令牌未初始化异常
            raise ProviderNotInitializeError(ex.description)
        except QuotaExceededError:
            # 处理配额超出异常
            raise ProviderQuotaExceededError()
        except ModelCurrentlyNotSupportError:
            # 处理模型当前不支持异常
            raise ProviderModelCurrentlyNotSupportError()
        except InvokeError as e:
            # 处理调用异常
            raise CompletionRequestError(e.description)

        return rules  # 返回生成的规则配置


api.add_resource(RuleGenerateApi, "/rule-generate")
