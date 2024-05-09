from core.app.app_config.entities import AppConfig, VariableEntity


class BaseAppGenerator:
    def _get_cleaned_inputs(self, user_inputs: dict, app_config: AppConfig):
        """
        清洗用户输入的数据，根据应用配置（app_config）来验证和处理输入值。
        
        参数:
        - user_inputs: dict, 用户提供的输入数据字典。
        - app_config: AppConfig, 应用的配置对象，包含变量配置信息。
        
        返回值:
        - filtered_inputs: dict, 清洗后的用户输入数据字典，移除了无效或不满足条件的输入。
        
        抛出:
        - ValueError: 如果某个必需的字段未提供，或者字段值类型不匹配、超出最大长度、不是预期的选项之一，则抛出此异常。
        """
        if user_inputs is None:
            user_inputs = {}

        filtered_inputs = {}

        # 根据表单配置过滤输入变量，处理必填字段、默认值和选项值
        variables = app_config.variables
        for variable_config in variables:
            variable = variable_config.variable

            if (variable not in user_inputs
                    or user_inputs[variable] is None
                    or (isinstance(user_inputs[variable], str) and user_inputs[variable] == '')):
                if variable_config.required:
                    raise ValueError(f"{variable} is required in input form")
                else:
                    filtered_inputs[variable] = variable_config.default if variable_config.default is not None else ""
                    continue

            value = user_inputs[variable]

            if value is not None:
                if variable_config.type != VariableEntity.Type.NUMBER and not isinstance(value, str):
                    raise ValueError(f"{variable} in input form must be a string")
                elif variable_config.type == VariableEntity.Type.NUMBER and isinstance(value, str):
                    if '.' in value:
                        value = float(value)
                    else:
                        value = int(value)

            # 处理选择类型字段的选项验证
            if variable_config.type == VariableEntity.Type.SELECT:
                options = variable_config.options if variable_config.options is not None else []
                if value not in options:
                    raise ValueError(f"{variable} in input form must be one of the following: {options}")
            elif variable_config.type in [VariableEntity.Type.TEXT_INPUT, VariableEntity.Type.PARAGRAPH]:
                if variable_config.max_length is not None:
                    max_length = variable_config.max_length
                    if len(value) > max_length:
                        raise ValueError(f'{variable} in input form must be less than {max_length} characters')

            if value and isinstance(value, str):
                filtered_inputs[variable] = value.replace('\x00', '')
            else:
                filtered_inputs[variable] = value if value is not None else None

        return filtered_inputs