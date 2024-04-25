import logging

from core.model_runtime.entities.model_entities import ModelType
from core.model_runtime.errors.validate import CredentialsValidateFailedError
from core.model_runtime.model_providers.__base.model_provider import ModelProvider

logger = logging.getLogger(__name__)


class AnthropicProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: dict) -> None:
        """
        验证提供者凭证的有效性

        如果验证失败，则抛出异常

        :param credentials: 提供者的凭证，其形式由`provider_credential_schema`定义。
        """
        try:
            model_instance = self.get_model_instance(ModelType.LLM)

            # 使用`claude-instant-1`模型进行验证
            model_instance.validate_credentials(
                model='claude-instant-1.2',
                credentials=credentials
            )
        except CredentialsValidateFailedError as ex:
            # 凭证验证失败时抛出异常
            raise ex
        except Exception as ex:
            # 记录异常并抛出，以处理验证过程中的任何其他异常
            logger.exception(f'{self.get_provider_schema().provider} credentials validate failed')
            raise ex