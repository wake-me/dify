import json
import re
import uuid
from enum import Enum
from typing import Optional

from flask import request
from flask_login import UserMixin
from sqlalchemy import Float, func, text
from sqlalchemy.orm import Mapped, mapped_column

from configs import dify_config
from core.file.tool_file_parser import ToolFileParser
from core.file.upload_file_parser import UploadFileParser
from extensions.ext_database import db
from libs.helper import generate_string

from .account import Account, Tenant
from .types import StringUUID


class DifySetup(db.Model):
    """
    DifySetup 类代表了 Dify 设置的信息模型。
    
    属性:
    - version: 设置的版本号，为字符串类型，不可为空。
    - setup_at: 设置完成的时间，为日期时间类型，不可为空，默认为当前时间。
    
    该模型映射到数据库表 'dify_setups'，其中主键为 'version'。
    """
    __tablename__ = 'dify_setups'  # 指定数据库表名为 'dify_setups'
    __table_args__ = (
        db.PrimaryKeyConstraint('version', name='dify_setup_pkey'),  # 设置 'version' 字段为 primary key
    )

    version = db.Column(db.String(255), nullable=False)
    setup_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))


class AppMode(Enum):
    # 应用模式枚举类
    COMPLETION = 'completion'  # 生成模式
    WORKFLOW = 'workflow'  # 工作流模式
    CHAT = 'chat'  # 聊天模式
    ADVANCED_CHAT = 'advanced-chat'  # 高级聊天模式
    AGENT_CHAT = 'agent-chat'  # 代理聊天模式
    CHANNEL = 'channel'  # 频道模式

    @classmethod
    def value_of(cls, value: str) -> 'AppMode':
        """
        根据字符串值获取对应的应用模式枚举实例。

        :param value: 模式对应的字符串值。
        :return: 对应的AppMode枚举实例。
        """
        for mode in cls:
            if mode.value == value:
                return mode
        # 如果传入的值没有对应的枚举实例，则抛出异常
        raise ValueError(f'invalid mode value {value}')


class IconType(Enum):
    IMAGE = "image"
    EMOJI = "emoji"

class App(db.Model):
    """
    App 类表示一个应用程序模型，它在数据库中映射为一个表。

    属性:
    - id: 应用的唯一标识符，使用UUID生成。
    - tenant_id: 租户的唯一标识符，不可为空。
    - name: 应用的名称，不可为空。
    - mode: 应用的模式，不可为空。
    - icon: 应用的图标地址。
    - icon_background: 图标的背景颜色。
    - app_model_config_id: 应用模型配置的唯一标识符，可为空。
    - status: 应用的状态，默认为'normal'。
    - enable_site: 是否启用Web界面。
    - enable_api: 是否启用API接口。
    - api_rpm: API每分钟请求限制。
    - api_rph: API每小时请求限制。
    - is_demo: 是否为演示应用。
    - is_public: 是否为公共应用。
    - is_universal: 是否为通用应用。
    - created_at: 创建时间。
    - updated_at: 更新时间。

    方法:
    - site: 获取应用对应的Site对象。
    - app_model_config: 获取应用的模型配置对象。
    - api_base_url: 获取API的基础URL。
    - tenant: 获取应用所属的租户对象。
    - is_agent: 判断应用是否为代理模式。
    - deleted_tools: 获取已删除的工具信息。
    """
    __tablename__ = 'apps'
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='app_pkey'),
        db.Index('app_tenant_id_idx', 'tenant_id')
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    tenant_id = db.Column(StringUUID, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False, server_default=db.text("''::character varying"))
    mode = db.Column(db.String(255), nullable=False)
    icon_type = db.Column(db.String(255), nullable=True)
    icon = db.Column(db.String(255))
    icon_background = db.Column(db.String(255))
    app_model_config_id = db.Column(StringUUID, nullable=True)
    workflow_id = db.Column(StringUUID, nullable=True)
    status = db.Column(db.String(255), nullable=False, server_default=db.text("'normal'::character varying"))
    enable_site = db.Column(db.Boolean, nullable=False)
    enable_api = db.Column(db.Boolean, nullable=False)
    api_rpm = db.Column(db.Integer, nullable=False, server_default=db.text('0'))
    api_rph = db.Column(db.Integer, nullable=False, server_default=db.text('0'))
    is_demo = db.Column(db.Boolean, nullable=False, server_default=db.text('false'))
    is_public = db.Column(db.Boolean, nullable=False, server_default=db.text('false'))
    is_universal = db.Column(db.Boolean, nullable=False, server_default=db.text('false'))
    tracing = db.Column(db.Text, nullable=True)
    max_active_requests = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))

    @property
    def desc_or_prompt(self):
        if self.description:
            return self.description
        else:
            app_model_config = self.app_model_config
            if app_model_config:
                return app_model_config.pre_prompt
            else:
                return ''

    @property
    def site(self):
        """
        获取关联的Site对象。

        返回:
        - Site对象或None（如果找不到对应的Site对象）。
        """
        site = db.session.query(Site).filter(Site.app_id == self.id).first()
        return site

    @property
    def app_model_config(self) -> Optional['AppModelConfig']:
        """
        获取应用模型配置。
        
        通过app_model_config_id来查询数据库，尝试获取对应的AppModelConfig对象。
        如果app_model_config_id存在，则返回查询到的第一个对象；否则，返回None。
        
        返回值:
            Optional['AppModelConfig']: AppModelConfig对象，如果未查询到则为None。
        """
        if self.app_model_config_id:
            # 根据id查询AppModelConfig对象
            return db.session.query(AppModelConfig).filter(AppModelConfig.id == self.app_model_config_id).first()

        return None

    @property
    def workflow(self) -> Optional['Workflow']:
        if self.workflow_id:
            # 从workflow模块导入Workflow类
            from .workflow import Workflow
            # 根据id查询Workflow对象
            return db.session.query(Workflow).filter(Workflow.id == self.workflow_id).first()

        return None

    @property
    def api_base_url(self):
        return (dify_config.SERVICE_API_URL if dify_config.SERVICE_API_URL
                else request.host_url.rstrip('/')) + '/v1'

    @property
    def tenant(self):
        """
        获取关联的租户对象。

        返回:
        - Tenant对象或None（如果找不到对应的租户）。
        """
        tenant = db.session.query(Tenant).filter(Tenant.id == self.tenant_id).first()
        return tenant

    @property
    def is_agent(self) -> bool:
        """
        判断应用是否运行在代理模式。

        返回:
        - 布尔值，表示应用是否为代理模式。
        """
        app_model_config = self.app_model_config
        if not app_model_config:
            return False
        if not app_model_config.agent_mode:
            return False
        if self.app_model_config.agent_mode_dict.get('enabled', False) \
                and self.app_model_config.agent_mode_dict.get('strategy', '') in ['function_call', 'react']:
            self.mode = AppMode.AGENT_CHAT.value
            db.session.commit()
            return True
        return False

    @property
    def mode_compatible_with_agent(self) -> str:
        if self.mode == AppMode.CHAT.value and self.is_agent:
            return AppMode.AGENT_CHAT.value

        return self.mode

    @property
    def deleted_tools(self) -> list:
        """
        获取已从系统中删除的工具名称列表。

        返回:
        - 已删除工具的名称列表。
        """
        # 获取并处理应用的代理模式工具配置
        app_model_config = self.app_model_config
        if not app_model_config:
            return []
        if not app_model_config.agent_mode:
            return []
        agent_mode = app_model_config.agent_mode_dict
        tools = agent_mode.get('tools', [])

        provider_ids = []

        # 筛选出有效的API提供者ID
        for tool in tools:
            keys = list(tool.keys())
            if len(keys) >= 4:
                provider_type = tool.get('provider_type', '')
                provider_id = tool.get('provider_id', '')
                if provider_type == 'api':
                    # 如果提供者ID是有效的UUID，则加入到列表中
                    try:
                        uuid.UUID(provider_id)
                    except Exception:
                        continue
                    provider_ids.append(provider_id)

        if not provider_ids:
            return []

        # 查询数据库，确认哪些工具的提供者已经被删除
        api_providers = db.session.execute(
            text('SELECT id FROM tool_api_providers WHERE id IN :provider_ids'),
            {'provider_ids': tuple(provider_ids)}
        ).fetchall()

        deleted_tools = []
        current_api_provider_ids = [str(api_provider.id) for api_provider in api_providers]

        # 比较当前和已删除的提供者ID，收集已删除的工具名称
        for tool in tools:
            keys = list(tool.keys())
            if len(keys) >= 4:
                provider_type = tool.get('provider_type', '')
                provider_id = tool.get('provider_id', '')
                if provider_type == 'api' and provider_id not in current_api_provider_ids:
                    deleted_tools.append(tool['tool_name'])

        return deleted_tools

    @property
    def tags(self):
        tags = db.session.query(Tag).join(
            TagBinding,
            Tag.id == TagBinding.tag_id
        ).filter(
            TagBinding.target_id == self.id,
            TagBinding.tenant_id == self.tenant_id,
            Tag.tenant_id == self.tenant_id,
            Tag.type == 'app'
        ).all()

        return tags if tags else []


