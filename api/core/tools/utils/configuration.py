import os
from copy import deepcopy
from typing import Any, Union

from pydantic import BaseModel
from yaml import FullLoader, load

from core.helper import encrypter
from core.helper.tool_parameter_cache import ToolParameterCache, ToolParameterCacheType
from core.helper.tool_provider_cache import ToolProviderCredentialsCache, ToolProviderCredentialsCacheType
from core.tools.entities.tool_entities import (
    ModelToolConfiguration,
    ModelToolProviderConfiguration,
    ToolParameter,
    ToolProviderCredentials,
)
from core.tools.provider.tool_provider import ToolProviderController
from core.tools.tool.tool import Tool


class ToolConfigurationManager(BaseModel):
    # ToolConfigurationManager类继承自BaseModel，用于管理工具配置。
    tenant_id: str  # 租户ID
    provider_controller: ToolProviderController  # 工具提供者控制器

    def _deep_copy(self, credentials: dict[str, str]) -> dict[str, str]:
        """
        深拷贝凭据信息。
        
        参数:
        - credentials: 一个字典，包含需要深拷贝的凭据信息。
        
        返回值:
        - 一个深拷贝后的凭据信息字典。
        """
        return deepcopy(credentials)
    
    def encrypt_tool_credentials(self, credentials: dict[str, str]) -> dict[str, str]:
        """
        使用租户ID加密工具凭据。
        
        参数:
        - credentials: 一个字典，包含未加密的工具凭据信息。
        
        返回值:
        - 一个字典，包含使用租户ID加密后的凭据信息。
        """
        credentials = self._deep_copy(credentials)

        # 获取需要加密的字段
        fields = self.provider_controller.get_credentials_schema()
        for field_name, field in fields.items():
            if field.type == ToolProviderCredentials.CredentialsType.SECRET_INPUT:
                if field_name in credentials:
                    encrypted = encrypter.encrypt_token(self.tenant_id, credentials[field_name])
                    credentials[field_name] = encrypted
        
        return credentials
    
    def mask_tool_credentials(self, credentials: dict[str, Any]) -> dict[str, Any]:
        """
        遮掩工具凭据信息。
        
        参数:
        - credentials: 一个字典，包含未遮掩的工具凭据信息。
        
        返回值:
        - 一个字典，包含凭据信息的深拷贝，并且敏感信息被遮掩。
        """
        credentials = self._deep_copy(credentials)

        # 获取需要遮掩的字段
        fields = self.provider_controller.get_credentials_schema()
        for field_name, field in fields.items():
            if field.type == ToolProviderCredentials.CredentialsType.SECRET_INPUT:
                if field_name in credentials:
                    if len(credentials[field_name]) > 6:
                        credentials[field_name] = \
                            credentials[field_name][:2] + \
                            '*' * (len(credentials[field_name]) - 4) +\
                            credentials[field_name][-2:]
                    else:
                        credentials[field_name] = '*' * len(credentials[field_name])

        return credentials

    def decrypt_tool_credentials(self, credentials: dict[str, str]) -> dict[str, str]:
        """
        使用租户ID解密工具凭据。
        
        参数:
        - credentials: 一个字典，包含加密的工具凭据信息。
        
        返回值:
        - 一个字典，包含解密后的凭据信息。
        """
        cache = ToolProviderCredentialsCache(
            tenant_id=self.tenant_id, 
            identity_id=f'{self.provider_controller.app_type.value}.{self.provider_controller.identity.name}',
            cache_type=ToolProviderCredentialsCacheType.PROVIDER
        )
        cached_credentials = cache.get()  # 尝试从缓存获取凭据
        if cached_credentials:
            return cached_credentials
        credentials = self._deep_copy(credentials)
        
        # 获取需要解密的字段
        fields = self.provider_controller.get_credentials_schema()
        for field_name, field in fields.items():
            if field.type == ToolProviderCredentials.CredentialsType.SECRET_INPUT:
                if field_name in credentials:
                    try:
                        credentials[field_name] = encrypter.decrypt_token(self.tenant_id, credentials[field_name])
                    except:
                        pass  # 解密失败时忽略该凭据项

        cache.set(credentials)  # 将解密后的凭据缓存起来
        return credentials
    
    def delete_tool_credentials_cache(self):
        """
        删除工具凭据的缓存。
        """
        cache = ToolProviderCredentialsCache(
            tenant_id=self.tenant_id, 
            identity_id=f'{self.provider_controller.app_type.value}.{self.provider_controller.identity.name}',
            cache_type=ToolProviderCredentialsCacheType.PROVIDER
        )
        cache.delete()  # 删除指定租户和身份的工具凭据缓存

