import openai
from httpx import Timeout

from core.model_runtime.errors.invoke import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
from core.model_runtime.model_providers.azure_openai._constant import AZURE_OPENAI_API_VERSION


class _CommonAzureOpenAI:
    """
    提供与Azure OpenAI服务交互的常用功能。
    """
    
    @staticmethod
    def _to_credential_kwargs(credentials: dict) -> dict:
        """
        将认证信息字典转换为调用时的参数字典。
        
        参数:
        - credentials: 一个包含OpenAI认证信息的字典。
        
        返回值:
        - 一个包含用于API调用的关键词参数的字典。
        """
        # 获取或设置OpenAI API版本
        api_version = credentials.get('openai_api_version', AZURE_OPENAI_API_VERSION)
        # 构建认证参数字典
        credentials_kwargs = {
            "api_key": credentials['openai_api_key'],  # API密钥
            "azure_endpoint": credentials['openai_api_base'],  # Azure端点
            "api_version": api_version,  # API版本
            "timeout": Timeout(315.0, read=300.0, write=10.0, connect=5.0),  # 超时设置
            "max_retries": 1,  # 最大重试次数
        }

        return credentials_kwargs

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        """
        定义调用过程中不同错误类型与OpenAI异常之间的映射。
        
        返回值:
        - 一个字典，将内部调用错误类型映射到相应的OpenAI异常列表。
        """
        return {
            InvokeConnectionError: [
                openai.APIConnectionError,
                openai.APITimeoutError
            ],
            InvokeServerUnavailableError: [
                openai.InternalServerError
            ],
            InvokeRateLimitError: [
                openai.RateLimitError
            ],
            InvokeAuthorizationError: [
                openai.AuthenticationError,
                openai.PermissionDeniedError
            ],
            InvokeBadRequestError: [
                openai.BadRequestError,
                openai.NotFoundError,
                openai.UnprocessableEntityError,
                openai.APIError
            ]
        }