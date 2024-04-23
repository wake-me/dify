from typing import Optional

from core.extension.api_based_extension_requestor import APIBasedExtensionRequestor
from core.external_data_tool.base import ExternalDataTool
from core.helper import encrypter
from extensions.ext_database import db
from models.api_based_extension import APIBasedExtension, APIBasedExtensionPoint


class ApiExternalDataTool(ExternalDataTool):
    """
    ApiExternalDataTool 类：一个外部数据工具的API实现。
    
    属性：
    name: str - 外部数据工具的唯一名称。
    """
    
    name: str = "api"  # 外部数据工具的唯一名称

    @classmethod
    def validate_config(cls, tenant_id: str, config: dict) -> None:
        """
        验证传入的表单配置数据。

        :param tenant_id: 工作空间的id
        :param config: 表单配置数据
        :return: 无返回值
        """
        # 校验逻辑开始
        api_based_extension_id = config.get("api_based_extension_id")
        if not api_based_extension_id:
            raise ValueError("api_based_extension_id is required")

        # 通过数据库查询api_based_extension
        api_based_extension = db.session.query(APIBasedExtension).filter(
            APIBasedExtension.tenant_id == tenant_id,
            APIBasedExtension.id == api_based_extension_id
        ).first()

        if not api_based_extension:
            raise ValueError("api_based_extension_id is invalid")

    def query(self, inputs: dict, query: Optional[str] = None) -> str:
        """
        查询外部数据工具。

        :param inputs: 用户输入
        :param query: 聊天应用的查询内容
        :return: 工具查询结果
        """
        # 从配置中获取参数
        api_based_extension_id = self.config.get("api_based_extension_id")

        # 根据 id 查询 API 基础扩展信息
        api_based_extension = db.session.query(APIBasedExtension).filter(
            APIBasedExtension.tenant_id == self.tenant_id,
            APIBasedExtension.id == api_based_extension_id
        ).first()

        if not api_based_extension:
            # 如果查询不到对应的扩展信息，则抛出异常
            raise ValueError("[External data tool] API query failed, variable: {}, "
                            "error: api_based_extension_id is invalid"
                            .format(self.variable))

        # 解密 api_key
        api_key = encrypter.decrypt_token(
            tenant_id=self.tenant_id,
            token=api_based_extension.api_key
        )

        try:
            # 初始化 API 请求器
            requestor = APIBasedExtensionRequestor(
                api_endpoint=api_based_extension.api_endpoint,
                api_key=api_key
            )
        except Exception as e:
            # 如果初始化失败，则抛出异常
            raise ValueError("[External data tool] API query failed, variable: {}, error: {}".format(
                self.variable,
                e
            ))

        # 发起 API 请求
        response_json = requestor.request(point=APIBasedExtensionPoint.APP_EXTERNAL_DATA_TOOL_QUERY, params={
            'app_id': self.app_id,
            'tool_variable': self.variable,
            'inputs': inputs,
            'query': query
        })

        if 'result' not in response_json:
            # 如果响应结果中没有 'result' 字段，则抛出异常
            raise ValueError("[External data tool] API query failed, variable: {}, error: result not found in response"
                            .format(self.variable))

        if not isinstance(response_json['result'], str):
            # 如果 'result' 字段的类型不是字符串，则抛出异常
            raise ValueError("[External data tool] API query failed, variable: {}, error: result is not string"
                            .format(self.variable))

        return response_json['result']
