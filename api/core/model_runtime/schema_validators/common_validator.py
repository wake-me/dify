from typing import Optional

from core.model_runtime.entities.provider_entities import CredentialFormSchema, FormType


class CommonValidator:
    def _validate_and_filter_credential_form_schemas(self,
                                                        credential_form_schemas: list[CredentialFormSchema],
                                                        credentials: dict) -> dict:
        """
        验证并过滤凭证表单模式。
        
        此函数根据给定的凭证表单模式和提供的凭证，首先筛选出需要验证的表单模式，然后验证这些表单模式对应的凭证信息。
        
        :param credential_form_schemas: 凭证表单模式列表，每个表单模式包含变量、展示条件等信息。
        :param credentials: 包含凭证信息的字典，键为变量名，值为凭证值。
        :return: 一个字典，包含验证通过的凭证信息，键为变量名，值为凭证值。
        """
        # 初始化一个字典，用于存储需要验证的凭证表单模式
        need_validate_credential_form_schema_map = {}
        for credential_form_schema in credential_form_schemas:
            # 如果表单模式设置为不显示，则直接加入到需要验证的表单模式字典中
            if not credential_form_schema.show_on:
                need_validate_credential_form_schema_map[credential_form_schema.variable] = credential_form_schema
                continue

            # 检查表单模式的所有展示条件是否匹配
            all_show_on_match = True
            for show_on_object in credential_form_schema.show_on:
                # 如果展示条件中的变量不存在于凭证中，则不匹配
                if show_on_object.variable not in credentials:
                    all_show_on_match = False
                    break

                # 如果凭证中的变量值与展示条件的值不匹配，则不匹配
                if credentials[show_on_object.variable] != show_on_object.value:
                    all_show_on_match = False
                    break

            # 如果所有展示条件都匹配，则加入到需要验证的表单模式字典中
            if all_show_on_match:
                need_validate_credential_form_schema_map[credential_form_schema.variable] = credential_form_schema

        # 遍历需要验证的凭证表单模式，对每个模式进行验证，并收集验证通过的凭证信息
        validated_credentials = {}
        for credential_form_schema in need_validate_credential_form_schema_map.values():
            # 验证凭证表单模式，并将验证通过的凭证信息添加到结果字典中
            result = self._validate_credential_form_schema(credential_form_schema, credentials)
            if result:
                validated_credentials[credential_form_schema.variable] = result

        return validated_credentials

    def _validate_credential_form_schema(self, credential_form_schema: CredentialFormSchema, credentials: dict) \
            -> Optional[str]:
        """
        验证凭证表单架构

        :param credential_form_schema: 凭证表单架构
        :param credentials: 凭证信息
        :return: 验证通过的凭证信息值
        """
        # 检查凭证信息中是否存在指定变量，若不存在或值为空，则根据是否必需抛出异常或返回默认值
        if credential_form_schema.variable not in credentials or not credentials[credential_form_schema.variable]:
            # 如果该变量是必需的，则抛出异常
            if credential_form_schema.required:
                raise ValueError(f'Variable {credential_form_schema.variable} is required')
            else:
                # 如果是非必需的，并且有默认值，则返回默认值，否则返回None
                if credential_form_schema.default:
                    return credential_form_schema.default
                else:
                    return None

        # 从凭证信息中获取对应变量的值
        value = credentials[credential_form_schema.variable]

        # 如果设置了最大长度，进行长度验证，若超过最大长度则抛出异常
        if credential_form_schema.max_length:
            if len(value) > credential_form_schema.max_length:
                raise ValueError(f'Variable {credential_form_schema.variable} length should not greater than {credential_form_schema.max_length}')

        # 验证变量值的类型，必须为字符串类型，否则抛出异常
        if not isinstance(value, str):
            raise ValueError(f'Variable {credential_form_schema.variable} should be string')

        # 根据表单类型进行不同规则的验证
        if credential_form_schema.type in [FormType.SELECT, FormType.RADIO]:
            # 如果是选择类型，验证值是否在选项范围内，若不在则抛出异常
            if credential_form_schema.options:
                if value not in [option.value for option in credential_form_schema.options]:
                    raise ValueError(f'Variable {credential_form_schema.variable} is not in options')

        if credential_form_schema.type == FormType.SWITCH:
            # 如果是开关类型，验证值是否为['true', 'false']之一，否则抛出异常，并转换为布尔值
            if value.lower() not in ['true', 'false']:
                raise ValueError(f'Variable {credential_form_schema.variable} should be true or false')

            value = True if value.lower() == 'true' else False

        return value