class AppModelConfig(db.Model):
    """
    应用模型配置类，用于表示应用程序与模型之间的配置关系。
    
    属性:
    - id: 唯一标识符，使用UUID生成。
    - app_id: 关联的应用程序的唯一标识符，不可为空。
    - provider: 模型提供者。
    - model_id: 模型的唯一标识符，不可为空。
    - configs: 模型的配置信息，以JSON格式存储，不可为空。
    - created_at: 记录创建时间，不可为空，默认为当前时间。
    - updated_at: 记录更新时间，不可为空，默认为当前时间。
    - opening_statement: 开场白。
    - suggested_questions: 建议的问题列表。
    - suggested_questions_after_answer: 回答后建议的问题。
    - speech_to_text: 语音转文本的配置。
    - text_to_speech: 文本转语音的配置。
    - more_like_this: 类似的配置。
    - model: 有关模型的额外信息。
    - user_input_form: 用户输入表单的配置。
    - dataset_query_variable: 数据集查询变量。
    - pre_prompt: 预提示信息。
    - agent_mode: 代理模式配置。
    - sensitive_word_avoidance: 敏感词规避配置。
    - retriever_resource: 检索资源配置。
    - prompt_type: 提示类型，默认为'simple'。
    - chat_prompt_config: 聊天提示配置。
    - completion_prompt_config: 完成提示配置。
    - dataset_configs: 数据集配置。
    - external_data_tools: 外部数据工具配置。
    - file_upload: 文件上传配置。
    
    方法:
    - app: 根据app_id获取关联的应用程序对象。
    - model_dict: 获取model属性解析后的字典形式。
    - suggested_questions_list: 获取suggested_questions属性解析后的列表形式。
    - suggested_questions_after_answer_dict: 获取suggested_questions_after_answer属性解析后的字典形式，若不存在则默认为{"enabled": False}。
    - speech_to_text_dict: 获取speech_to_text属性解析后的字典形式，若不存在则默认为{"enabled": False}。
    - text_to_speech_dict: 获取text_to_speech属性解析后的字典形式，若不存在则默认为{"enabled": False}。
    - retriever_resource_dict: 获取retriever_resource属性解析后的字典形式，若不存在则默认为{"enabled": False}。
    - annotation_reply_dict：获取注解回复配置的字典表示。
    - more_like_this_dict：获取"更多类似"功能的配置字典。
    - sensitive_word_avoidance_dict：获取敏感词规避配置的字典表示。
    - external_data_tools_list：获取外部数据工具列表的字典表示。
    - user_input_form_list：获取用户输入表单配置的列表表示。
    - agent_mode_dict：获取代理模式配置的字典表示。
    - chat_prompt_config_dict：获取聊天提示配置的字典表示。
    - completion_prompt_config_dict：获取完成提示配置的字典表示。
    - dataset_configs_dict：获取数据集配置的字典表示。
    - file_upload_dict：获取文件上传配置的字典表示。
    """

    __tablename__ = 'app_model_configs'
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='app_model_config_pkey'),
        db.Index('app_app_id_idx', 'app_id')
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    app_id = db.Column(StringUUID, nullable=False)
    provider = db.Column(db.String(255), nullable=True)
    model_id = db.Column(db.String(255), nullable=True)
    configs = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    opening_statement = db.Column(db.Text)
    suggested_questions = db.Column(db.Text)
    suggested_questions_after_answer = db.Column(db.Text)
    speech_to_text = db.Column(db.Text)
    text_to_speech = db.Column(db.Text)
    more_like_this = db.Column(db.Text)
    model = db.Column(db.Text)
    user_input_form = db.Column(db.Text)
    dataset_query_variable = db.Column(db.String(255))
    pre_prompt = db.Column(db.Text)
    agent_mode = db.Column(db.Text)
    sensitive_word_avoidance = db.Column(db.Text)
    retriever_resource = db.Column(db.Text)
    prompt_type = db.Column(db.String(255), nullable=False, server_default=db.text("'simple'::character varying"))
    chat_prompt_config = db.Column(db.Text)
    completion_prompt_config = db.Column(db.Text)
    dataset_configs = db.Column(db.Text)
    external_data_tools = db.Column(db.Text)
    file_upload = db.Column(db.Text)

    @property
    def app(self):
        """
        根据app_id获取关联的应用程序对象。
        
        返回:
        - App对象: 与当前AppModelConfig关联的应用程序对象。
        """
        app = db.session.query(App).filter(App.id == self.app_id).first()
        return app

    @property
    def model_dict(self) -> dict:
        """
        获取model属性解析后的字典形式。
        
        返回:
        - dict: model属性解析后的字典形式，如果model为空则返回None。
        """
        return json.loads(self.model) if self.model else None

    @property
    def suggested_questions_list(self) -> list:
        """
        获取suggested_questions属性解析后的列表形式。
        
        返回:
        - list: suggested_questions属性解析后的列表形式，如果suggested_questions为空则返回空列表。
        """
        return json.loads(self.suggested_questions) if self.suggested_questions else []

    @property
    def suggested_questions_after_answer_dict(self) -> dict:
        """
        获取suggested_questions_after_answer属性解析后的字典形式，若不存在则默认为{"enabled": False}。
        
        返回:
        - dict: suggested_questions_after_answer属性解析后的字典形式。
        """
        return json.loads(self.suggested_questions_after_answer) if self.suggested_questions_after_answer \
            else {"enabled": False}

    @property
    def speech_to_text_dict(self) -> dict:
        """
        获取speech_to_text属性解析后的字典形式，若不存在则默认为{"enabled": False}。
        
        返回:
        - dict: speech_to_text属性解析后的字典形式。
        """
        return json.loads(self.speech_to_text) if self.speech_to_text \
            else {"enabled": False}

    @property
    def text_to_speech_dict(self) -> dict:
        """
        获取text_to_speech属性解析后的字典形式，若不存在则默认为{"enabled": False}。
        
        返回:
        - dict: text_to_speech属性解析后的字典形式。
        """
        return json.loads(self.text_to_speech) if self.text_to_speech \
            else {"enabled": False}

    @property
    def retriever_resource_dict(self) -> dict:
        """
        获取retriever_resource属性解析后的字典形式，若不存在则默认为{"enabled": False}。
        
        返回:
        - dict: retriever_resource属性解析后的字典形式。
        """
        return json.loads(self.retriever_resource) if self.retriever_resource \
            else {"enabled": True}

    @property
    def annotation_reply_dict(self) -> dict:
        """
        获取注解回复配置的字典表示。

        返回:
            dict: 包含注解设置的id、启用状态、分数阈值和嵌入模型信息的字典。
        """
        # 从数据库查询注解设置，并根据设置构建返回的字典
        annotation_setting = db.session.query(AppAnnotationSetting).filter(
            AppAnnotationSetting.app_id == self.app_id).first()
        if annotation_setting:
            collection_binding_detail = annotation_setting.collection_binding_detail
            return {
                "id": annotation_setting.id,
                "enabled": True,
                "score_threshold": annotation_setting.score_threshold,
                "embedding_model": {
                    "embedding_provider_name": collection_binding_detail.provider_name,
                    "embedding_model_name": collection_binding_detail.model_name
                }
            }

        else:
            return {"enabled": False}

    @property
    def more_like_this_dict(self) -> dict:
        """
        获取"更多类似"功能的配置字典。

        返回:
            dict: 包含该功能的启用状态的字典。
        """
        # 将字符串形式的配置转换为字典形式，若无配置，则返回禁用状态
        return json.loads(self.more_like_this) if self.more_like_this else {"enabled": False}

    @property
    def sensitive_word_avoidance_dict(self) -> dict:
        """
        获取敏感词规避配置的字典表示。

        返回:
            dict: 包含敏感词规避的启用状态、类型和配置信息的字典。
        """
        # 处理敏感词规避配置，转换为字典格式，若无配置，则返回默认禁用状态
        return json.loads(self.sensitive_word_avoidance) if self.sensitive_word_avoidance \
            else {"enabled": False, "type": "", "configs": []}

    @property
    def external_data_tools_list(self) -> list[dict]:
        """
        获取外部数据工具列表的字典表示。

        返回:
            list[dict]: 包含外部数据工具信息的列表。
        """
        # 将外部数据工具的字符串配置转换为列表形式，若无配置，则返回空列表
        return json.loads(self.external_data_tools) if self.external_data_tools \
            else []

    @property
    def user_input_form_list(self) -> dict:
        """
        获取用户输入表单配置的列表表示。

        返回:
            dict: 包含用户输入表单信息的列表。
        """
        # 将用户输入表单的字符串配置转换为列表形式，若无配置，则返回空列表
        return json.loads(self.user_input_form) if self.user_input_form else []

    @property
    def agent_mode_dict(self) -> dict:
        return json.loads(self.agent_mode) if self.agent_mode else {"enabled": False, "strategy": None, "tools": [],
                                                                    "prompt": None}

    @property
    def chat_prompt_config_dict(self) -> dict:
        """
        获取聊天提示配置的字典表示。

        返回:
            dict: 聊天提示配置的字典。
        """
        # 转换聊天提示配置为字典形式，若无配置，则返回空字典
        return json.loads(self.chat_prompt_config) if self.chat_prompt_config else {}

    @property
    def completion_prompt_config_dict(self) -> dict:
        """
        获取完成提示配置的字典表示。

        返回:
            dict: 完成提示配置的字典。
        """
        # 转换完成提示配置为字典形式，若无配置，则返回空字典
        return json.loads(self.completion_prompt_config) if self.completion_prompt_config else {}

    @property
    def dataset_configs_dict(self) -> dict:
        """
        获取数据集配置的字典表示。

        返回:
            dict: 包含数据集配置信息的字典，若无配置，默认返回单模型检索配置。
        """
        # 处理数据集配置，转换为字典格式，若无配置，则返回默认的单模型检索配置
        if self.dataset_configs:
            dataset_configs = json.loads(self.dataset_configs)
            if 'retrieval_model' not in dataset_configs:
                return {'retrieval_model': 'single'}
            else:
                return dataset_configs
        return {
                'retrieval_model': 'multiple',
            }

    @property
    def file_upload_dict(self) -> dict:
        """
        获取文件上传配置的字典表示。

        返回:
            dict: 包含文件上传配置的字典，若无配置，则返回默认配置。
        """
        # 转换文件上传配置为字典形式，若无配置，则返回默认配置
        return json.loads(self.file_upload) if self.file_upload else {
            "image": {"enabled": False, "number_limits": 3, "detail": "high",
                      "transfer_methods": ["remote_url", "local_file"]}}

    def to_dict(self) -> dict:
        """
        将对象转换为字典格式。
        
        该方法整理并返回了一个包含模型配置、问答建议、语音转换设置等多样信息的字典结构，方便对聊天机器人进行配置和管理。
        
        返回值:
            dict: 包含模型提供者、模型ID、配置信息、开场白、建议问题等多样信息的字典。
        """
        return {
            "opening_statement": self.opening_statement,
            "suggested_questions": self.suggested_questions_list,
            "suggested_questions_after_answer": self.suggested_questions_after_answer_dict,
            "speech_to_text": self.speech_to_text_dict,
            "text_to_speech": self.text_to_speech_dict,
            "retriever_resource": self.retriever_resource_dict,
            "annotation_reply": self.annotation_reply_dict,
            "more_like_this": self.more_like_this_dict,
            "sensitive_word_avoidance": self.sensitive_word_avoidance_dict,
            "external_data_tools": self.external_data_tools_list,
            "model": self.model_dict,
            "user_input_form": self.user_input_form_list,
            "dataset_query_variable": self.dataset_query_variable,
            "pre_prompt": self.pre_prompt,
            "agent_mode": self.agent_mode_dict,
            "prompt_type": self.prompt_type,
            "chat_prompt_config": self.chat_prompt_config_dict,
            "completion_prompt_config": self.completion_prompt_config_dict,
            "dataset_configs": self.dataset_configs_dict,
            "file_upload": self.file_upload_dict
        }

    def from_model_config_dict(self, model_config: dict):
        self.opening_statement = model_config.get('opening_statement')
        self.suggested_questions = json.dumps(model_config['suggested_questions']) \
            if model_config.get('suggested_questions') else None
        self.suggested_questions_after_answer = json.dumps(model_config['suggested_questions_after_answer']) \
            if model_config.get('suggested_questions_after_answer') else None
        self.speech_to_text = json.dumps(model_config['speech_to_text']) \
            if model_config.get('speech_to_text') else None
        self.text_to_speech = json.dumps(model_config['text_to_speech']) \
            if model_config.get('text_to_speech') else None
        self.more_like_this = json.dumps(model_config['more_like_this']) \
            if model_config.get('more_like_this') else None
        self.sensitive_word_avoidance = json.dumps(model_config['sensitive_word_avoidance']) \
            if model_config.get('sensitive_word_avoidance') else None
        self.external_data_tools = json.dumps(model_config['external_data_tools']) \
            if model_config.get('external_data_tools') else None
        self.model = json.dumps(model_config['model']) \
            if model_config.get('model') else None
        self.user_input_form = json.dumps(model_config['user_input_form']) \
            if model_config.get('user_input_form') else None
        self.dataset_query_variable = model_config.get('dataset_query_variable')
        self.pre_prompt = model_config['pre_prompt']
        self.agent_mode = json.dumps(model_config['agent_mode']) \
            if model_config.get('agent_mode') else None
        self.retriever_resource = json.dumps(model_config['retriever_resource']) \
            if model_config.get('retriever_resource') else None
        self.prompt_type = model_config.get('prompt_type', 'simple')
        self.chat_prompt_config = json.dumps(model_config.get('chat_prompt_config')) \
            if model_config.get('chat_prompt_config') else None
        self.completion_prompt_config = json.dumps(model_config.get('completion_prompt_config')) \
            if model_config.get('completion_prompt_config') else None
        self.dataset_configs = json.dumps(model_config.get('dataset_configs')) \
            if model_config.get('dataset_configs') else None
        self.file_upload = json.dumps(model_config.get('file_upload')) \
            if model_config.get('file_upload') else None
        
        return self

    def copy(self):
        """
        创建当前AppModelConfig对象的一个深拷贝。
        
        参数:
        - 无
        
        返回值:
        - new_app_model_config: AppModelConfig类型，一个新的AppModelConfig对象，是当前对象的深拷贝。
        """
        # 初始化一个新的AppModelConfig实例，复制当前实例的所有字段但不包括敏感信息
        new_app_model_config = AppModelConfig(
            id=self.id,
            app_id=self.app_id,
            opening_statement=self.opening_statement,
            suggested_questions=self.suggested_questions,
            suggested_questions_after_answer=self.suggested_questions_after_answer,
            speech_to_text=self.speech_to_text,
            text_to_speech=self.text_to_speech,
            more_like_this=self.more_like_this,
            sensitive_word_avoidance=self.sensitive_word_avoidance,
            external_data_tools=self.external_data_tools,
            model=self.model,
            user_input_form=self.user_input_form,
            dataset_query_variable=self.dataset_query_variable,
            pre_prompt=self.pre_prompt,
            agent_mode=self.agent_mode,
            retriever_resource=self.retriever_resource,
            prompt_type=self.prompt_type,
            chat_prompt_config=self.chat_prompt_config,
            completion_prompt_config=self.completion_prompt_config,
            dataset_configs=self.dataset_configs,
            file_upload=self.file_upload
        )

        return new_app_model_config


