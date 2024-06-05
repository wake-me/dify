import json
from typing import Optional

from core.app.app_config.entities import (
    DatasetEntity,
    DatasetRetrieveConfigEntity,
    EasyUIBasedAppConfig,
    ExternalDataVariableEntity,
    FileExtraConfig,
    ModelConfigEntity,
    PromptTemplateEntity,
    VariableEntity,
)
from core.app.apps.agent_chat.app_config_manager import AgentChatAppConfigManager
from core.app.apps.chat.app_config_manager import ChatAppConfigManager
from core.app.apps.completion.app_config_manager import CompletionAppConfigManager
from core.helper import encrypter
from core.model_runtime.entities.llm_entities import LLMMode
from core.model_runtime.utils.encoders import jsonable_encoder
from core.prompt.simple_prompt_transform import SimplePromptTransform
from core.workflow.entities.node_entities import NodeType
from events.app_event import app_was_created
from extensions.ext_database import db
from models.account import Account
from models.api_based_extension import APIBasedExtension, APIBasedExtensionPoint
from models.model import App, AppMode, AppModelConfig
from models.workflow import Workflow, WorkflowType


class WorkflowConverter:
    """
    应用转换为工作流模式
    """
    def convert_to_workflow(self, app_model: App,
                            account: Account,
                            name: str,
                            icon: str,
                            icon_background: str) -> App:
        """
        将应用转换为工作流模式。

        - 聊天机器人应用的基本模式
        - 聊天机器人应用的专家模式
        - 完成应用

        :param app_model: App实例
        :param account: 账户
        :param name: 新应用名称
        :param icon: 新应用图标
        :param icon_background: 新应用图标背景
        :return: 新的App实例
        """
        # 将应用模型配置转换为工作流
        workflow = self.convert_app_model_config_to_workflow(
            app_model=app_model,
            app_model_config=app_model.app_model_config,
            account_id=account.id
        )

        # 创建新应用
        new_app = App()
        new_app.tenant_id = app_model.tenant_id
        new_app.name = name if name else app_model.name + '(workflow)'
        new_app.mode = AppMode.ADVANCED_CHAT.value \
            if app_model.mode == AppMode.CHAT.value else AppMode.WORKFLOW.value
        new_app.icon = icon if icon else app_model.icon
        new_app.icon_background = icon_background if icon_background else app_model.icon_background
        new_app.enable_site = app_model.enable_site
        new_app.enable_api = app_model.enable_api
        new_app.api_rpm = app_model.api_rpm
        new_app.api_rph = app_model.api_rph
        new_app.is_demo = False
        new_app.is_public = app_model.is_public
        db.session.add(new_app)
        db.session.flush()
        db.session.commit()

        workflow.app_id = new_app.id
        db.session.commit()

        # 发送应用创建信号
        app_was_created.send(new_app, account=account)

        return new_app

    def convert_app_model_config_to_workflow(self, app_model: App,
                                            app_model_config: AppModelConfig,
                                            account_id: str) -> Workflow:
        """
        将应用模型配置转换为工作流模式
        :param app_model: App实例
        :param app_model_config: AppModelConfig实例
        :param account_id: 账户ID
        :return: 工作流实例
        """
        # 获取新的应用模式
        new_app_mode = self._get_new_app_mode(app_model)

        # 转换应用模型配置
        app_config = self._convert_to_app_config(
            app_model=app_model,
            app_model_config=app_model_config
        )

        # 初始化工作流图
        graph = {
            "nodes": [],
            "edges": []
        }

        # 转换列表：
        # - variables -> start
        # - model_config -> llm
        # - prompt_template -> llm
        # - file_upload -> llm
        # - external_data_variables -> http-request
        # - dataset -> knowledge-retrieval
        # - show_retrieve_source -> knowledge-retrieval

        # 转换为起始节点
        start_node = self._convert_to_start_node(
            variables=app_config.variables
        )
        graph['nodes'].append(start_node)

        # 转换为HTTP请求节点
        external_data_variable_node_mapping = {}
        if app_config.external_data_variables:
            http_request_nodes, external_data_variable_node_mapping = self._convert_to_http_request_node(
                app_model=app_model,
                variables=app_config.variables,
                external_data_variables=app_config.external_data_variables
            )

            for http_request_node in http_request_nodes:
                graph = self._append_node(graph, http_request_node)

        # 转换为知识检索节点
        if app_config.dataset:
            knowledge_retrieval_node = self._convert_to_knowledge_retrieval_node(
                new_app_mode=new_app_mode,
                dataset_config=app_config.dataset,
                model_config=app_config.model
            )

            if knowledge_retrieval_node:
                graph = self._append_node(graph, knowledge_retrieval_node)

        # 转换为LLM节点
        llm_node = self._convert_to_llm_node(
            original_app_mode=AppMode.value_of(app_model.mode),
            new_app_mode=new_app_mode,
            graph=graph,
            model_config=app_config.model,
            prompt_template=app_config.prompt_template,
            file_upload=app_config.additional_features.file_upload,
            external_data_variable_node_mapping=external_data_variable_node_mapping
        )
        graph = self._append_node(graph, llm_node)

        if new_app_mode == AppMode.WORKFLOW:
            # 根据应用模式转换为结束节点
            end_node = self._convert_to_end_node()
            graph = self._append_node(graph, end_node)
        else:
            answer_node = self._convert_to_answer_node()
            graph = self._append_node(graph, answer_node)

        app_model_config_dict = app_config.app_model_config_dict

        # 设置功能
        if new_app_mode == AppMode.ADVANCED_CHAT:
            features = {
                "opening_statement": app_model_config_dict.get("opening_statement"),
                "suggested_questions": app_model_config_dict.get("suggested_questions"),
                "suggested_questions_after_answer": app_model_config_dict.get("suggested_questions_after_answer"),
                "speech_to_text": app_model_config_dict.get("speech_to_text"),
                "text_to_speech": app_model_config_dict.get("text_to_speech"),
                "file_upload": app_model_config_dict.get("file_upload"),
                "sensitive_word_avoidance": app_model_config_dict.get("sensitive_word_avoidance"),
                "retriever_resource": app_model_config_dict.get("retriever_resource"),
            }
        else:
            features = {
                "text_to_speech": app_model_config_dict.get("text_to_speech"),
                "file_upload": app_model_config_dict.get("file_upload"),
                "sensitive_word_avoidance": app_model_config_dict.get("sensitive_word_avoidance"),
            }

        # 创建工作流记录
        workflow = Workflow(
            tenant_id=app_model.tenant_id,
            app_id=app_model.id,
            type=WorkflowType.from_app_mode(new_app_mode).value,
            version='draft',
            graph=json.dumps(graph),
            features=json.dumps(features),
            created_by=account_id
        )

        db.session.add(workflow)
        db.session.commit()

        return workflow

    def _convert_to_app_config(self, app_model: App,
                                app_model_config: AppModelConfig) -> EasyUIBasedAppConfig:
            """
            将应用模型配置转换为对应的易于使用的应用配置。
            
            :param app_model: 应用模型，包含应用的配置和状态信息。
            :param app_model_config: 应用模型配置，详细定义了应用的各种配置选项。
            :return: 返回一个基于EasyUI的应用配置对象，根据应用的模式不同，返回的具体类型也不同。
            """
            # 根据应用模式获取对应的枚举值
            app_mode = AppMode.value_of(app_model.mode)
            if app_mode == AppMode.AGENT_CHAT or app_model.is_agent:
                # 如果是代理聊天模式或设置为代理模式，则使用代理聊天应用配置
                app_model.mode = AppMode.AGENT_CHAT.value
                app_config = AgentChatAppConfigManager.get_app_config(
                    app_model=app_model,
                    app_model_config=app_model_config
                )
            elif app_mode == AppMode.CHAT:
                # 如果是聊天模式，则使用聊天应用配置
                app_config = ChatAppConfigManager.get_app_config(
                    app_model=app_model,
                    app_model_config=app_model_config
                )
            elif app_mode == AppMode.COMPLETION:
                # 如果是完成模式，则使用完成应用配置
                app_config = CompletionAppConfigManager.get_app_config(
                    app_model=app_model,
                    app_model_config=app_model_config
                )
            else:
                # 如果没有有效的应用模式，则抛出异常
                raise ValueError("Invalid app mode")

            return app_config

    def _convert_to_start_node(self, variables: list[VariableEntity]) -> dict:
        """
        转换为起始节点
        :param variables: 变量列表，每个变量都是一个VariableEntity实例
        :return: 返回一个表示起始节点的字典，包含节点的id、位置信息和数据内容
        """
        # 构建并返回起始节点的字典表示
        return {
            "id": "start",  # 节点ID，这里固定为"start"
            "position": None,  # 节点位置，对于起始节点，位置信息可为空
            "data": {  # 节点的数据部分
                "title": "START",  # 节点标题，固定为"START"
                "type": NodeType.START.value,  # 节点类型，取自NodeType中的START值
                "variables": [jsonable_encoder(v) for v in variables]  # 变量列表，将每个变量通过jsonable_encoder编码后添加到节点数据中
            }
        }

    def _convert_to_http_request_node(self, app_model: App,
                                    variables: list[VariableEntity],
                                    external_data_variables: list[ExternalDataVariableEntity]) \
            -> tuple[list[dict], dict[str, str]]:
        """
        将基于API的扩展转换为HTTP请求节点
        :param app_model: App实例
        :param variables: 变量列表
        :param external_data_variables: 外部数据变量列表
        :return: 返回一个元组，包含HTTP请求节点列表和外部数据变量到代码节点的映射字典
        """
        index = 1
        nodes = []  # 存储生成的HTTP请求节点
        external_data_variable_node_mapping = {}  # 存储外部数据变量到代码节点的映射
        tenant_id = app_model.tenant_id  # 获取租户ID

        # 遍历外部数据变量，筛选出类型为API的变量并处理
        for external_data_variable in external_data_variables:
            tool_type = external_data_variable.type
            if tool_type != "api":
                continue

            # 解析外部数据工具的配置信息
            tool_variable = external_data_variable.variable
            tool_config = external_data_variable.config
            api_based_extension_id = tool_config.get("api_based_extension_id")
            api_based_extension = self._get_api_based_extension(
                tenant_id=tenant_id,
                api_based_extension_id=api_based_extension_id
            )

            if not api_based_extension:
                raise ValueError("[External data tool] API query failed, variable: {}, "
                                "error: api_based_extension_id is invalid"
                                .format(tool_variable))

            # 解密API密钥
            api_key = encrypter.decrypt_token(
                tenant_id=tenant_id,
                token=api_based_extension.api_key
            )

            # 准备请求的输入参数
            inputs = {}
            for v in variables:
                inputs[v.variable] = '{{#start.' + v.variable + '#}}'

            # 构建HTTP请求体
            request_body = {
                'point': APIBasedExtensionPoint.APP_EXTERNAL_DATA_TOOL_QUERY.value,
                'params': {
                    'app_id': app_model.id,
                    'tool_variable': tool_variable,
                    'inputs': inputs,
                    'query': '{{#sys.query#}}' if app_model.mode == AppMode.CHAT.value else ''
                }
            }

            request_body_json = json.dumps(request_body)
            request_body_json = request_body_json.replace(r'\{\{', '{{').replace(r'\}\}', '}}')

            # 创建HTTP请求节点
            http_request_node = {
                "id": f"http_request_{index}",
                "position": None,
                "data": {
                    "title": f"HTTP REQUEST {api_based_extension.name}",
                    "type": NodeType.HTTP_REQUEST.value,
                    "method": "post",
                    "url": api_based_extension.api_endpoint,
                    "authorization": {
                        "type": "api-key",
                        "config": {
                            "type": "bearer",
                            "api_key": api_key
                        }
                    },
                    "headers": "",
                    "params": "",
                    "body": {
                        "type": "json",
                        "data": request_body_json
                    }
                }
            }

            nodes.append(http_request_node)

            # 创建代码节点，用于解析HTTP响应体
            code_node = {
                "id": f"code_{index}",
                "position": None,
                "data": {
                    "title": f"Parse {api_based_extension.name} Response",
                    "type": NodeType.CODE.value,
                    "variables": [{
                        "variable": "response_json",
                        "value_selector": [http_request_node['id'], "body"]
                    }],
                    "code_language": "python3",
                    "code": "import json\n\ndef main(response_json: str) -> str:\n    response_body = json.loads("
                            "response_json)\n    return {\n        \"result\": response_body[\"result\"]\n    }",
                    "outputs": {
                        "result": {
                            "type": "string"
                        }
                    }
                }
            }

            nodes.append(code_node)

            # 记录外部数据变量到代码节点的映射
            external_data_variable_node_mapping[external_data_variable.variable] = code_node['id']
            index += 1

        return nodes, external_data_variable_node_mapping

    def _convert_to_knowledge_retrieval_node(self, new_app_mode: AppMode,
                                             dataset_config: DatasetEntity,
                                             model_config: ModelConfigEntity) \
            -> Optional[dict]:
        """
        Convert datasets to Knowledge Retrieval Node
        :param new_app_mode: new app mode
        :param dataset_config: dataset
        :param model_config: model config
        :return:
        """
        retrieve_config = dataset_config.retrieve_config
        if new_app_mode == AppMode.ADVANCED_CHAT:
            query_variable_selector = ["sys", "query"]
        elif retrieve_config.query_variable:
            # fetch query variable
            query_variable_selector = ["start", retrieve_config.query_variable]
        else:
            return None

        return {
            "id": "knowledge_retrieval",
            "position": None,
            "data": {
                "title": "KNOWLEDGE RETRIEVAL",
                "type": NodeType.KNOWLEDGE_RETRIEVAL.value,
                "query_variable_selector": query_variable_selector,
                "dataset_ids": dataset_config.dataset_ids,
                "retrieval_mode": retrieve_config.retrieve_strategy.value,
                "single_retrieval_config": {
                    "model": {
                        "provider": model_config.provider,
                        "name": model_config.model,
                        "mode": model_config.mode,
                        "completion_params": {
                            **model_config.parameters,
                            "stop": model_config.stop,
                        }
                    }
                }
                if retrieve_config.retrieve_strategy == DatasetRetrieveConfigEntity.RetrieveStrategy.SINGLE
                else None,
                "multiple_retrieval_config": {
                    "top_k": retrieve_config.top_k,
                    "score_threshold": retrieve_config.score_threshold,
                    "reranking_model": retrieve_config.reranking_model
                }
                if retrieve_config.retrieve_strategy == DatasetRetrieveConfigEntity.RetrieveStrategy.MULTIPLE
                else None,
            }
        }

    def _convert_to_llm_node(self, original_app_mode: AppMode,
                             new_app_mode: AppMode,
                             graph: dict,
                             model_config: ModelConfigEntity,
                             prompt_template: PromptTemplateEntity,
                             file_upload: Optional[FileExtraConfig] = None,
                             external_data_variable_node_mapping: dict[str, str] = None) -> dict:
        """
        转换为LLM（Large Language Model）节点。
        :param original_app_mode: 原始应用模式。
        :param new_app_mode: 新的应用模式。
        :param graph: 图结构数据。
        :param model_config: 模型配置实体。
        :param prompt_template: 提示模板实体。
        :param file_upload: 文件上传配置（可选）。
        :param external_data_variable_node_mapping: 外部数据变量节点映射。
        :return: 转换后的LLM节点信息字典。
        """
        # 获取起始节点和知识检索节点
        start_node = next(filter(lambda n: n['data']['type'] == NodeType.START.value, graph['nodes']))
        knowledge_retrieval_node = next(filter(
            lambda n: n['data']['type'] == NodeType.KNOWLEDGE_RETRIEVAL.value,
            graph['nodes']
        ), None)

        role_prefix = None

        # 根据模型模式（聊天模式或完成模式）处理提示模板
        if model_config.mode == LLMMode.CHAT.value:
            # 处理简单提示模板
            if prompt_template.prompt_type == PromptTemplateEntity.PromptType.SIMPLE:
                prompt_transform = SimplePromptTransform()
                prompt_template_config = prompt_transform.get_prompt_template(
                    app_mode=original_app_mode,
                    provider=model_config.provider,
                    model=model_config.model,
                    pre_prompt=prompt_template.simple_prompt_template,
                    has_context=knowledge_retrieval_node is not None,
                    query_in_prompt=False
                )

                template = prompt_template_config['prompt_template'].template
                if not template:
                    prompts = []
                else:
                    template = self._replace_template_variables(
                        template,
                        start_node['data']['variables'],
                        external_data_variable_node_mapping
                    )

                    prompts = [
                        {
                            "role": 'user',
                            "text": template
                        }
                    ]
            # 处理高级聊天提示模板
            else:
                prompts = []
                for m in prompt_template.advanced_chat_prompt_template.messages:
                    text = m.text
                    text = self._replace_template_variables(
                        text,
                        start_node['data']['variables'],
                        external_data_variable_node_mapping
                    )

                    prompts.append({
                        "role": m.role.value,
                        "text": text
                    })
        else:
            # 处理简单完成提示模板
            if prompt_template.prompt_type == PromptTemplateEntity.PromptType.SIMPLE:
                prompt_transform = SimplePromptTransform()
                prompt_template_config = prompt_transform.get_prompt_template(
                    app_mode=original_app_mode,
                    provider=model_config.provider,
                    model=model_config.model,
                    pre_prompt=prompt_template.simple_prompt_template,
                    has_context=knowledge_retrieval_node is not None,
                    query_in_prompt=False
                )

                template = prompt_template_config['prompt_template'].template
                template = self._replace_template_variables(
                    template,
                    start_node['data']['variables'],
                    external_data_variable_node_mapping
                )

                prompts = {
                    "text": template
                }

                prompt_rules = prompt_template_config['prompt_rules']
                role_prefix = {
                    "user": prompt_rules['human_prefix'] if 'human_prefix' in prompt_rules else 'Human',
                    "assistant": prompt_rules['assistant_prefix'] if 'assistant_prefix' in prompt_rules else 'Assistant'
                }
            # 处理高级完成提示模板
            else:
                prompts = {
                    "text": ""
                }

                if prompt_template.advanced_completion_prompt_template.role_prefix:
                    role_prefix = {
                        "user": prompt_template.advanced_completion_prompt_template.role_prefix.user,
                        "assistant": prompt_template.advanced_completion_prompt_template.role_prefix.assistant
                    }

        # 配置高级聊天模式的内存信息
        memory = None
        if new_app_mode == AppMode.ADVANCED_CHAT:
            memory = {
                "role_prefix": role_prefix,
                "window": {
                    "enabled": False
                }
            }

        # 组装并返回LLM节点信息
        completion_params = model_config.parameters
        completion_params.update({"stop": model_config.stop})
        return {
            "id": "llm",
            "position": None,
            "data": {
                "title": "LLM",
                "type": NodeType.LLM.value,
                "model": {
                    "provider": model_config.provider,
                    "name": model_config.model,
                    "mode": model_config.mode,
                    "completion_params": completion_params
                },
                "prompt_template": prompts,
                "memory": memory,
                "context": {
                    "enabled": knowledge_retrieval_node is not None,
                    "variable_selector": ["knowledge_retrieval", "result"]
                    if knowledge_retrieval_node is not None else None
                },
                "vision": {
                    "enabled": file_upload is not None,
                    "variable_selector": ["sys", "files"] if file_upload is not None else None,
                    "configs": {
                        "detail": file_upload.image_config['detail']
                    } if file_upload is not None else None
                }
            }
        }

    def _replace_template_variables(self, template: str,
                                    variables: list[dict],
                                    external_data_variable_node_mapping: dict[str, str] = None) -> str:
        """
        替换模板变量
        :param template: 待处理的模板字符串，其中包含需要被替换的变量占位符（形式为{{变量名}}）
        :param variables: 包含变量信息的列表，每个变量是一个字典，至少包含'variable'键，其值为变量名
        :param external_data_variable_node_mapping: 一个可选的字典，用于映射外部数据变量到代码节点ID，键为变量名，值为代码节点ID
        :return: 替换变量后的模板字符串
        """
        # 替换内部变量
        for v in variables:
            template = template.replace('{{' + v['variable'] + '}}', '{{#start.' + v['variable'] + '#}}')

        # 如果提供了外部数据变量节点映射，则替换这些外部变量
        if external_data_variable_node_mapping:
            for variable, code_node_id in external_data_variable_node_mapping.items():
                template = template.replace('{{' + variable + '}}',
                                            '{{#' + code_node_id + '.result#}}')

        return template

    def _convert_to_end_node(self) -> dict:
        """
        转换为结束节点
        :return: 返回一个表示结束节点的字典
        """
        # 用于原始完成应用程序的结束节点
        return {
            "id": "end",  # 节点ID，这里固定为"end"
            "position": None,  # 节点位置，对于结束节点，位置不重要，故设为None
            "data": {  # 节点数据信息
                "title": "END",  # 节点标题，显示为"END"
                "type": NodeType.END.value,  # 节点类型，设置为结束节点类型
                "outputs": [  # 节点输出信息
                    {
                        "variable": "result",  # 输出变量名，这里设为"result"
                        "value_selector": ["llm", "text"]  # 输出值的选择器，指定获取"llm"下的"text"值
                    }
                ]
            }
        }

    def _convert_to_answer_node(self) -> dict:
        """
        转换为答案节点
        :return: 返回一个字典，该字典表示一个特定的答案节点
        """
        # 用于原始聊天应用
        return {
            "id": "answer",  # 节点ID
            "position": None,  # 节点位置，此处为None
            "data": {  # 节点数据
                "title": "ANSWER",  # 节点标题
                "type": NodeType.ANSWER.value,  # 节点类型
                "answer": "{{#llm.text#}}"  # 答案内容，使用特定模板语法
            }
        }

    def _create_edge(self, source: str, target: str) -> dict:
        """
        创建边
        :param source: 源节点id
        :param target: 目标节点id
        :return: 返回边的字典表示，包含id、source和target字段
        """
        # 根据源节点和目标节点创建边的id，然后构建边的字典表示
        return {
            "id": f"{source}-{target}",  # 边的唯一标识
            "source": source,  # 源节点
            "target": target  # 目标节点
        }

    def _append_node(self, graph: dict, node: dict) -> dict:
        """
        将节点追加到图中

        :param graph: 图，包含节点和边的信息
        :param node: 需要追加的节点
        :return: 更新后的图
        """
        # 添加新节点前，记录图中最后一个节点
        previous_node = graph['nodes'][-1]
        # 将新节点添加到图的节点列表中
        graph['nodes'].append(node)
        # 创建并添加从上一个节点到新节点的边
        graph['edges'].append(self._create_edge(previous_node['id'], node['id']))
        return graph

    def _get_new_app_mode(self, app_model: App) -> AppMode:
        """
        获取新的应用模式
        :param app_model: App实例
        :return: AppMode枚举类型，代表新的应用模式
        """
        # 根据当前应用模式决定返回的新应用模式
        if app_model.mode == AppMode.COMPLETION.value:
            return AppMode.WORKFLOW
        else:
            return AppMode.ADVANCED_CHAT

    def _get_api_based_extension(self, tenant_id: str, api_based_extension_id: str) -> APIBasedExtension:
        """
        获取基于API的扩展
        :param tenant_id: 租户id
        :param api_based_extension_id: 基于API的扩展id
        :return: 返回基于API的扩展对象
        """
        # 从数据库会话中查询指定租户ID和扩展ID的基于API的扩展记录
        return db.session.query(APIBasedExtension).filter(
            APIBasedExtension.tenant_id == tenant_id,
            APIBasedExtension.id == api_based_extension_id
        ).first()
