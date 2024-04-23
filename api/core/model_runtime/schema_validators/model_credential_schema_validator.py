from core.model_runtime.entities.model_entities import ModelType
from core.model_runtime.entities.provider_entities import ModelCredentialSchema
from core.model_runtime.schema_validators.common_validator import CommonValidator


class ModelCredentialSchemaValidator(CommonValidator):
    """
    模型凭证架构验证器类，用于验证和过滤模型凭证。

    :param model_type: 模型类型，决定了模型凭证的验证规则。
    :param model_credential_schema: 模型凭证架构，定义了凭证的格式和要求。
    """

    def __init__(self, model_type: ModelType, model_credential_schema: ModelCredentialSchema):
        self.model_type = model_type  # 模型类型
        self.model_credential_schema = model_credential_schema  # 模型凭证架构

    def validate_and_filter(self, credentials: dict) -> dict:
        """
        验证模型凭证，并过滤掉不满足要求的凭证项。

        :param credentials: 待验证的模型凭证，为字典格式。
        :return: 经过验证和过滤后的凭证，只包含符合要求的项。
        """

        if self.model_credential_schema is None:
            raise ValueError("Model credential schema is None")  # 如果模型凭证架构为None，则抛出异常

        # 从模型凭证架构中获取凭证表单架构
        credential_form_schemas = self.model_credential_schema.credential_form_schemas

        credentials["__model_type"] = self.model_type.value  # 添加模型类型到凭证中

        # 使用凭证表单架构验证和过滤凭证
        return self._validate_and_filter_credential_form_schemas(credential_form_schemas, credentials)