class RecommendedApp(db.Model):
    """
    推荐应用模型类，用于表示推荐应用的信息
    
    属性:
    - id: 应用的唯一标识符，UUID类型，自动生成
    - app_id: 关联的应用的ID，UUID类型，不可为空
    - description: 应用的描述信息，JSON类型，不可为空
    - copyright: 应用的版权声明信息，字符串类型，不可为空
    - privacy_policy: 应用的隐私政策链接，字符串类型，不可为空
    - category: 应用的分类，字符串类型，不可为空
    - position: 应用在推荐列表中的位置，整数类型，默认为0
    - is_listed: 应用是否在推荐列表上显示，布尔类型，默认为True
    - install_count: 应用的安装计数，整数类型，默认为0
    - language: 应用的语言设置，字符串类型，默认为'en-US'
    - created_at: 记录创建时间，日期时间类型，默认为当前时间
    - updated_at: 记录更新时间，日期时间类型，默认为当前时间
    """
    
    __tablename__ = 'recommended_apps'  # 指定数据库表名为recommended_apps
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='recommended_app_pkey'),  # 指定主键约束
        db.Index('recommended_app_app_id_idx', 'app_id'),  # 为app_id创建索引
        db.Index('recommended_app_is_listed_idx', 'is_listed', 'language')  # 为is_listed和language创建复合索引
    )

    id = db.Column(StringUUID, primary_key=True, server_default=db.text('uuid_generate_v4()'))
    app_id = db.Column(StringUUID, nullable=False)
    description = db.Column(db.JSON, nullable=False)
    copyright = db.Column(db.String(255), nullable=False)
    privacy_policy = db.Column(db.String(255), nullable=False)
    custom_disclaimer = db.Column(db.String(255), nullable=True)
    category = db.Column(db.String(255), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    is_listed = db.Column(db.Boolean, nullable=False, default=True)
    install_count = db.Column(db.Integer, nullable=False, default=0)
    language = db.Column(db.String(255), nullable=False, server_default=db.text("'en-US'::character varying"))
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))

    @property
    def app(self):
        """
        获取关联的应用对象
        
        返回值:
        - App对象: 与当前推荐应用关联的应用对象，如果找不到则返回None
        """
        app = db.session.query(App).filter(App.id == self.app_id).first()
        return app

class InstalledApp(db.Model):
    """
    已安装应用的模型类，用于表示一个租户安装的具体应用的信息。
    
    属性:
    - id: 应用的唯一标识符，使用UUID生成。
    - tenant_id: 租户的唯一标识符，不可为空。
    - app_id: 应用的唯一标识符，不可为空。
    - app_owner_tenant_id: 应用所有者的租户标识符，不可为空。
    - position: 应用在界面中的位置，默认为0。
    - is_pinned: 应用是否被固定在界面上，默认为false。
    - last_used_at: 应用最后一次被使用的时间，可为空。
    - created_at: 记录创建的时间，不可为空。
    
    方法:
    - app: 一个属性方法，返回与该安装记录关联的应用对象。
    - tenant: 一个属性方法，返回与该安装记录关联的租户对象。
    - is_agent: 一个属性方法，判断该应用是否为代理应用。
    """
    __tablename__ = 'installed_apps'  # 指定数据库表名为installed_apps
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='installed_app_pkey'),  # 指定id为表的主要键
        db.Index('installed_app_tenant_id_idx', 'tenant_id'),  # 为tenant_id创建索引
        db.Index('installed_app_app_id_idx', 'app_id'),  # 为app_id创建索引
        db.UniqueConstraint('tenant_id', 'app_id', name='unique_tenant_app')  # 确保每个租户对每个应用只能有一条安装记录
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    tenant_id = db.Column(StringUUID, nullable=False)
    app_id = db.Column(StringUUID, nullable=False)
    app_owner_tenant_id = db.Column(StringUUID, nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    is_pinned = db.Column(db.Boolean, nullable=False, server_default=db.text('false'))
    last_used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))

    @property
    def app(self):
        """
        查询并返回与当前安装记录关联的应用对象。
        
        返回:
        - App对象: 与当前安装记录关联的应用对象，如果找不到则返回None。
        """
        app = db.session.query(App).filter(App.id == self.app_id).first()
        return app

    @property
    def tenant(self):
        """
        查询并返回与当前安装记录关联的租户对象。
        
        返回:
        - Tenant对象: 与当前安装记录关联的租户对象，如果找不到则返回None。
        """
        tenant = db.session.query(Tenant).filter(Tenant.id == self.tenant_id).first()
        return tenant



