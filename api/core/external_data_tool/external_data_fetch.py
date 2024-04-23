import concurrent
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from flask import Flask, current_app

from core.app.app_config.entities import ExternalDataVariableEntity
from core.external_data_tool.factory import ExternalDataToolFactory

logger = logging.getLogger(__name__)


class ExternalDataFetch:
    def fetch(self, tenant_id: str,
            app_id: str,
            external_data_tools: list[ExternalDataVariableEntity],
            inputs: dict,
            query: str) -> dict:
        """
        如果存在的话，从外部数据工具填充变量输入。

        :param tenant_id: 工作空间id
        :param app_id: 应用id
        :param external_data_tools: 外部数据工具配置列表
        :param inputs: 输入参数
        :param query: 查询语句
        :return: 填充后的输入参数
        """
        results = {}  # 用于存储从外部数据工具获取的结果

        # 使用线程池执行器来并发地从外部数据工具获取数据
        with ThreadPoolExecutor() as executor:
            futures = {}  # 用于存储future对象及其对应的外部数据工具

            # 为每个外部数据工具提交一个任务
            for tool in external_data_tools:
                future = executor.submit(
                    self._query_external_data_tool,
                    current_app._get_current_object(),
                    tenant_id,
                    app_id,
                    tool,
                    inputs,
                    query
                )

                futures[future] = tool

            # 等待所有任务完成，并收集结果
            for future in concurrent.futures.as_completed(futures):
                tool_variable, result = future.result()
                results[tool_variable] = result

        # 将从外部数据工具获取的结果更新到输入参数中
        inputs.update(results)
        return inputs

    def _query_external_data_tool(self, flask_app: Flask,
                                  tenant_id: str,
                                  app_id: str,
                                  external_data_tool: ExternalDataVariableEntity,
                                  inputs: dict,
                                  query: str) -> tuple[Optional[str], Optional[str]]:
        """
        查询外部数据工具。
        :param flask_app: Flask应用实例
        :param tenant_id: 租户ID
        :param app_id: 应用ID
        :param external_data_tool: 外部数据工具实体
        :param inputs: 输入参数
        :param query: 查询语句
        :return: 返回一个元组，包含工具变量和查询结果，两者都可能是None
        """
        with flask_app.app_context():
            # 提取外部数据工具的变量、类型和配置信息
            tool_variable = external_data_tool.variable
            tool_type = external_data_tool.type
            tool_config = external_data_tool.config

            # 创建外部数据工具的实例
            external_data_tool_factory = ExternalDataToolFactory(
                name=tool_type,
                tenant_id=tenant_id,
                app_id=app_id,
                variable=tool_variable,
                config=tool_config
            )

            # 执行查询操作
            result = external_data_tool_factory.query(
                inputs=inputs,
                query=query
            )

            return tool_variable, result
