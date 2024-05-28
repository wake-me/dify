import decimal
import os
from abc import ABC, abstractmethod
from typing import Optional

from core.model_runtime.entities.common_entities import I18nObject
from core.model_runtime.entities.defaults import PARAMETER_RULE_TEMPLATE
from core.model_runtime.entities.model_entities import (
    AIModelEntity,
    DefaultParameterName,
    FetchFrom,
    ModelType,
    PriceConfig,
    PriceInfo,
    PriceType,
)
from core.model_runtime.errors.invoke import InvokeAuthorizationError, InvokeError
from core.model_runtime.model_providers.__base.tokenizers.gpt2_tokenzier import GPT2Tokenizer
from core.tools.utils.yaml_utils import load_yaml_file
from core.utils.position_helper import get_position_map, sort_by_position_map


class AIModel(ABC):
    """
    所有模型的基类。
    """
    model_type: ModelType  # 模型类型
    model_schemas: list[AIModelEntity] = None  # 模型架构列表
    started_at: float = 0  # 模型启动时间（秒）

    @abstractmethod
    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        验证模型凭证的正确性。
        
        :param model: 模型名称
        :param credentials: 模型凭证
        :return: 无返回值
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        """
        将模型调用错误映射到统一错误。
        键是抛给调用者的错误类型；
        值是模型抛出的错误类型，
        需要被转换成统一的错误类型给调用者。
        
        :return: 调用错误映射字典
        """
        raise NotImplementedError
    def _transform_invoke_error(self, error: Exception) -> InvokeError:
        """
        将调用错误转换为统一的错误格式
        
        :param error: 模型调用时发生的错误
        :type error: Exception
        :return: 统一格式的调用错误
        :rtype: InvokeError
        """
        # 获取提供者名称，用于错误信息标识
        provider_name = self.__class__.__module__.split('.')[-3]

        # 遍历调用错误映射，寻找匹配的错误类型
        for invoke_error, model_errors in self._invoke_error_mapping.items():
            # 如果错误类型匹配，则根据错误类型返回不同的错误信息
            if isinstance(error, tuple(model_errors)):
                # 特殊处理授权错误
                if invoke_error == InvokeAuthorizationError:
                    return invoke_error(description=f"[{provider_name}] 提供的模型凭证不正确，请检查后重试。 ")

                # 返回特定的调用错误信息
                return invoke_error(description=f"[{provider_name}] {invoke_error.description}, {str(error)}")

        # 如果没有匹配到特定的调用错误类型，返回通用的调用错误信息
        return InvokeError(description=f"[{provider_name}] 错误： {str(error)}")

    def get_price(self, model: str, credentials: dict, price_type: PriceType, tokens: int) -> PriceInfo:
        """
        为指定模型和令牌数量获取价格信息

        :param model: 模型名称
        :param credentials: 模型凭证
        :param price_type: 价格类型
        :param tokens: 令牌数量
        :return: 价格信息
        """
        # 获取模型架构
        model_schema = self.get_model_schema(model, credentials)

        # 从预定义的模型架构中获取价格配置
        price_config: Optional[PriceConfig] = None
        if model_schema:
            price_config: PriceConfig = model_schema.pricing

        # 获取单位价格
        unit_price = None
        if price_config:
            if price_type == PriceType.INPUT:
                unit_price = price_config.input
            elif price_type == PriceType.OUTPUT and price_config.output is not None:
                unit_price = price_config.output

        # 若未获取到单位价格，则返回默认价格信息
        if unit_price is None:
            return PriceInfo(
                unit_price=decimal.Decimal('0.0'),
                unit=decimal.Decimal('0.0'),
                total_amount=decimal.Decimal('0.0'),
                currency="USD",
            )

        # 计算总价
        total_amount = tokens * unit_price * price_config.unit
        total_amount = total_amount.quantize(decimal.Decimal('0.0000001'), rounding=decimal.ROUND_HALF_UP)

        return PriceInfo(
            unit_price=unit_price,
            unit=price_config.unit,
            total_amount=total_amount,
            currency=price_config.currency,
        )

    def predefined_models(self) -> list[AIModelEntity]:
        """
        获取给定提供者的所有预定义模型。

        该函数不接受参数。

        :return: 返回一个AIModelEntity实体列表，包含所有预定义的模型。
        """
        if self.model_schemas:
            return self.model_schemas

        model_schemas = []

        # 获取模块名称
        model_type = self.__class__.__module__.split('.')[-1]

        # 获取提供者名称
        provider_name = self.__class__.__module__.split('.')[-3]

        # 获取当前类的路径
        current_path = os.path.abspath(__file__)
        # 获取当前路径的父路径
        provider_model_type_path = os.path.join(os.path.dirname(os.path.dirname(current_path)), provider_name, model_type)

        # 获取provider_model_type_path路径下所有不以'__'开头的yaml文件路径
        model_schema_yaml_paths = [
            os.path.join(provider_model_type_path, model_schema_yaml)
            for model_schema_yaml in os.listdir(provider_model_type_path)
            if not model_schema_yaml.startswith('__')
            and not model_schema_yaml.startswith('_')
            and os.path.isfile(os.path.join(provider_model_type_path, model_schema_yaml))
            and model_schema_yaml.endswith('.yaml')
        ]

        # 获取_position.yaml文件的路径
        position_map = get_position_map(provider_model_type_path)

        # 遍历所有model_schema_yaml_paths
        for model_schema_yaml_path in model_schema_yaml_paths:
            # read yaml data from yaml file
            yaml_data = load_yaml_file(model_schema_yaml_path, ignore_error=True)

            new_parameter_rules = []
            for parameter_rule in yaml_data.get('parameter_rules', []):
                # 尝试使用模板更新参数规则
                if 'use_template' in parameter_rule:
                    try:
                        default_parameter_name = DefaultParameterName.value_of(parameter_rule['use_template'])
                        default_parameter_rule = self._get_default_parameter_rule_variable_map(default_parameter_name)
                        copy_default_parameter_rule = default_parameter_rule.copy()
                        copy_default_parameter_rule.update(parameter_rule)
                        parameter_rule = copy_default_parameter_rule
                    except ValueError:
                        pass

                # 更新参数规则的标签
                if 'label' not in parameter_rule:
                    parameter_rule['label'] = {
                        'zh_Hans': parameter_rule['name'],
                        'en_US': parameter_rule['name']
                    }

                new_parameter_rules.append(parameter_rule)

            # 更新yaml数据中的参数规则和标签
            yaml_data['parameter_rules'] = new_parameter_rules
            if 'label' not in yaml_data:
                yaml_data['label'] = {
                    'zh_Hans': yaml_data['model'],
                    'en_US': yaml_data['model']
                }

            yaml_data['fetch_from'] = FetchFrom.PREDEFINED_MODEL.value

            try:
                # 将yaml数据转换为实体
                model_schema = AIModelEntity(**yaml_data)
            except Exception as e:
                model_schema_yaml_file_name = os.path.basename(model_schema_yaml_path).rstrip(".yaml")
                raise Exception(f'Invalid model schema for {provider_name}.{model_type}.{model_schema_yaml_file_name}:'
                                f' {str(e)}')

            # 缓存模型架构
            model_schemas.append(model_schema)

        # 根据位置信息排序模型架构
        model_schemas = sort_by_position_map(position_map, model_schemas, lambda x: x.model)

        # 缓存模型架构
        self.model_schemas = model_schemas

        return model_schemas

    def get_model_schema(self, model: str, credentials: Optional[dict] = None) -> Optional[AIModelEntity]:
        """
        通过模型名称和凭证获取模型架构

        :param model: 模型名称
        :param credentials: 模型凭证
        :return: 模型架构，如果找不到则返回None
        """
        # 获取预定义的模型列表
        models = self.predefined_models()

        # 通过模型名称创建模型映射
        model_map = {model.model: model for model in models}
        if model in model_map:
            return model_map[model]

        # 如果提供了凭证，尝试从凭证获取可定制模型的架构
        if credentials:
            model_schema = self.get_customizable_model_schema_from_credentials(model, credentials)
            if model_schema:
                return model_schema

        return None

    def get_customizable_model_schema_from_credentials(self, model: str, credentials: dict) -> Optional[AIModelEntity]:
        """
        从凭证中获取可定制的模型架构
        
        :param model: 模型名称
        :param credentials: 模型凭证
        :return: 模型架构
        """
        # 根据模型名称和凭证获取可定制的模型架构
        return self._get_customizable_model_schema(model, credentials)
        
    def _get_customizable_model_schema(self, model: str, credentials: dict) -> Optional[AIModelEntity]:
        """
        获取可定制模型的架构，并填充模板。

        参数:
        model: 字符串，指定模型的名称。
        credentials: 字典，包含获取模型架构所需的认证信息。

        返回值:
        Optional[AIModelEntity]: 如果成功获取模型架构，则返回 AIModelEntity 对象；如果无法获取，则返回 None。
        """
        # 尝试获取指定模型的可定制架构
        schema = self.get_customizable_model_schema(model, credentials)

        if not schema:
            return None
        
        # 根据模板填充架构参数规则
        new_parameter_rules = []
        for parameter_rule in schema.parameter_rules:
            if parameter_rule.use_template:
                try:
                    # 将模板名称转换为默认参数名
                    default_parameter_name = DefaultParameterName.value_of(parameter_rule.use_template)
                    # 获取对应默认参数的规则映射
                    default_parameter_rule = self._get_default_parameter_rule_variable_map(default_parameter_name)
                    # 填充参数规则的各个属性
                    if not parameter_rule.max and 'max' in default_parameter_rule:
                        parameter_rule.max = default_parameter_rule['max']
                    if not parameter_rule.min and 'min' in default_parameter_rule:
                        parameter_rule.min = default_parameter_rule['min']
                    if not parameter_rule.default and 'default' in default_parameter_rule:
                        parameter_rule.default = default_parameter_rule['default']
                    if not parameter_rule.precision and 'precision' in default_parameter_rule:
                        parameter_rule.precision = default_parameter_rule['precision']
                    if not parameter_rule.required and 'required' in default_parameter_rule:
                        parameter_rule.required = default_parameter_rule['required']
                    if not parameter_rule.help and 'help' in default_parameter_rule:
                        parameter_rule.help = I18nObject(
                            en_US=default_parameter_rule['help']['en_US'],
                        )
                    # 国际化帮助信息
                    if not parameter_rule.help.en_US and ('help' in default_parameter_rule and 'en_US' in default_parameter_rule['help']):
                        parameter_rule.help.en_US = default_parameter_rule['help']['en_US']
                    if not parameter_rule.help.zh_Hans and ('help' in default_parameter_rule and 'zh_Hans' in default_parameter_rule['help']):
                        parameter_rule.help.zh_Hans = default_parameter_rule['help'].get('zh_Hans', default_parameter_rule['help']['en_US'])
                except ValueError:
                    # 忽略无效的模板名称
                    pass

            new_parameter_rules.append(parameter_rule)

        schema.parameter_rules = new_parameter_rules

        return schema

    def get_customizable_model_schema(self, model: str, credentials: dict) -> Optional[AIModelEntity]:
        """
        获取可定制模型的架构

        :param model: 模型名称
        :param credentials: 模型凭证
        :return: 模型架构
        """
        return None

    def _get_default_parameter_rule_variable_map(self, name: DefaultParameterName) -> dict:
        """
        获取给定名称的默认参数规则

        :param name: 参数名称
        :return: 参数规则字典
        """
        # 尝试从预定义模板中获取指定名称的参数规则
        default_parameter_rule = PARAMETER_RULE_TEMPLATE.get(name)

        # 如果未找到指定的参数规则，则抛出异常
        if not default_parameter_rule:
            raise Exception(f'Invalid model parameter rule name {name}')

        return default_parameter_rule

    def _get_num_tokens_by_gpt2(self, text: str) -> int:
        """
        通过GPT-2获取给定提示消息的令牌数量
        一些提供者模型没有提供获取令牌数量的接口。
        这里使用gpt2分词器来计算令牌数量。
        此方法可以在离线状态下执行，且gpt2分词器已在项目中缓存。

        :param text: 提示文本的纯文本。需要将原始消息转换为纯文本
        :return: 令牌数量
        """
        return GPT2Tokenizer.get_num_tokens(text)