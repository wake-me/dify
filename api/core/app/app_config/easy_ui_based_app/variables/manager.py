import re

from core.app.app_config.entities import ExternalDataVariableEntity, VariableEntity
from core.external_data_tool.factory import ExternalDataToolFactory


class BasicVariablesConfigManager:
    @classmethod
    def convert(cls, config: dict) -> tuple[list[VariableEntity], list[ExternalDataVariableEntity]]:
        """
        将模型配置转换为模型配置。

        :param config: 模型配置参数
        :return: 一个元组，包含两个元素：变量列表和外部数据变量列表
        """
        external_data_variables = []  # 外部数据变量列表
        variables = []  # 变量列表

        # 处理旧的external_data_tools
        external_data_tools = config.get('external_data_tools', [])
        for external_data_tool in external_data_tools:
            # 如果未启用或者启用标志为False，则跳过
            if 'enabled' not in external_data_tool or not external_data_tool['enabled']:
                continue

            external_data_variables.append(
                ExternalDataVariableEntity(
                    variable=external_data_tool['variable'],
                    type=external_data_tool['type'],
                    config=external_data_tool['config']
                )
            )

        # 处理variables和external_data_tools
        for variable in config.get('user_input_form', []):
            typ = list(variable.keys())[0]
            if typ == 'external_data_tool':
                val = variable[typ]
                # 如果缺少config，则跳过
                if 'config' not in val:
                    continue

                external_data_variables.append(
                    ExternalDataVariableEntity(
                        variable=val['variable'],
                        type=val['type'],
                        config=val['config']
                    )
                )
            elif typ in [
                VariableEntity.Type.TEXT_INPUT.value,
                VariableEntity.Type.PARAGRAPH.value,
                VariableEntity.Type.NUMBER.value,
            ]:
                variables.append(
                    VariableEntity(
                        type=VariableEntity.Type.value_of(typ),
                        variable=variable[typ].get('variable'),
                        description=variable[typ].get('description'),
                        label=variable[typ].get('label'),
                        required=variable[typ].get('required', False),
                        max_length=variable[typ].get('max_length'),
                        default=variable[typ].get('default'),
                    )
                )
            elif typ == VariableEntity.Type.SELECT.value:
                variables.append(
                    VariableEntity(
                        type=VariableEntity.Type.SELECT,
                        variable=variable[typ].get('variable'),
                        description=variable[typ].get('description'),
                        label=variable[typ].get('label'),
                        required=variable[typ].get('required', False),
                        options=variable[typ].get('options'),
                        default=variable[typ].get('default'),
                    )
                )

        return variables, external_data_variables

    @classmethod
    def validate_and_set_defaults(cls, tenant_id: str, config: dict) -> tuple[dict, list[str]]:
        """
        验证并设置用户输入表单的默认值。

        :param tenant_id: 工作空间ID
        :param config: 应用模型配置参数
        :return: 一个元组，包含两个元素：配置字典和相关配置键列表
        """
        related_config_keys = []
        # 验证并设置变量的默认值
        config, current_related_config_keys = cls.validate_variables_and_set_defaults(config)
        related_config_keys.extend(current_related_config_keys)

        # 验证并设置外部数据工具的默认值
        config, current_related_config_keys = cls.validate_external_data_tools_and_set_defaults(tenant_id, config)
        related_config_keys.extend(current_related_config_keys)

        return config, related_config_keys

    @classmethod
    def validate_variables_and_set_defaults(cls, config: dict) -> tuple[dict, list[str]]:
        """
        验证并设置用户输入表单的默认值。

        :param config: 应用模型配置参数
        :return: 一个元组，包含两个元素：配置字典和相关配置键列表
        """
        if not config.get("user_input_form"):
            config["user_input_form"] = []

        if not isinstance(config["user_input_form"], list):
            raise ValueError("user_input_form must be a list of objects")

        variables = []
        for item in config["user_input_form"]:
            key = list(item.keys())[0]
            # 验证表单项类型
            if key not in ["text-input", "select", "paragraph", "number", "external_data_tool"]:
                raise ValueError("Keys in user_input_form list can only be 'text-input', 'paragraph'  or 'select'")

            form_item = item[key]
            # 验证标签是否存在且为字符串类型
            if 'label' not in form_item:
                raise ValueError("label is required in user_input_form")

            if not isinstance(form_item["label"], str):
                raise ValueError("label in user_input_form must be of string type")

            # 验证变量名是否存在且为字符串类型，且不能以数字开头
            if 'variable' not in form_item:
                raise ValueError("variable is required in user_input_form")

            if not isinstance(form_item["variable"], str):
                raise ValueError("variable in user_input_form must be of string type")

            pattern = re.compile(r"^(?!\d)[\u4e00-\u9fa5A-Za-z0-9_\U0001F300-\U0001F64F\U0001F680-\U0001F6FF]{1,100}$")
            if pattern.match(form_item["variable"]) is None:
                raise ValueError("variable in user_input_form must be a string, "
                                 "and cannot start with a number")

            variables.append(form_item["variable"])

            # 设置required字段的默认值为False
            if 'required' not in form_item or not form_item["required"]:
                form_item["required"] = False

            if not isinstance(form_item["required"], bool):
                raise ValueError("required in user_input_form must be of boolean type")

            # 如果是选择类型，验证options是否存在且为字符串列表，检查default值是否在options中
            if key == "select":
                if 'options' not in form_item or not form_item["options"]:
                    form_item["options"] = []

                if not isinstance(form_item["options"], list):
                    raise ValueError("options in user_input_form must be a list of strings")

                if "default" in form_item and form_item['default'] \
                        and form_item["default"] not in form_item["options"]:
                    raise ValueError("default value in user_input_form must be in the options list")

        return config, ["user_input_form"]

    @classmethod
    def validate_external_data_tools_and_set_defaults(cls, tenant_id: str, config: dict) -> tuple[dict, list[str]]:
        """
        验证并设置外部数据获取功能的默认值。

        :param tenant_id: 工作空间ID
        :param config: 应用模型配置参数
        :return: 一个元组，包含两个元素：配置字典和相关配置键列表
        """
        if not config.get("external_data_tools"):
            config["external_data_tools"] = []

        if not isinstance(config["external_data_tools"], list):
            raise ValueError("external_data_tools must be of list type")

        for tool in config["external_data_tools"]:
            # 设置enabled字段的默认值为False
            if "enabled" not in tool or not tool["enabled"]:
                tool["enabled"] = False

            if not tool["enabled"]:
                continue

            if "type" not in tool or not tool["type"]:
                raise ValueError("external_data_tools[].type is required")

            typ = tool["type"]
            config = tool["config"]

            ExternalDataToolFactory.validate_config(
                name=typ,
                tenant_id=tenant_id,
                config=config
            )

        return config, ["external_data_tools"]