class Conversation(db.Model):
    """
    对话模型，用于表示一个对话实体。

    属性:
    - id: 对话的唯一标识符。
    - app_id: 关联的应用程序ID。
    - app_model_config_id: 关联的应用模型配置ID。
    - model_provider: 模型提供者。
    - override_model_configs: 覆盖的模型配置。
    - model_id: 模型ID。
    - mode: 模式。
    - name: 对话名称。
    - summary: 对话摘要。
    - inputs: 输入参数。
    - introduction: 介绍。
    - system_instruction: 系统指令。
    - system_instruction_tokens: 系统指令标记。
    - status: 状态。
    - from_source: 来源。
    - from_end_user_id: 来自终端用户的ID。
    - from_account_id: 来自账户的ID。
    - read_at: 阅读时间。
    - read_account_id: 阅读账户ID。
    - created_at: 创建时间。
    - updated_at: 更新时间。
    - messages: 消息关系。
    - message_annotations: 消息注解关系。
    - is_deleted: 是否已删除。
    
    方法:
    - model_config: 获取当前对话所使用的模型配置信息。
    - summary_or_query: 获取对话摘要或首个消息的查询内容。
    - annotated: 判断对话是否包含注解信息。
    - annotation: 获取对话的第一个注解信息。
    - message_count: 获取对话中包含的消息总数。
    - user_feedback_stats: 获取用户反馈统计数据。
    - admin_feedback_stats: 获取管理员反馈统计数据。
    - first_message: 获取对话中的第一条消息。
    - app: 获取与对话关联的应用程序实例。
    - from_end_user_session_id: 获取发起对话的终端用户的会话ID。
    - in_debug_mode: 判断对话是否处于调试模式。
    """
    # 定义表名和主键等数据库表配置
    __tablename__ = 'conversations'
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='conversation_pkey'),
        db.Index('conversation_app_from_user_idx', 'app_id', 'from_source', 'from_end_user_id')
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    app_id = db.Column(StringUUID, nullable=False)
    app_model_config_id = db.Column(StringUUID, nullable=True)
    model_provider = db.Column(db.String(255), nullable=True)
    override_model_configs = db.Column(db.Text)
    model_id = db.Column(db.String(255), nullable=True)
    mode = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    summary = db.Column(db.Text)
    inputs = db.Column(db.JSON)
    introduction = db.Column(db.Text)
    system_instruction = db.Column(db.Text)
    system_instruction_tokens = db.Column(db.Integer, nullable=False, server_default=db.text('0'))
    status = db.Column(db.String(255), nullable=False)
    invoke_from = db.Column(db.String(255), nullable=True)
    from_source = db.Column(db.String(255), nullable=False)
    from_end_user_id = db.Column(StringUUID)
    from_account_id = db.Column(StringUUID)
    read_at = db.Column(db.DateTime)
    read_account_id = db.Column(StringUUID)
    dialogue_count: Mapped[int] = mapped_column(default=0)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))

    # 定义与其他模型的关系
    messages = db.relationship("Message", backref="conversation", lazy='select', passive_deletes="all")
    message_annotations = db.relationship("MessageAnnotation", backref="conversation", lazy='select', passive_deletes="all")

    is_deleted = db.Column(db.Boolean, nullable=False, server_default=db.text('false'))

    @property
    def model_config(self):
        """
        获取模型配置。

        返回:
        - 模型配置的字典表示。
        """
        model_config = {}
        if self.mode == AppMode.ADVANCED_CHAT.value:
            if self.override_model_configs:
                override_model_configs = json.loads(self.override_model_configs)
                model_config = override_model_configs
        else:
            if self.override_model_configs:
                override_model_configs = json.loads(self.override_model_configs)

                if 'model' in override_model_configs:
                    app_model_config = AppModelConfig()
                    app_model_config = app_model_config.from_model_config_dict(override_model_configs)
                    model_config = app_model_config.to_dict()
                else:
                    model_config['configs'] = override_model_configs
            else:
                app_model_config = db.session.query(AppModelConfig).filter(
                    AppModelConfig.id == self.app_model_config_id).first()

                model_config = app_model_config.to_dict()

        model_config['model_id'] = self.model_id
        model_config['provider'] = self.model_provider

        return model_config

    @property
    def summary_or_query(self):
        """
        获取对话摘要或第一个消息的查询内容。

        返回:
        - 对话摘要或第一个消息的查询字符串。
        """
        if self.summary:
            return self.summary
        else:
            first_message = self.first_message
            if first_message:
                return first_message.query
            else:
                return ''

    @property
    def annotated(self):
        """
        检查对话是否有注解。

        返回:
        - 如果对话有注解则为True，否则为False。
        """
        return db.session.query(MessageAnnotation).filter(MessageAnnotation.conversation_id == self.id).count() > 0

    @property
    def annotation(self):
        """
        获取对话的第一个注解。

        返回:
        - 第一个注解对象，如果没有则为None。
        """
        return db.session.query(MessageAnnotation).filter(MessageAnnotation.conversation_id == self.id).first()

    @property
    def message_count(self):
        """
        获取对话中的消息数量。

        返回:
        - 消息数量。
        """
        return db.session.query(Message).filter(Message.conversation_id == self.id).count()

    @property
    def user_feedback_stats(self):
        """
        获取用户反馈统计信息。

        返回:
        - 包含"like"和"dislike"计数的字典。
        """
        like = db.session.query(MessageFeedback) \
            .filter(MessageFeedback.conversation_id == self.id,
                    MessageFeedback.from_source == 'user',
                    MessageFeedback.rating == 'like').count()

        dislike = db.session.query(MessageFeedback) \
            .filter(MessageFeedback.conversation_id == self.id,
                    MessageFeedback.from_source == 'user',
                    MessageFeedback.rating == 'dislike').count()

        return {'like': like, 'dislike': dislike}

    @property
    def admin_feedback_stats(self):
        """
        获取管理员反馈统计信息。

        返回:
        - 包含"like"和"dislike"计数的字典。
        """
        like = db.session.query(MessageFeedback) \
            .filter(MessageFeedback.conversation_id == self.id,
                    MessageFeedback.from_source == 'admin',
                    MessageFeedback.rating == 'like').count()

        dislike = db.session.query(MessageFeedback) \
            .filter(MessageFeedback.conversation_id == self.id,
                    MessageFeedback.from_source == 'admin',
                    MessageFeedback.rating == 'dislike').count()

        return {'like': like, 'dislike': dislike}

    @property
    def first_message(self):
        """
        获取对话中的第一个消息。

        返回:
        - 第一个消息对象，如果没有则为None。
        """
        return db.session.query(Message).filter(Message.conversation_id == self.id).first()

    @property
    def app(self):
        """
        获取对话关联的应用程序。

        返回:
        - 关联的应用程序对象，如果没有则为None。
        """
        return db.session.query(App).filter(App.id == self.app_id).first()

    @property
    def from_end_user_session_id(self):
        """
        获取来自终端用户的会话ID。

        返回:
        - 终端用户会话ID，如果不存在则为None。
        """
        if self.from_end_user_id:
            end_user = db.session.query(EndUser).filter(EndUser.id == self.from_end_user_id).first()
            if end_user:
                return end_user.session_id

        return None

    @property
    def in_debug_mode(self):
        """
        检查对话是否处于调试模式。

        返回:
        - 如果对话配置了覆盖模型配置，则为True，表示处于调试模式；否则为False。
        """
        return self.override_model_configs is not None


