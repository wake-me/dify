from copy import deepcopy
from typing import Any

from pydantic import BaseModel

from core.helper import encrypter
from core.helper.tool_parameter_cache import ToolParameterCache, ToolParameterCacheType
from core.helper.tool_provider_cache import ToolProviderCredentialsCache, ToolProviderCredentialsCacheType
from core.tools.entities.tool_entities import (
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
                            '*' * (len(credentials[field_name]) - 4) + \
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
            identity_id=f'{self.provider_controller.provider_type.value}.{self.provider_controller.identity.name}',
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
            identity_id=f'{self.provider_controller.provider_type.value}.{self.provider_controller.identity.name}',
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
        decrypt tool parameters with tenant id

        return a deep copy of parameters with decrypted values
        """
        cache = ToolParameterCache(
            tenant_id=self.tenant_id,
            provider=f'{self.provider_type}.{self.provider_name}',
            tool_name=self.tool_runtime.identity.name,
            cache_type=ToolParameterCacheType.PARAMETER,
            identity_id=self.identity_id
        )
        cached_parameters = cache.get()
        if cached_parameters:
            return cached_parameters

        # override parameters
        current_parameters = self._merge_parameters()
        has_secret_input = False

        for parameter in current_parameters:
            if parameter.form == ToolParameter.ToolParameterForm.FORM and parameter.type == ToolParameter.ToolParameterType.SECRET_INPUT:
                if parameter.name in parameters:
                    try:
                        has_secret_input = True
                        parameters[parameter.name] = encrypter.decrypt_token(self.tenant_id, parameters[parameter.name])
                    except:
                        pass

        if has_secret_input:
            cache.set(parameters)

        return parameters

    def delete_tool_parameters_cache(self):
        cache = ToolParameterCache(
            tenant_id=self.tenant_id,
            provider=f'{self.provider_type}.{self.provider_name}',
            tool_name=self.tool_runtime.identity.name,
            cache_type=ToolParameterCacheType.PARAMETER,
            identity_id=self.identity_id
        )
        cache.delete()
