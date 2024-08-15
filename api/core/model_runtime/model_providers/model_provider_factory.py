import logging
import os
from collections.abc import Sequence
from typing import Optional

from pydantic import BaseModel, ConfigDict

from core.helper.module_import_helper import load_single_subclass_from_source
from core.helper.position_helper import get_provider_position_map, sort_to_dict_by_position_map
from core.model_runtime.entities.model_entities import ModelType
from core.model_runtime.entities.provider_entities import ProviderConfig, ProviderEntity, SimpleProviderEntity
from core.model_runtime.model_providers.__base.model_provider import ModelProvider
from core.model_runtime.schema_validators.model_credential_schema_validator import ModelCredentialSchemaValidator
from core.model_runtime.schema_validators.provider_credential_schema_validator import ProviderCredentialSchemaValidator

logger = logging.getLogger(__name__)


class ModelProviderExtension(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    provider_instance: ModelProvider
    name: str
    position: Optional[int] = None


class ModelProviderFactory:
    model_provider_extensions: Optional[dict[str, ModelProviderExtension]] = None

    def __init__(self) -> None:
        """
        类的构造器，初始化时获取所有模型提供者。
        """
        self.get_providers()

    def get_providers(self) -> Sequence[ProviderEntity]:
        """
        获取所有模型提供者的信息。
        
        :return: 提供者信息列表，每个元素为一个ProviderEntity实例。
        """
        # 扫描并获取所有模型提供者的扩展信息
        model_provider_extensions = self._get_model_provider_map()

        # 遍历所有模型提供者扩展信息
        providers = []
        for model_provider_extension in model_provider_extensions.values():
            # get model_provider instance
            model_provider_instance = model_provider_extension.provider_instance

            # 获取提供者的架构信息
            provider_schema = model_provider_instance.get_provider_schema()

            # 遍历支持的模型类型，获取并添加预定义的模型
            for model_type in provider_schema.supported_model_types:
                models = model_provider_instance.models(model_type)
                if models:
                    provider_schema.models.extend(models)

            providers.append(provider_schema)

        # 返回所有收集到的提供者信息
        return providers

    def provider_credentials_validate(self, *, provider: str, credentials: dict) -> dict:
        """
        验证供应商凭证

        :param provider: 供应商名称
        :param credentials: 供应商凭证，凭证形式遵循`provider_credential_schema`定义。
        :return: 验证通过后的凭证信息
        """
        # 获取供应商实例
        model_provider_instance = self.get_provider_instance(provider)

        # 获取供应商方案
        provider_schema = model_provider_instance.get_provider_schema()

        # 获取provider_credential_schema，并根据规则验证凭证
        provider_credential_schema = provider_schema.provider_credential_schema

        if not provider_credential_schema:
            raise ValueError(f"Provider {provider} does not have provider_credential_schema")

        # validate provider credential schema
        validator = ProviderCredentialSchemaValidator(provider_credential_schema)
        filtered_credentials = validator.validate_and_filter(credentials)

        # 验证凭证信息，如果验证失败则抛出异常
        model_provider_instance.validate_provider_credentials(filtered_credentials)

        return filtered_credentials

    def model_credentials_validate(
        self, *, provider: str, model_type: ModelType, model: str, credentials: dict
    ) -> dict:
        """
        验证模型凭证

        :param provider: 提供者名称
        :param model_type: 模型类型
        :param model: 模型名称
        :param credentials: 模型凭证，凭证形式定义在`model_credential_schema`中。
        :return: 验证过滤后的凭证
        """
        # 获取提供者实例
        model_provider_instance = self.get_provider_instance(provider)

        # 获取提供者方案
        provider_schema = model_provider_instance.get_provider_schema()

        # 获取 model_credential_schema 并根据规则验证凭证
        model_credential_schema = provider_schema.model_credential_schema

        if not model_credential_schema:
            raise ValueError(f"Provider {provider} does not have model_credential_schema")

        # validate model credential schema
        validator = ModelCredentialSchemaValidator(model_type, model_credential_schema)
        filtered_credentials = validator.validate_and_filter(credentials)

        # 获取模型类型对应的模型实例
        model_instance = model_provider_instance.get_model_instance(model_type)

        # 调用模型类型的 validate_credentials 方法验证凭证，验证失败则抛出异常
        model_instance.validate_credentials(model, filtered_credentials)

        return filtered_credentials

    def get_models(
        self,
        *,
        provider: Optional[str] = None,
        model_type: Optional[ModelType] = None,
        provider_configs: Optional[list[ProviderConfig]] = None,
    ) -> list[SimpleProviderEntity]:
        """
        根据给定的模型类型获取所有模型

        :param provider: 提供者名称
        :param model_type: 模型类型
        :param provider_configs: 提供者配置列表
        :return: 模型列表
        """
        provider_configs = provider_configs or []

        # scan all providers
        model_provider_extensions = self._get_model_provider_map()

        # 将提供者配置转换为字典
        provider_credentials_dict = {}
        for provider_config in provider_configs:
            provider_credentials_dict[provider_config.provider] = provider_config.credentials

        # 遍历所有model_provider_extensions
        providers = []
        for name, model_provider_extension in model_provider_extensions.items():
            # 如果指定了提供者且当前提供者不匹配，则跳过
            if provider and name != provider:
                continue

            # 获取model_provider实例
            model_provider_instance = model_provider_extension.provider_instance

            # 获取提供者架构
            provider_schema = model_provider_instance.get_provider_schema()

            model_types = provider_schema.supported_model_types
            if model_type:
                # 如果指定了模型类型且不匹配，则跳过
                if model_type not in model_types:
                    continue

                # 将模型类型缩小为指定的模型类型
                model_types = [model_type]

            all_model_type_models = []
            for model_type in model_types:
                # 根据给定的模型类型获取预定义的模型
                models = model_provider_instance.models(
                    model_type=model_type,
                )

                all_model_type_models.extend(models)

            simple_provider_schema = provider_schema.to_simple_provider()
            simple_provider_schema.models.extend(all_model_type_models)

            providers.append(simple_provider_schema)

        return providers

    def get_provider_instance(self, provider: str) -> ModelProvider:
        """
        通过提供者名称获取提供者实例
        :param provider: 提供者名称
        :return: 提供者实例
        """
        # 扫描所有提供者
        model_provider_extensions = self._get_model_provider_map()

        # 获取指定提供的扩展
        model_provider_extension = model_provider_extensions.get(provider)
        if not model_provider_extension:
            raise Exception(f"Invalid provider: {provider}")

        # 获取提供者实例
        model_provider_instance = model_provider_extension.provider_instance

        return model_provider_instance

    def _get_model_provider_map(self) -> dict[str, ModelProviderExtension]:
        """
        Retrieves the model provider map.

        This method retrieves the model provider map, which is a dictionary containing the model provider names as keys
        and instances of `ModelProviderExtension` as values. The model provider map is used to store information about
        available model providers.

        Returns:
            A dictionary containing the model provider map.

        Raises:
            None.
        """
        if self.model_provider_extensions:
            return self.model_provider_extensions

        # get the path of current classes
        current_path = os.path.abspath(__file__)
        model_providers_path = os.path.dirname(current_path)

        # 确定模型提供者目录下所有不以'__'开头的子目录路径
        model_provider_dir_paths = [
            os.path.join(model_providers_path, model_provider_dir)
            for model_provider_dir in os.listdir(model_providers_path)
            if not model_provider_dir.startswith("__")
            and os.path.isdir(os.path.join(model_providers_path, model_provider_dir))
        ]

        # get _position.yaml file path
        position_map = get_provider_position_map(model_providers_path)

        # 遍历所有模型提供者目录路径
        model_providers: list[ModelProviderExtension] = []
        for model_provider_dir_path in model_provider_dir_paths:
            # 获取模型提供者目录的名称
            model_provider_name = os.path.basename(model_provider_dir_path)

            file_names = os.listdir(model_provider_dir_path)

            if (model_provider_name + ".py") not in file_names:
                logger.warning(f"Missing {model_provider_name}.py file in {model_provider_dir_path}, Skip.")
                continue

            # Dynamic loading {model_provider_name}.py file and find the subclass of ModelProvider
            py_path = os.path.join(model_provider_dir_path, model_provider_name + ".py")
            model_provider_class = load_single_subclass_from_source(
                module_name=f"core.model_runtime.model_providers.{model_provider_name}.{model_provider_name}",
                script_path=py_path,
                parent_type=ModelProvider,
            )

            # 如果找不到子类，则记录警告并跳过
            if not model_provider_class:
                logger.warning(f"Missing Model Provider Class that extends ModelProvider in {py_path}, Skip.")
                continue

            if f"{model_provider_name}.yaml" not in file_names:
                logger.warning(f"Missing {model_provider_name}.yaml file in {model_provider_dir_path}, Skip.")
                continue

            model_providers.append(
                ModelProviderExtension(
                    name=model_provider_name,
                    provider_instance=model_provider_class(),
                    position=position_map.get(model_provider_name),
                )
            )

        # 根据位置映射信息对模型提供者进行排序，并存储为字典
        sorted_extensions = sort_to_dict_by_position_map(position_map, model_providers, lambda x: x.name)

        # 更新并返回排序后的模型提供者扩展
        self.model_provider_extensions = sorted_extensions
        return sorted_extensions