class Message(db.Model):
    """
    消息模型，用于表示与对话相关的信息和元数据。
    
    属性:
    - id: 消息的唯一标识符。
    - app_id: 关联的应用程序ID。
    - model_provider: 模型提供者。
    - model_id: 模型的ID。
    - override_model_configs: 覆盖的模型配置。
    - conversation_id: 对话的唯一标识符。
    - inputs: 输入消息的内容。
    - query: 查询内容。
    - message: 消息的内容。
    - message_tokens: 消息的标记数量。
    - message_unit_price: 消息的单位价格。
    - message_price_unit: 消息的价格单位。
    - answer: 答案内容。
    - answer_tokens: 答案的标记数量。
    - answer_unit_price: 答案的单位价格。
    - answer_price_unit: 答案的价格单位。
    - provider_response_latency: 提供者响应延迟。
    - total_price: 总价格。
    - currency: 货币单位。
    - from_source: 消息来源。
    - from_end_user_id: 来自终端用户的ID。
    - from_account_id: 来自账户的ID。
    - created_at: 创建时间。
    - updated_at: 更新时间。
    - agent_based: 是否基于代理。

    方法:
    - user_feedback: 获取用户的反馈信息。
    - admin_feedback: 获取管理员的反馈信息。
    - feedbacks: 获取所有反馈信息。
    - annotation: 获取注解信息。
    - annotation_hit_history: 获取注解命中历史。
    - app_model_config: 获取应用模型配置。
    - in_debug_mode: 判断是否处于调试模式。
    - agent_thoughts: 获取代理思考信息。
    - retriever_resources: 获取检索资源信息。
    - message_files: 获取消息文件信息。
    - files: 获取所有文件信息，包括处理后的URL等。
    """
    __tablename__ = 'messages'
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='message_pkey'),
        db.Index('message_app_id_idx', 'app_id', 'created_at'),
        db.Index('message_conversation_id_idx', 'conversation_id'),
        db.Index('message_end_user_idx', 'app_id', 'from_source', 'from_end_user_id'),
        db.Index('message_account_idx', 'app_id', 'from_source', 'from_account_id'),
        db.Index('message_workflow_run_id_idx', 'conversation_id', 'workflow_run_id')
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    app_id = db.Column(StringUUID, nullable=False)
    model_provider = db.Column(db.String(255), nullable=True)
    model_id = db.Column(db.String(255), nullable=True)
    override_model_configs = db.Column(db.Text)
    conversation_id = db.Column(StringUUID, db.ForeignKey('conversations.id'), nullable=False)
    inputs = db.Column(db.JSON)
    query = db.Column(db.Text, nullable=False)
    message = db.Column(db.JSON, nullable=False)
    message_tokens = db.Column(db.Integer, nullable=False, server_default=db.text('0'))
    message_unit_price = db.Column(db.Numeric(10, 4), nullable=False)
    message_price_unit = db.Column(db.Numeric(10, 7), nullable=False, server_default=db.text('0.001'))
    answer = db.Column(db.Text, nullable=False)
    answer_tokens = db.Column(db.Integer, nullable=False, server_default=db.text('0'))
    answer_unit_price = db.Column(db.Numeric(10, 4), nullable=False)
    answer_price_unit = db.Column(db.Numeric(10, 7), nullable=False, server_default=db.text('0.001'))
    provider_response_latency = db.Column(db.Float, nullable=False, server_default=db.text('0'))
    total_price = db.Column(db.Numeric(10, 7))
    currency = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(255), nullable=False, server_default=db.text("'normal'::character varying"))
    error = db.Column(db.Text)
    message_metadata = db.Column(db.Text)
    invoke_from = db.Column(db.String(255), nullable=True)
    from_source = db.Column(db.String(255), nullable=False)
    from_end_user_id = db.Column(StringUUID)
    from_account_id = db.Column(StringUUID)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    agent_based = db.Column(db.Boolean, nullable=False, server_default=db.text('false'))
    workflow_run_id = db.Column(StringUUID)

    @property
    def re_sign_file_url_answer(self) -> str:
        if not self.answer:
            return self.answer

        pattern = r'\[!?.*?\]\((((http|https):\/\/.+)?\/files\/(tools\/)?[\w-]+.*?timestamp=.*&nonce=.*&sign=.*)\)'
        matches = re.findall(pattern, self.answer)

        if not matches:
            return self.answer

        urls = [match[0] for match in matches]

        # remove duplicate urls
        urls = list(set(urls))

        if not urls:
            return self.answer

        re_sign_file_url_answer = self.answer
        for url in urls:
            if 'files/tools' in url:
                # get tool file id
                tool_file_id_pattern = r'\/files\/tools\/([\.\w-]+)?\?timestamp='
                result = re.search(tool_file_id_pattern, url)
                if not result:
                    continue

                tool_file_id = result.group(1)

                # get extension
                if '.' in tool_file_id:
                    split_result = tool_file_id.split('.')
                    extension = f'.{split_result[-1]}'
                    if len(extension) > 10:
                        extension = '.bin'
                    tool_file_id = split_result[0]
                else:
                    extension = '.bin'

                if not tool_file_id:
                    continue

                sign_url = ToolFileParser.get_tool_file_manager().sign_file(
                    tool_file_id=tool_file_id,
                    extension=extension
                )
            else:
                # get upload file id
                upload_file_id_pattern = r'\/files\/([\w-]+)\/image-preview?\?timestamp='
                result = re.search(upload_file_id_pattern, url)
                if not result:
                    continue

                upload_file_id = result.group(1)

                if not upload_file_id:
                    continue

                sign_url = UploadFileParser.get_signed_temp_image_url(upload_file_id)

            re_sign_file_url_answer = re_sign_file_url_answer.replace(url, sign_url)

        return re_sign_file_url_answer

    @property
    def user_feedback(self):
        """
        获取用户的反馈信息。
        
        返回:
        - user_feedback: 用户反馈的实例。
        """
        feedback = db.session.query(MessageFeedback).filter(MessageFeedback.message_id == self.id,
                                                            MessageFeedback.from_source == 'user').first()
        return feedback

    @property
    def admin_feedback(self):
        """
        获取管理员的反馈信息。
        
        返回:
        - admin_feedback: 管理员反馈的实例。
        """
        feedback = db.session.query(MessageFeedback).filter(MessageFeedback.message_id == self.id,
                                                            MessageFeedback.from_source == 'admin').first()
        return feedback

    @property
    def feedbacks(self):
        """
        获取所有反馈信息。
        
        返回:
        - feedbacks: 反馈信息列表。
        """
        feedbacks = db.session.query(MessageFeedback).filter(MessageFeedback.message_id == self.id).all()
        return feedbacks

    @property
    def annotation(self):
        """
        获取注解信息。
        
        返回:
        - annotation: 注解的实例。
        """
        annotation = db.session.query(MessageAnnotation).filter(MessageAnnotation.message_id == self.id).first()
        return annotation

    @property
    def annotation_hit_history(self):
        """
        获取注解命中历史。
        
        返回:
        - annotation: 命中历史对应的注解实例，如果没有则返回None。
        """
        annotation_history = (db.session.query(AppAnnotationHitHistory)
                              .filter(AppAnnotationHitHistory.message_id == self.id).first())
        if annotation_history:
            annotation = (db.session.query(MessageAnnotation).
                          filter(MessageAnnotation.id == annotation_history.annotation_id).first())
            return annotation
        return None

    @property
    def app_model_config(self):
        """
        获取应用模型配置。
        
        返回:
        - app_model_config: 应用模型配置的实例，如果没有则返回None。
        """
        conversation = db.session.query(Conversation).filter(Conversation.id == self.conversation_id).first()
        if conversation:
            return db.session.query(AppModelConfig).filter(
                AppModelConfig.id == conversation.app_model_config_id).first()

        return None

    @property
    def in_debug_mode(self):
        """
        判断消息是否处于调试模式。
        
        返回:
        - bool: 如果有覆盖的模型配置则为True，否则为False。
        """
        return self.override_model_configs is not None

    @property
    def message_metadata_dict(self) -> dict:
        return json.loads(self.message_metadata) if self.message_metadata else {}

    @property
    def agent_thoughts(self):
        """
        获取代理思考信息。
        
        返回:
        - agent_thoughts: 代理思考信息列表，按位置升序排列。
        """
        return db.session.query(MessageAgentThought).filter(MessageAgentThought.message_id == self.id) \
            .order_by(MessageAgentThought.position.asc()).all()

    @property
    def retriever_resources(self):
        """
        获取检索资源信息。
        
        返回:
        - retriever_resources: 检索资源信息列表，按位置升序排列。
        """
        return db.session.query(DatasetRetrieverResource).filter(DatasetRetrieverResource.message_id == self.id) \
            .order_by(DatasetRetrieverResource.position.asc()).all()

    @property
    def message_files(self):
        """
        获取消息文件信息。
        
        返回:
        - message_files: 消息文件列表。
        """
        return db.session.query(MessageFile).filter(MessageFile.message_id == self.id).all()

    @property
    def files(self):
        """
        获取所有文件信息，包括处理后的URL等。
        
        返回:
        - files: 包含文件ID、类型、URL和归属者的字典列表。
        """
        message_files = self.message_files

        files = []
        for message_file in message_files:
            url = message_file.url
            if message_file.type == 'image':
                if message_file.transfer_method == 'local_file':
                    upload_file = (db.session.query(UploadFile)
                                   .filter(
                        UploadFile.id == message_file.upload_file_id
                    ).first())

                    url = UploadFileParser.get_image_data(
                        upload_file=upload_file,
                        force_url=True
                    )
                if message_file.transfer_method == 'tool_file':
                    # get tool file id
                    tool_file_id = message_file.url.split('/')[-1]
                    # trim extension
                    tool_file_id = tool_file_id.split('.')[0]

                    # get extension
                    if '.' in message_file.url:
                        extension = f'.{message_file.url.split(".")[-1]}'
                        if len(extension) > 10:
                            extension = '.bin'
                    else:
                        extension = '.bin'
                    # add sign url
                    url = ToolFileParser.get_tool_file_manager().sign_file(tool_file_id=tool_file_id, extension=extension)

            files.append({
                'id': message_file.id,
                'type': message_file.type,
                'url': url,
                'belongs_to': message_file.belongs_to if message_file.belongs_to else 'user'
            })

        return files

    @property
    def workflow_run(self):
        if self.workflow_run_id:
            from .workflow import WorkflowRun
            return db.session.query(WorkflowRun).filter(WorkflowRun.id == self.workflow_run_id).first()

        return None

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'app_id': self.app_id,
            'conversation_id': self.conversation_id,
            'inputs': self.inputs,
            'query': self.query,
            'message': self.message,
            'answer': self.answer,
            'status': self.status,
            'error': self.error,
            'message_metadata': self.message_metadata_dict,
            'from_source': self.from_source,
            'from_end_user_id': self.from_end_user_id,
            'from_account_id': self.from_account_id,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'agent_based': self.agent_based,
            'workflow_run_id': self.workflow_run_id
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            id=data['id'],
            app_id=data['app_id'],
            conversation_id=data['conversation_id'],
            inputs=data['inputs'],
            query=data['query'],
            message=data['message'],
            answer=data['answer'],
            status=data['status'],
            error=data['error'],
            message_metadata=json.dumps(data['message_metadata']),
            from_source=data['from_source'],
            from_end_user_id=data['from_end_user_id'],
            from_account_id=data['from_account_id'],
            created_at=data['created_at'],
            updated_at=data['updated_at'],
            agent_based=data['agent_based'],
            workflow_run_id=data['workflow_run_id']
        )


class MessageFeedback(db.Model):
    """
    消息反馈模型，用于表示用户对消息的反馈信息。
    
    属性:
    - id: 反馈信息的唯一标识符，UUID类型。
    - app_id: 关联的应用程序的ID，UUID类型，不可为空。
    - conversation_id: 关联的对话的ID，UUID类型，不可为空。
    - message_id: 关联的消息的ID，UUID类型，不可为空。
    - rating: 反馈的评分，字符串类型，不可为空。
    - content: 反馈的内容，文本类型，可为空。
    - from_source: 反馈来源，字符串类型，不可为空。
    - from_end_user_id: 提供反馈的终端用户ID，UUID类型，可为空。
    - from_account_id: 提供反馈的账户ID，UUID类型，可为空。
    - created_at: 反馈创建时间，日期时间类型，不可为空。
    - updated_at: 反馈更新时间，日期时间类型，不可为空。
    
    方法:
    - from_account: 获取提供反馈的账户信息。
    """
    
    __tablename__ = 'message_feedbacks'
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='message_feedback_pkey'),  # 主键约束
        db.Index('message_feedback_app_idx', 'app_id'),  # 应用ID索引
        db.Index('message_feedback_message_idx', 'message_id', 'from_source'),  # 消息ID和来源索引
        db.Index('message_feedback_conversation_idx', 'conversation_id', 'from_source', 'rating')  # 对话ID、来源和评分索引
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    app_id = db.Column(StringUUID, nullable=False)
    conversation_id = db.Column(StringUUID, nullable=False)
    message_id = db.Column(StringUUID, nullable=False)
    rating = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text)
    from_source = db.Column(db.String(255), nullable=False)
    from_end_user_id = db.Column(StringUUID)
    from_account_id = db.Column(StringUUID)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))

    @property
    def from_account(self):
        """
        获取提供反馈的账户信息。
        
        返回:
        - Account对象: 提供反馈的账户信息。如果找不到对应账户，则返回None。
        """
        account = db.session.query(Account).filter(Account.id == self.from_account_id).first()
        return account