class ToolParameterConfigurationManager(BaseModel):
    """
    工具参数配置管理器
    负责处理工具参数的配置工作，包括复制、合并、遮蔽、加密与解密等功能。
    """
    tenant_id: str  # 租户ID
    tool_runtime: Tool  # 工具运行时实例
    provider_name: str  # 提供商名称
    provider_type: str  # 提供商类型
    identity_id: str  # 身份标识ID

    def _deep_copy(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """
        对给定的参数字典进行深度复制。

        :param parameters: 需要深度复制的参数字典。
        :return: 输入参数字典的深度副本。
        """
        return deepcopy(parameters)
    
    def _merge_parameters(self) -> list[ToolParameter]:
        """
        合并工具参数与运行时参数。

        :return: 考虑了工具默认参数及运行时特有参数的合并后工具参数列表。
        """
        # 结合工具默认参数与运行时参数
        tool_parameters = self.tool_runtime.parameters or []
        runtime_parameters = self.tool_runtime.get_runtime_parameters() or []
        
        # 使用运行时参数覆盖默认参数
        current_parameters = tool_parameters.copy()
        for runtime_parameter in runtime_parameters:
            found = False
            for index, parameter in enumerate(current_parameters):
                if parameter.name == runtime_parameter.name and parameter.form == runtime_parameter.form:
                    current_parameters[index] = runtime_parameter
                    found = True
                    break
            if not found and runtime_parameter.form == ToolParameter.ToolParameterForm.FORM:
                current_parameters.append(runtime_parameter)
        
        return current_parameters
    
    def mask_tool_parameters(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """
        对敏感工具参数进行遮蔽处理，用星号替换其值。

        :param parameters: 包含工具参数的字典。
        :return: 带有敏感参数遮蔽值的字典。
        """
        parameters = self._deep_copy(parameters)

        # 合并参数以识别需要遮蔽的项
        current_parameters = self._merge_parameters()

        # 执行敏感参数的遮蔽逻辑
        for parameter in current_parameters:
            if parameter.form == ToolParameter.ToolParameterForm.FORM and parameter.type == ToolParameter.ToolParameterType.SECRET_INPUT:
                if parameter.name in parameters:
                    # 根据参数长度执行遮蔽逻辑
                    if len(parameters[parameter.name]) > 6:
                        parameters[parameter.name] = \
                            parameters[parameter.name][:2] + \
                            '*' * (len(parameters[parameter.name]) - 4) + \
                            parameters[parameter.name][-2:]
                    else:
                        parameters[parameter.name] = '*' * len(parameters[parameter.name])

        return parameters
    
    def encrypt_tool_parameters(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """
        使用租户ID对敏感工具参数进行加密。

        :param parameters: 包含工具参数的字典，可能包含明文敏感信息。
        :return: 带有敏感参数加密值的字典。
        """
        # 合并参数以识别需要加密的项
        current_parameters = self._merge_parameters()

        parameters = self._deep_copy(parameters)

        # 执行敏感参数的加密
        for parameter in current_parameters:
            if parameter.form == ToolParameter.ToolParameterForm.FORM and parameter.type == ToolParameter.ToolParameterType.SECRET_INPUT:
                if parameter.name in parameters:
                    encrypted = encrypter.encrypt_token(self.tenant_id, parameters[parameter.name])
                    parameters[parameter.name] = encrypted
        
        return parameters
    
    def decrypt_tool_parameters(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """
        使用租户ID对已加密的敏感工具参数进行解密。

        :param parameters: 可能含有加密敏感参数的字典。
        :return: 带有敏感参数解密值的字典。
        """
        # 尝试从缓存中获取已解密的参数
        cache = ToolParameterCache(
            tenant_id=self.tenant_id, 
            provider=f'{self.provider_type}.{self.provider_name}',
            tool_name=self.tool_runtime.identity.name,
            cache_type=ToolParameterCacheType.PARAMETER,
            identity_id=self.identity_id
        )
        cache.delete()

class ModelToolConfigurationManager:
    """
    用于管理模型工具配置的类。
    """

    _configurations: dict[str, ModelToolProviderConfiguration] = {}  # 保存供应商配置的字典
    _model_configurations: dict[str, ModelToolConfiguration] = {}  # 保存模型配置的字典
    _inited = False  # 标记是否已经初始化配置

    @classmethod
    def _init_configuration(cls):
        """
        初始化配置。
        从指定目录加载所有.yaml配置文件，解析并保存到类变量中。
        """
        
        # 计算model_tools目录的绝对路径
        absolute_path = os.path.abspath(os.path.dirname(__file__))
        model_tools_path = os.path.join(absolute_path, '..', 'model_tools')

        # 获取所有.yaml配置文件
        files = [f for f in os.listdir(model_tools_path) if f.endswith('.yaml')]

        for file in files:
            provider = file.split('.')[0]  # 从文件名提取供应商名称
            with open(os.path.join(model_tools_path, file), encoding='utf-8') as f:
                # 加载配置文件内容
                configurations = ModelToolProviderConfiguration(**load(f, Loader=FullLoader))
                models = configurations.models or []  # 获取模型列表，若不存在则默认为空列表
                for model in models:
                    # 生成并保存模型配置的键值对
                    model_key = f'{provider}.{model.model}'
                    cls._model_configurations[model_key] = model

                # 保存供应商配置的键值对
                cls._configurations[provider] = configurations
        cls._inited = True  # 标记配置已初始化

    @classmethod
    def get_configuration(cls, provider: str) -> Union[ModelToolProviderConfiguration, None]:
        """
        根据供应商名称获取配置。
        
        参数:
        - provider: str，供应商名称。
        
        返回值:
        - Union[ModelToolProviderConfiguration, None]，如果找到对应的配置则返回ModelToolProviderConfiguration对象，否则返回None。
        """
        if not cls._inited:
            cls._init_configuration()
        return cls._configurations.get(provider, None)
    
    @classmethod
    def get_all_configuration(cls) -> dict[str, ModelToolProviderConfiguration]:
        """
        获取所有供应商的配置。
        
        返回值:
        - dict[str, ModelToolProviderConfiguration]，键为供应商名称，值为对应的ModelToolProviderConfiguration对象。
        """
        if not cls._inited:
            cls._init_configuration()
        return cls._configurations
    
    @classmethod
    def get_model_configuration(cls, provider: str, model: str) -> Union[ModelToolConfiguration, None]:
        """
        根据供应商和模型名称获取模型配置。
        
        参数:
        - provider: str，供应商名称。
        - model: str，模型名称。
        
        返回值:
        - Union[ModelToolConfiguration, None]，如果找到对应的模型配置则返回ModelToolConfiguration对象，否则返回None。
        """
        key = f'{provider}.{model}'  # 生成模型配置的键

        if not cls._inited:
            cls._init_configuration()

        return cls._model_configurations.get(key, None)