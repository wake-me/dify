from core.model_runtime.entities.provider_entities import ProviderCredentialSchema
from core.model_runtime.schema_validators.common_validator import CommonValidator


class ProviderCredentialSchemaValidator(CommonValidator):
    """
    用于验证供应商凭证的合法性验证器类

    :param provider_credential_schema: 供应商凭证的模式，用于验证和过滤凭证信息
    """

    def __init__(self, provider_credential_schema: ProviderCredentialSchema):
        """
        初始化验证器

        :param provider_credential_schema: 详细定义了供应商凭证结构的模式对象
        """
        self.provider_credential_schema = provider_credential_schema

    def validate_and_filter(self, credentials: dict) -> dict:
        """
        验证并过滤供应商凭证

        对提供的凭证进行验证，确保它们符合预定义的模式。过滤掉不合法或未指定的凭证项，并返回验证通过的凭证。

        :param credentials: 待验证的供应商凭证字典
        :return: 验证通过的供应商凭证字典
        """
        # 获取供应商凭证模式中的凭证表单模式
        credential_form_schemas = self.provider_credential_schema.credential_form_schemas

        # 调用方法验证并过滤凭证
        return self._validate_and_filter_credential_form_schemas(credential_form_schemas, credentials)