class MessageFile(db.Model):
    """
    消息文件模型类，用于表示与消息相关的文件信息。
    
    属性:
    - id: 文件的唯一标识符，使用UUID生成。
    - message_id: 关联的消息的唯一标识符，不可为空。
    - type: 文件的类型，如文本、图片等，不可为空。
    - transfer_method: 文件传输方法，如直接上传、链接等，不可为空。
    - url: 文件的访问URL，可以为空。
    - belongs_to: 文件归属的类别或用户ID，可以为空。
    - upload_file_id: 上传过程中生成的文件ID，可以为空。
    - created_by_role: 创建文件的用户角色，如管理员、用户等，不可为空。
    - created_by: 创建文件的用户ID，不可为空。
    - created_at: 文件创建的时间，不可为空且默认为当前时间。
    
    使用数据库模型定义消息文件的表结构，包括主键、索引等设置。
    """
    
    __tablename__ = 'message_files'  # 指定数据库表名为message_files
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='message_file_pkey'),  # 设置id为 primary key
        db.Index('message_file_message_idx', 'message_id'),  # 为message_id创建索引，优化查询
        db.Index('message_file_created_by_idx', 'created_by')  # 为created_by创建索引，优化查询
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    message_id = db.Column(StringUUID, nullable=False)
    type = db.Column(db.String(255), nullable=False)
    transfer_method = db.Column(db.String(255), nullable=False)
    url = db.Column(db.Text, nullable=True)
    belongs_to = db.Column(db.String(255), nullable=True)
    upload_file_id = db.Column(StringUUID, nullable=True)
    created_by_role = db.Column(db.String(255), nullable=False)
    created_by = db.Column(StringUUID, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))


class MessageAnnotation(db.Model):
    """
    消息标注模型，用于表示消息的标注信息。
    
    属性:
    - id: 注解的唯一标识符，使用UUID生成。
    - app_id: 关联的应用程序ID，不可为空。
    - conversation_id: 关联的对话ID，可以为空。
    - message_id: 关联的消息ID，可以为空。
    - question: 注解的问题，可以为空。
    - content: 注解的内容，不可为空。
    - hit_count: 注解的点击次数，不可为空，默认值为0。
    - account_id: 创建注解的账户ID，不可为空。
    - created_at: 注解的创建时间，不可为空，默认为当前时间。
    - updated_at: 注解的更新时间，不可为空，默认为当前时间。
    
    方法:
    - account: 获取创建注解的账户信息。
    - annotation_create_account: 获取创建注解的账户信息（与account方法重复）。
    """
    
    __tablename__ = 'message_annotations'  # 指定数据库表名为message_annotations
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='message_annotation_pkey'),  # 指定id为表的主键
        db.Index('message_annotation_app_idx', 'app_id'),  # 为app_id创建索引
        db.Index('message_annotation_conversation_idx', 'conversation_id'),  # 为conversation_id创建索引
        db.Index('message_annotation_message_idx', 'message_id')  # 为message_id创建索引
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    app_id = db.Column(StringUUID, nullable=False)
    conversation_id = db.Column(StringUUID, db.ForeignKey('conversations.id'), nullable=True)
    message_id = db.Column(StringUUID, nullable=True)
    question = db.Column(db.Text, nullable=True)
    content = db.Column(db.Text, nullable=False)
    hit_count = db.Column(db.Integer, nullable=False, server_default=db.text('0'))
    account_id = db.Column(StringUUID, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))

    @property
    def account(self):
        """
        获取创建注解的账户信息。
        
        返回:
        - Account对象: 创建该注解的账户信息。
        """
        account = db.session.query(Account).filter(Account.id == self.account_id).first()
        return account

    @property
    def annotation_create_account(self):
        """
        获取创建注解的账户信息。
        
        说明:
        - 此方法与account方法功能相同，可能为冗余代码。
        
        返回:
        - Account对象: 创建该注解的账户信息。
        """
        account = db.session.query(Account).filter(Account.id == self.account_id).first()
        return account


class AppAnnotationHitHistory(db.Model):
    """
    App注解命中历史模型类，用于表示应用程序注解的命中历史记录。
    
    属性:
    - id: 唯一标识符，使用UUID生成。
    - app_id: 关联的应用程序ID，不可为空。
    - annotation_id: 关联的注解ID，不可为空。
    - source: 来源信息，不可为空。
    - question: 提问或任务，不可为空。
    - account_id: 创建注解的账户ID，不可为空。
    - created_at: 记录创建时间，不可为空，默认为当前时间。
    - score: 与该记录相关的得分，不可为空，默认为0。
    - message_id: 关联的消息ID，不可为空。
    - annotation_question: 注解的问题或主题，不可为空。
    - annotation_content: 注解的内容，不可为空。
    
    方法:
    - account: 获取创建注解的账户信息。
    - annotation_create_account: 获取创建该记录的账户信息。
    """
    
    __tablename__ = 'app_annotation_hit_histories'
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='app_annotation_hit_histories_pkey'),
        db.Index('app_annotation_hit_histories_app_idx', 'app_id'),
        db.Index('app_annotation_hit_histories_account_idx', 'account_id'),
        db.Index('app_annotation_hit_histories_annotation_idx', 'annotation_id'),
        db.Index('app_annotation_hit_histories_message_idx', 'message_id'),
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    app_id = db.Column(StringUUID, nullable=False)
    annotation_id = db.Column(StringUUID, nullable=False)
    source = db.Column(db.Text, nullable=False)
    question = db.Column(db.Text, nullable=False)
    account_id = db.Column(StringUUID, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    score = db.Column(Float, nullable=False, server_default=db.text('0'))
    message_id = db.Column(StringUUID, nullable=False)
    annotation_question = db.Column(db.Text, nullable=False)
    annotation_content = db.Column(db.Text, nullable=False)

    @property
    def account(self):
        """
        获取创建注解的账户信息。
        
        返回:
        - Account对象：与该注解关联的账户信息。
        """
        account = (db.session.query(Account)
                   .join(MessageAnnotation, MessageAnnotation.account_id == Account.id)
                   .filter(MessageAnnotation.id == self.annotation_id).first())
        return account

    @property
    def annotation_create_account(self):
        """
        获取创建该记录的账户信息。
        
        返回:
        - Account对象：创建该记录的账户信息。
        """
        account = db.session.query(Account).filter(Account.id == self.account_id).first()
        return account


class AppAnnotationSetting(db.Model):
    """
    应用注解设置模型，用于表示应用的注解设置信息。
    
    属性:
    - id: 唯一标识符，使用UUID生成。
    - app_id: 关联的应用ID，不可为空。
    - score_threshold: 分数阈值，不可为空，默认值为0。
    - collection_binding_id: 数据集绑定ID，不可为空。
    - created_user_id: 创建用户的ID，不可为空。
    - created_at: 创建时间，不可为空，默认为当前时间。
    - updated_user_id: 更新用户的ID，不可为空。
    - updated_at: 更新时间，不可为空，默认为当前时间。
    
    方法:
    - created_account: 获取创建该设置的账户信息。
    - updated_account: 获取最后更新该设置的账户信息。
    - collection_binding_detail: 获取与该设置关联的数据集绑定详细信息。
    """
    
    __tablename__ = 'app_annotation_settings'  # 指定数据库表名为app_annotation_settings
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='app_annotation_settings_pkey'),  # 指定主键约束
        db.Index('app_annotation_settings_app_idx', 'app_id')  # 创建app_id的索引
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    app_id = db.Column(StringUUID, nullable=False)
    score_threshold = db.Column(Float, nullable=False, server_default=db.text('0'))
    collection_binding_id = db.Column(StringUUID, nullable=False)
    created_user_id = db.Column(StringUUID, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    updated_user_id = db.Column(StringUUID, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))

    @property
    def created_account(self):
        """
        获取创建该设置的账户信息。
        
        返回:
        - 创建账户的信息对象。
        """
        account = (db.session.query(Account)
                   .join(AppAnnotationSetting, AppAnnotationSetting.created_user_id == Account.id)
                   .filter(AppAnnotationSetting.id == self.annotation_id).first())
        return account

    @property
    def updated_account(self):
        """
        获取最后更新该设置的账户信息。
        
        返回:
        - 最后更新账户的信息对象。
        """
        account = (db.session.query(Account)
                   .join(AppAnnotationSetting, AppAnnotationSetting.updated_user_id == Account.id)
                   .filter(AppAnnotationSetting.id == self.annotation_id).first())
        return account

    @property
    def collection_binding_detail(self):
        """
        获取与该设置关联的数据集绑定详细信息。
        
        返回:
        - 关联的数据集绑定详细信息对象。
        """
        from .dataset import DatasetCollectionBinding
        collection_binding_detail = (db.session.query(DatasetCollectionBinding)
                                     .filter(DatasetCollectionBinding.id == self.collection_binding_id).first())
        return collection_binding_detail


class OperationLog(db.Model):
    """
    操作日志模型类，用于记录操作日志信息。

    属性:
    - id: 操作日志的唯一标识符，使用UUID生成。
    - tenant_id: 租户ID，标识操作所属的租户，不可为空。
    - account_id: 账户ID，标识操作执行者的账户，不可为空。
    - action: 操作动作的描述，使用字符串表示，不可为空。
    - content: 操作内容的详细信息，以JSON格式存储。
    - created_at: 记录创建的时间，不可为空，默认为当前时间。
    - created_ip: 记录创建时的IP地址，不可为空。
    - updated_at: 记录最后更新的时间，不可为空，默认为当前时间。
    """
    __tablename__ = 'operation_logs'  # 指定数据库表名为operation_logs
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='operation_log_pkey'),  # 设置id为PRIMARY KEY
        db.Index('operation_log_account_action_idx', 'tenant_id', 'account_id', 'action')  # 创建索引以加速查询
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    tenant_id = db.Column(StringUUID, nullable=False)
    account_id = db.Column(StringUUID, nullable=False)
    action = db.Column(db.String(255), nullable=False)
    content = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    created_ip = db.Column(db.String(255), nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))


