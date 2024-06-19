from pydantic import BaseModel

from core.extension.api_based_extension_requestor import APIBasedExtensionPoint, APIBasedExtensionRequestor
from core.helper.encrypter import decrypt_token
from core.moderation.base import Moderation, ModerationAction, ModerationInputsResult, ModerationOutputsResult
from extensions.ext_database import db
from models.api_based_extension import APIBasedExtension


class ModerationInputParams(BaseModel):
    # 中介审核输入参数模型
    app_id: str = ""  # 应用ID
    inputs: dict = {}  # 输入数据字典
    query: str = ""  # 查询字符串

class ModerationOutputParams(BaseModel):
    # 中介审核输出参数模型
    app_id: str = ""  # 应用ID
    text: str  # 审核后的文本输出

class ApiModeration(Moderation):
    # API中介审核类
    name: str = "api"  # 类型名称

    @classmethod
    def validate_config(cls, tenant_id: str, config: dict) -> None:
        """
        验证传入的表单配置数据。

        :param tenant_id: 工作空间的ID
        :param config: 表单配置数据
        :return: 无返回值
        """
        cls._validate_inputs_and_outputs_config(config, False)

        api_based_extension_id = config.get("api_based_extension_id")
        if not api_based_extension_id:
            raise ValueError("api_based_extension_id is required")

        extension = cls._get_api_based_extension(tenant_id, api_based_extension_id)
        if not extension:
            raise ValueError("API-based Extension not found. Please check it again.")

    def moderation_for_inputs(self, inputs: dict, query: str = "") -> ModerationInputsResult:
        """
        对输入数据进行审核。

        :param inputs: 待审核的输入数据字典
        :param query: 查询字符串
        :return: 返回审核输入结果
        """
        flagged = False
        preset_response = ""

        if self.config['inputs_config']['enabled']:
            params = ModerationInputParams(
                app_id=self.app_id,
                inputs=inputs,
                query=query
            )

            result = self._get_config_by_requestor(APIBasedExtensionPoint.APP_MODERATION_INPUT, params.model_dump())
            return ModerationInputsResult(**result)

        return ModerationInputsResult(flagged=flagged, action=ModerationAction.DIRECT_OUTPUT, preset_response=preset_response)

    def moderation_for_outputs(self, text: str) -> ModerationOutputsResult:
        """
        对输出数据进行审核。

        :param text: 待审核的文本
        :return: 返回审核输出结果
        """
        flagged = False
        preset_response = ""

        if self.config['outputs_config']['enabled']:
            params = ModerationOutputParams(
                app_id=self.app_id,
                text=text
            )

            result = self._get_config_by_requestor(APIBasedExtensionPoint.APP_MODERATION_OUTPUT, params.model_dump())
            return ModerationOutputsResult(**result)

        return ModerationOutputsResult(flagged=flagged, action=ModerationAction.DIRECT_OUTPUT, preset_response=preset_response)

    def _get_config_by_requestor(self, extension_point: APIBasedExtensionPoint, params: dict) -> dict:
        """
        根据请求者获取配置信息。

        :param extension_point: 扩展点
        :param params: 请求参数
        :return: 返回请求结果
        """
        extension = self._get_api_based_extension(self.tenant_id, self.config.get("api_based_extension_id"))
        requestor = APIBasedExtensionRequestor(extension.api_endpoint, decrypt_token(self.tenant_id, extension.api_key))

        result = requestor.request(extension_point, params)
        return result

    @staticmethod
    def _get_api_based_extension(tenant_id: str, api_based_extension_id: str) -> APIBasedExtension:
        """
        根据租户ID和API基础扩展ID获取扩展信息。

        :param tenant_id: 租户ID
        :param api_based_extension_id: API基础扩展ID
        :return: 返回API基础扩展信息
        """
        extension = db.session.query(APIBasedExtension).filter(
            APIBasedExtension.tenant_id == tenant_id,
            APIBasedExtension.id == api_based_extension_id
        ).first()

        return extension