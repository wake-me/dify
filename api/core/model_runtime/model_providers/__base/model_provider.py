import os
from abc import ABC, abstractmethod
from typing import Optional

from core.helper.module_import_helper import get_subclasses_from_module, import_module_from_source
from core.model_runtime.entities.model_entities import AIModelEntity, ModelType
from core.model_runtime.entities.provider_entities import ProviderEntity
from core.model_runtime.model_providers.__base.ai_model import AIModel
from core.tools.utils.yaml_utils import load_yaml_file


class ModelProvider(ABC):
    provider_schema: Optional[ProviderEntity] = None
    model_instance_map: dict[str, AIModel] = {}

    @abstractmethod
    def validate_provider_credentials(self, credentials: dict) -> None:
        """
        验证提供者凭证的合法性。
        你可以选择任何模型类型的验证凭证方法或自己实现验证方法，例如：通过获取模型列表API。

        如果验证失败，则抛出异常。

        :param credentials: 提供者凭证，凭证形式定义在`provider_credential_schema`中。
        """
        raise NotImplementedError

    def get_provider_schema(self) -> ProviderEntity:
        """
        Get provider schema
    
        :return: provider schema
        """
        if self.provider_schema:
            return self.provider_schema
    
        # get dirname of the current path
        provider_name = self.__class__.__module__.split('.')[-1]

        # 获取模型提供者类所在的路径
        base_path = os.path.abspath(__file__)
        current_path = os.path.join(os.path.dirname(os.path.dirname(base_path)), provider_name)
    
        # read provider schema from yaml file
        yaml_path = os.path.join(current_path, f'{provider_name}.yaml')
        yaml_data = load_yaml_file(yaml_path, ignore_error=True)
    
        try:
            # 将yaml数据转换为实体
            provider_schema = ProviderEntity(**yaml_data)
        except Exception as e:
            raise Exception(f'Invalid provider schema for {provider_name}: {str(e)}')

        # 缓存模式
        self.provider_schema = provider_schema
    
        return provider_schema

    def models(self, model_type: ModelType) -> list[AIModelEntity]:
        """
        根据给定的模型类型获取所有模型。

        :param model_type: 模型类型，定义在`ModelType`中。
        :return: 模型列表。
        """
        provider_schema = self.get_provider_schema()
        if model_type not in provider_schema.supported_model_types:
            return []

        # 获取指定模型类型的模型实例
        model_instance = self.get_model_instance(model_type)

        # 获取预定义的模型
        models = model_instance.predefined_models()

        # 返回模型列表
        return models

    def get_model_instance(self, model_type: ModelType) -> AIModel:
        """
        获取模型实例。

        :param model_type: 模型类型，定义在`ModelType`中。
        :return: 返回模型实例。
        """
        # get dirname of the current path
        provider_name = self.__class__.__module__.split(".")[-1]

        if f"{provider_name}.{model_type.value}" in self.model_instance_map:
            return self.model_instance_map[f"{provider_name}.{model_type.value}"]

        # 获取模型类型类的路径
        base_path = os.path.abspath(__file__)
        model_type_name = model_type.value.replace('-', '_')
        model_type_path = os.path.join(os.path.dirname(os.path.dirname(base_path)), provider_name, model_type_name)
        model_type_py_path = os.path.join(model_type_path, f'{model_type_name}.py')

        if not os.path.isdir(model_type_path) or not os.path.exists(model_type_py_path):
            raise Exception(f'Invalid model type {model_type} for provider {provider_name}')

        # 如果模型类型的路径不存在或模型的py文件不存在，则抛出异常
        parent_module = '.'.join(self.__class__.__module__.split('.')[:-1])
        mod = import_module_from_source(
            module_name=f"{parent_module}.{model_type_name}.{model_type_name}", py_file_path=model_type_py_path
        )
        model_class = next(
            filter(
                lambda x: x.__module__ == mod.__name__ and not x.__abstractmethods__,
                get_subclasses_from_module(mod, AIModel),
            ),
            None,
        )
        if not model_class:
            raise Exception(f"Missing AIModel Class for model type {model_type} in {model_type_py_path}")

        model_instance_map = model_class()
        self.model_instance_map[f"{provider_name}.{model_type.value}"] = model_instance_map

        return model_instance_map