class EndUser(UserMixin, db.Model):
    """
    EndUser 类表示一个最终用户模型，它继承自 Flask-Login 的 UserMixin 以及 SQLAlchemy 的 Model，
    用于定义与数据库交互的用户模型。

    属性:
    - id: 用户唯一标识符，使用UUID生成。
    - tenant_id: 租户ID，不可为空，用于区分不同租户的用户。
    - app_id: 应用ID，可为空，用于区分不同应用的用户。
    - type: 用户类型，不可为空，用于区分不同类型的用户。
    - external_user_id: 外部系统中的用户ID，可为空。
    - name: 用户名，可为空。
    - is_anonymous: 标记是否为匿名用户，不可为空，默认为 True。
    - session_id: 用户会话ID，不可为空，用于会话管理。
    - created_at: 用户创建时间，不可为空，默认为当前时间。
    - updated_at: 用户信息更新时间，不可为空，默认为当前时间。
    
    方法:
    - 无特殊方法，使用 Flask-Login 和 SQLAlchemy 提供的方法进行用户管理操作。
    """
    __tablename__ = 'end_users'  # 指定数据库表名为 end_users
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='end_user_pkey'),  # 指定 id 为表的主键
        db.Index('end_user_session_id_idx', 'session_id', 'type'),  # 创建 session_id 和 type 的索引
        db.Index('end_user_tenant_session_id_idx', 'tenant_id', 'session_id', 'type'),  # 创建 tenant_id, session_id 和 type 的索引
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    tenant_id = db.Column(StringUUID, nullable=False)
    app_id = db.Column(StringUUID, nullable=True)
    type = db.Column(db.String(255), nullable=False)
    external_user_id = db.Column(db.String(255), nullable=True)
    name = db.Column(db.String(255))
    is_anonymous = db.Column(db.Boolean, nullable=False, server_default=db.text('true'))
    session_id = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))


class Site(db.Model):
    """
    Site 类表示一个网站模型，用于数据库中的站点信息的映射。
    """
    __tablename__ = 'sites'  # 指定数据库表名为 sites
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='site_pkey'),  # 指定 id 为主键
        db.Index('site_app_id_idx', 'app_id'),  # 创建 app_id 的索引
        db.Index('site_code_idx', 'code', 'status')  # 创建 code 和 status 的复合索引
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    app_id = db.Column(StringUUID, nullable=False)
    title = db.Column(db.String(255), nullable=False)
    icon_type = db.Column(db.String(255), nullable=True)
    icon = db.Column(db.String(255))
    icon_background = db.Column(db.String(255))
    description = db.Column(db.Text)
    default_language = db.Column(db.String(255), nullable=False)
    chat_color_theme = db.Column(db.String(255))
    chat_color_theme_inverted = db.Column(db.Boolean, nullable=False, server_default=db.text('false'))
    copyright = db.Column(db.String(255))
    privacy_policy = db.Column(db.String(255))
    show_workflow_steps = db.Column(db.Boolean, nullable=False, server_default=db.text('true'))
    custom_disclaimer = db.Column(db.String(255), nullable=True)
    customize_domain = db.Column(db.String(255))
    customize_token_strategy = db.Column(db.String(255), nullable=False)
    prompt_public = db.Column(db.Boolean, nullable=False, server_default=db.text('false'))
    status = db.Column(db.String(255), nullable=False, server_default=db.text("'normal'::character varying"))
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    code = db.Column(db.String(255))

    @staticmethod
    def generate_code(n):
        """
        生成一个唯一的站点代码。

        :param n: 生成的代码长度。
        :return: 生成的唯一代码字符串。
        """
        while True:
            result = generate_string(n)  # 生成代码字符串
            # 检查生成的代码是否已存在，如果存在，则继续生成
            while db.session.query(Site).filter(Site.code == result).count() > 0:
                result = generate_string(n)

            return result  # 返回生成的唯一代码

    @property
    def app_base_url(self):
        """
        获取应用的基础 URL。

        :return: 应用的基础 URL 字符串。
        """
        return (
            dify_config.APP_WEB_URL if  dify_config.APP_WEB_URL else request.url_root.rstrip('/'))


class ApiToken(db.Model):
    __tablename__ = 'api_tokens'
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='api_token_pkey'),
        db.Index('api_token_app_id_type_idx', 'app_id', 'type'),
        db.Index('api_token_token_idx', 'token', 'type'),
        db.Index('api_token_tenant_idx', 'tenant_id', 'type')
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    app_id = db.Column(StringUUID, nullable=True)
    tenant_id = db.Column(StringUUID, nullable=True)
    type = db.Column(db.String(16), nullable=False)
    token = db.Column(db.String(255), nullable=False)
    last_used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))

    @staticmethod
    def generate_api_key(prefix, n):
        while True:
            result = prefix + generate_string(n)
            while db.session.query(ApiToken).filter(ApiToken.token == result).count() > 0:
                result = prefix + generate_string(n)

            return result


class UploadFile(db.Model):
    """
    上传文件模型，用于表示数据库中的上传文件信息。

    属性:
    - id: 文件唯一标识符，使用UUID生成。
    - tenant_id: 租户ID，标识文件所属的租户，不可为空。
    - storage_type: 存储类型，例如本地存储、云存储等，不可为空。
    - key: 文件在存储系统中的键，不可为空。
    - name: 文件名，不可为空。
    - size: 文件大小，以字节为单位，不可为空。
    - extension: 文件扩展名，不可为空。
    - mime_type: 文件的MIME类型，可为空。
    - created_by_role: 创建文件的用户角色，例如'account'，不可为空，默认值为'account'。
    - created_by: 创建文件的用户ID，不可为空。
    - created_at: 文件创建时间，不可为空，默认为当前时间。
    - used: 标记文件是否已被使用，不可为空，默认为false。
    - used_by: 使用文件的用户ID，可为空。
    - used_at: 文件被使用的时间，可为空。
    - hash: 文件的哈希值，用于验证文件完整性，可为空。
    """
    __tablename__ = 'upload_files'  # 指定数据库表名为upload_files
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='upload_file_pkey'),  # 设置id为PRIMARY KEY
        db.Index('upload_file_tenant_idx', 'tenant_id')  # 为tenant_id创建索引
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    tenant_id = db.Column(StringUUID, nullable=False)
    storage_type = db.Column(db.String(255), nullable=False)
    key = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    size = db.Column(db.Integer, nullable=False)
    extension = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(255), nullable=True)
    created_by_role = db.Column(db.String(255), nullable=False, server_default=db.text("'account'::character varying"))
    created_by = db.Column(StringUUID, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    used = db.Column(db.Boolean, nullable=False, server_default=db.text('false'))
    used_by = db.Column(StringUUID, nullable=True)
    used_at = db.Column(db.DateTime, nullable=True)
    hash = db.Column(db.String(255), nullable=True)


class ApiRequest(db.Model):
    """
    ApiRequest 类表示一个API请求的模型，用于数据库操作。
    
    属性:
    - id: 请求的唯一标识符，使用UUID生成。
    - tenant_id: 租户的唯一标识符，不可为空。
    - api_token_id: API令牌的唯一标识符，不可为空。
    - path: 请求的路径，不可为空。
    - request: 请求的内容，可以为空。
    - response: 响应的内容，可以为空。
    - ip: 发起请求的IP地址，不可为空。
    - created_at: 请求创建的时间，不可为空且默认为当前时间。
    
    表结构信息:
    - 表名: api_requests
    - 主键: id，约束名称为 api_request_pkey
    - 索引: 一个组合索引，包含 tenant_id 和 api_token_id，索引名称为 api_request_token_idx
    """
    
    __tablename__ = 'api_requests'  # 指定表名为 api_requests
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='api_request_pkey'),  # 定义主键约束
        db.Index('api_request_token_idx', 'tenant_id', 'api_token_id')  # 定义组合索引
    )

    id = db.Column(StringUUID, nullable=False, server_default=db.text('uuid_generate_v4()'))
    tenant_id = db.Column(StringUUID, nullable=False)
    api_token_id = db.Column(StringUUID, nullable=False)
    path = db.Column(db.String(255), nullable=False)
    request = db.Column(db.Text, nullable=True)
    response = db.Column(db.Text, nullable=True)
    ip = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))


class MessageChain(db.Model):
    """
    消息链表模型类，用于表示一系列消息的数据结构。
    
    属性:
    - id: 消息链的唯一标识符，使用UUID作为类型，不可为空，通过服务器默认函数生成。
    - message_id: 消息的唯一标识符，使用UUID作为类型，不可为空。
    - type: 消息链的类型，使用字符串表示，不可为空。
    - input: 消息的输入内容，以文本形式存储，可为空。
    - output: 消息的输出内容，以文本形式存储，可为空。
    - created_at: 消息链创建的时间，使用日期时间类型存储，不可为空，通过服务器默认当前时间函数设置。
    
    使用数据库模型的特性，定义了消息链表在数据库中的表结构和约束条件。
    """
    __tablename__ = 'message_chains'  # 指定数据库表名为message_chains
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='message_chain_pkey'),  # 定义主键约束
        db.Index('message_chain_message_id_idx', 'message_id')  # 创建message_id的索引
    )

    id = db.Column(StringUUID, nullable=False, server_default=db.text('uuid_generate_v4()'))
    message_id = db.Column(StringUUID, nullable=False)
    type = db.Column(db.String(255), nullable=False)
    input = db.Column(db.Text, nullable=True)
    output = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.current_timestamp())


class MessageAgentThought(db.Model):
    """
    消息代理思考模型，用于表示机器人在处理消息时的思考过程和相关信息。

    属性:
    - id: 唯一标识符，使用UUID生成。
    - message_id: 关联的消息ID，使用UUID。
    - message_chain_id: 消息链的ID，使用UUID，可为空。
    - position: 思考的位置，整数，不为空。
    - thought: 思考的内容，文本，可为空。
    - tool: 使用的工具，文本，可为空。
    - tool_labels_str: 工具标签的字符串表示，文本，不为空，默认为空字典。
    - tool_input: 工具输入，文本，可为空。
    - observation: 观察结果，文本，可为空。
    - tool_process_data: 工具处理数据，文本，可为空。
    - message: 消息内容，文本，可为空。
    - message_token: 消息令牌，整数，可为空。
    - message_unit_price: 消息单价，数值，不为空，默认值为0.001。
    - message_files: 消息文件，文本，可为空。
    - answer: 回答内容，文本，可为空。
    - answer_token: 回答令牌，整数，可为空。
    - answer_unit_price: 回答单价，数值，不为空，默认值为0.001。
    - tokens: 令牌数量，整数，可为空。
    - total_price: 总价格，数值，可为空。
    - currency: 货币单位，字符串，可为空。
    - latency: 延迟时间，浮点数，可为空。
    - created_by_role: 创建者角色，字符串，不为空。
    - created_by: 创建者ID，UUID，不为空。
    - created_at: 创建时间，日期时间，不为空，默认为当前时间。

    方法:
    - files: 获取消息文件列表的属性装饰器。
    - tool_labels: 获取工具标签字典的属性装饰器。
    """

    __tablename__ = 'message_agent_thoughts'
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='message_agent_thought_pkey'),
        db.Index('message_agent_thought_message_id_idx', 'message_id'),
        db.Index('message_agent_thought_message_chain_id_idx', 'message_chain_id'),
    )

    id = db.Column(StringUUID, nullable=False, server_default=db.text('uuid_generate_v4()'))
    message_id = db.Column(StringUUID, nullable=False)
    message_chain_id = db.Column(StringUUID, nullable=True)
    position = db.Column(db.Integer, nullable=False)
    thought = db.Column(db.Text, nullable=True)
    tool = db.Column(db.Text, nullable=True)
    tool_labels_str = db.Column(db.Text, nullable=False, server_default=db.text("'{}'::text"))
    tool_meta_str = db.Column(db.Text, nullable=False, server_default=db.text("'{}'::text"))
    tool_input = db.Column(db.Text, nullable=True)
    observation = db.Column(db.Text, nullable=True)
    # plugin_id = db.Column(StringUUID, nullable=True)  ## for future design
    tool_process_data = db.Column(db.Text, nullable=True)
    message = db.Column(db.Text, nullable=True)
    message_token = db.Column(db.Integer, nullable=True)
    message_unit_price = db.Column(db.Numeric, nullable=True)
    message_price_unit = db.Column(db.Numeric(10, 7), nullable=False, server_default=db.text('0.001'))
    message_files = db.Column(db.Text, nullable=True)
    answer = db.Column(db.Text, nullable=True)
    answer_token = db.Column(db.Integer, nullable=True)
    answer_unit_price = db.Column(db.Numeric, nullable=True)
    answer_price_unit = db.Column(db.Numeric(10, 7), nullable=False, server_default=db.text('0.001'))
    tokens = db.Column(db.Integer, nullable=True)
    total_price = db.Column(db.Numeric, nullable=True)
    currency = db.Column(db.String, nullable=True)
    latency = db.Column(db.Float, nullable=True)
    created_by_role = db.Column(db.String, nullable=False)
    created_by = db.Column(StringUUID, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.current_timestamp())

    @property
    def files(self) -> list:
        """
        获取消息文件列表。

        返回:
        - 文件列表，如果消息文件为空则返回空列表。
        """
        if self.message_files:
            return json.loads(self.message_files)
        else:
            return []

    @property
    def tools(self) -> list[str]:
        return self.tool.split(";") if self.tool else []

    @property
    def tool_labels(self) -> dict:
        """
        获取工具标签字典。

        返回:
        - 工具标签字典，如果工具标签字符串为空则返回空字典，解析失败也返回空字典。
        """
        try:
            if self.tool_labels_str:
                return json.loads(self.tool_labels_str)
            else:
                return {}
        except Exception as e:
            return {}

    @property
    def tool_meta(self) -> dict:
        try:
            if self.tool_meta_str:
                return json.loads(self.tool_meta_str)
            else:
                return {}
        except Exception as e:
            return {}

    @property
    def tool_inputs_dict(self) -> dict:
        tools = self.tools
        try:
            if self.tool_input:
                data = json.loads(self.tool_input)
                result = {}
                for tool in tools:
                    if tool in data:
                        result[tool] = data[tool]
                    else:
                        if len(tools) == 1:
                            result[tool] = data
                        else:
                            result[tool] = {}
                return result
            else:
                return {
                    tool: {} for tool in tools
                }
        except Exception as e:
            return {}

    @property
    def tool_outputs_dict(self) -> dict:
        tools = self.tools
        try:
            if self.observation:
                data = json.loads(self.observation)
                result = {}
                for tool in tools:
                    if tool in data:
                        result[tool] = data[tool]
                    else:
                        if len(tools) == 1:
                            result[tool] = data
                        else:
                            result[tool] = {}
                return result
            else:
                return {
                    tool: {} for tool in tools
                }
        except Exception as e:
            if self.observation:
                return dict.fromkeys(tools, self.observation)


class DatasetRetrieverResource(db.Model):
    """
    数据集检索资源模型，用于表示数据集中每个文档或片段的检索相关信息。
    
    属性:
    - id: 唯一标识符，使用UUID生成。
    - message_id: 消息ID，关联到特定的消息。
    - position: 文档或片段在数据集中的位置。
    - dataset_id: 数据集的唯一标识符。
    - dataset_name: 数据集的名称。
    - document_id: 文档的唯一标识符。
    - document_name: 文档的名称。
    - data_source_type: 数据源类型，表明数据来自何处。
    - segment_id: 片段的唯一标识符。
    - score: 检索评分，表示文档与查询的相关性。
    - content: 文档或片段的内容。
    - hit_count: 击中次数，表示文档在检索中的被击中次数。
    - word_count: 字词数，文档中的单词数量。
    - segment_position: 片段在文档中的位置。
    - index_node_hash: 索引节点哈希值，用于快速检索。
    - retriever_from: 检索来源，表明检索是如何执行的。
    - created_by: 创建者的唯一标识符。
    - created_at: 创建时间，记录行的创建时间戳。
    """
    
    __tablename__ = 'dataset_retriever_resources'  # 指定数据库表名
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='dataset_retriever_resource_pkey'),  # 设置主键约束
        db.Index('dataset_retriever_resource_message_id_idx', 'message_id'),  # 为message_id创建索引，优化查询
    )

    id = db.Column(StringUUID, nullable=False, server_default=db.text('uuid_generate_v4()'))
    message_id = db.Column(StringUUID, nullable=False)
    position = db.Column(db.Integer, nullable=False)
    dataset_id = db.Column(StringUUID, nullable=False)
    dataset_name = db.Column(db.Text, nullable=False)
    document_id = db.Column(StringUUID, nullable=False)
    document_name = db.Column(db.Text, nullable=False)
    data_source_type = db.Column(db.Text, nullable=False)
    segment_id = db.Column(StringUUID, nullable=False)
    score = db.Column(db.Float, nullable=True)
    content = db.Column(db.Text, nullable=False)
    hit_count = db.Column(db.Integer, nullable=True)
    word_count = db.Column(db.Integer, nullable=True)
    segment_position = db.Column(db.Integer, nullable=True)
    index_node_hash = db.Column(db.Text, nullable=True)
    retriever_from = db.Column(db.Text, nullable=False)
    created_by = db.Column(StringUUID, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.current_timestamp())


class Tag(db.Model):
    """
    标签模型，用于表示标签信息。

    属性:
    - id: 标签的唯一标识符，使用UUID生成。
    - tenant_id: 租户ID，标识标签所属的租户，可为空。
    - type: 标签类型，限定为['knowledge', 'app']中的值，不可为空。
    - name: 标签名称，不可为空。
    - created_by: 创建者的UUID，不可为空。
    - created_at: 标签创建的时间戳，不可为空，默认为当前时间。
    """
    __tablename__ = 'tags'  # 指定数据库表名为tags
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='tag_pkey'),  # 指定id为primary key
        db.Index('tag_type_idx', 'type'),  # 为type字段创建索引
        db.Index('tag_name_idx', 'name'),  # 为name字段创建索引
    )

    TAG_TYPE_LIST = ['knowledge', 'app']  # 定义有效的标签类型列表

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    tenant_id = db.Column(StringUUID, nullable=True)
    type = db.Column(db.String(16), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    created_by = db.Column(StringUUID, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))

class TagBinding(db.Model):
    """
    标签绑定模型，用于表示标签与目标对象的绑定关系。

    属性:
    - id: 绑定关系的唯一标识符，使用UUID生成。
    - tenant_id: 租户ID，标识绑定关系所属的租户，可为空。
    - tag_id: 标签的UUID，不可为空。
    - target_id: 目标对象的UUID，例如知识库条目或应用，不可为空。
    - created_by: 创建者的UUID，不可为空。
    - created_at: 绑定关系创建的时间戳，不可为空，默认为当前时间。
    """
    __tablename__ = 'tag_bindings'  # 指定数据库表名为tag_bindings
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='tag_binding_pkey'),  # 指定id为primary key
        db.Index('tag_bind_target_id_idx', 'target_id'),  # 为目标ID字段创建索引
        db.Index('tag_bind_tag_id_idx', 'tag_id'),  # 为标签ID字段创建索引
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    tenant_id = db.Column(StringUUID, nullable=True)
    tag_id = db.Column(StringUUID, nullable=True)
    target_id = db.Column(StringUUID, nullable=True)
    created_by = db.Column(StringUUID, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))


class TraceAppConfig(db.Model):
    __tablename__ = 'trace_app_config'
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='tracing_app_config_pkey'),
        db.Index('trace_app_config_app_id_idx', 'app_id'),
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    app_id = db.Column(StringUUID, nullable=False)
    tracing_provider = db.Column(db.String(255), nullable=True)
    tracing_config = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now())
    updated_at = db.Column(db.DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    is_active = db.Column(db.Boolean, nullable=False, server_default=db.text('true'))

    @property
    def tracing_config_dict(self):
        return self.tracing_config if self.tracing_config else {}

    @property
    def tracing_config_str(self):
        return json.dumps(self.tracing_config_dict)

    def to_dict(self):
        return {
            'id': self.id,
            'app_id': self.app_id,
            'tracing_provider': self.tracing_provider,
            'tracing_config': self.tracing_config_dict,
            "is_active": self.is_active,
            "created_at": self.created_at.__str__() if self.created_at else None,
            'updated_at': self.updated_at.__str__() if self.updated_at else None,
        }
