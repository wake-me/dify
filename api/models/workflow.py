import json
from collections.abc import Mapping, Sequence
from enum import Enum
from typing import Any, Optional, Union

from sqlalchemy import func
from sqlalchemy.orm import Mapped

import contexts
from constants import HIDDEN_VALUE
from core.app.segments import SecretVariable, Variable, factory
from core.helper import encrypter
from extensions.ext_database import db
from libs import helper

from .account import Account
from .types import StringUUID


class CreatedByRole(Enum):
    """
    Created By Role 枚举类，定义了创建者角色的枚举值。
    """
    ACCOUNT = 'account'  # 代表账户创建
    END_USER = 'end_user'  # 代表最终用户创建

    @classmethod
    def value_of(cls, value: str) -> 'CreatedByRole':
        """
        根据给定的字符串值获取对应的 CreatedByRole 枚举实例。

        :param value: 字符串值，期望是 ACCOUNT 或 END_USER 中的一个。
        :return: 返回与给定值匹配的 CreatedByRole 枚举实例。
        """
        for mode in cls:
            if mode.value == value:
                return mode
        # 如果给定的值不在枚举定义范围内，则抛出异常
        raise ValueError(f'invalid created by role value {value}')


class WorkflowType(Enum):
    """
    工作流类型枚举
    """
    WORKFLOW = 'workflow'  # 表示工作流类型
    CHAT = 'chat'  # 表示聊天类型

    @classmethod
    def value_of(cls, value: str) -> 'WorkflowType':
        """
        根据给定的值获取工作流类型。

        :param value: 工作流类型的值
        :return: 对应的工作流类型枚举实例
        """
        for mode in cls:
            if mode.value == value:
                return mode
        raise ValueError(f'invalid workflow type value {value}')

    @classmethod
    def from_app_mode(cls, app_mode: Union[str, 'AppMode']) -> 'WorkflowType':
        """
        根据应用模式获取对应的工作流类型。

        :param app_mode: 应用模式，可以是字符串或AppMode枚举实例
        :return: 对应的工作流类型枚举实例
        """
        from models.model import AppMode  # 导入AppMode枚举
        app_mode = app_mode if isinstance(app_mode, AppMode) else AppMode.value_of(app_mode)  # 确保app_mode是AppMode实例
        return cls.WORKFLOW if app_mode == AppMode.WORKFLOW else cls.CHAT  # 根据应用模式返回对应的工作流类型

class Workflow(db.Model):
    """
    Workflow 类，用于Workflow App和Chat App workflow模式。

    属性:
    - id (uuid): 工作流ID，主键。
    - tenant_id (uuid): 工作空间ID。
    - app_id (uuid): 应用ID。
    - type (string): 工作流类型。

        'workflow' 代表Workflow App。

        'chat' 代表Chat App workflow模式。

    - version (string): 版本号。

        'draft' 代表草稿版本（每个应用仅有一个），其他为版本号（冗余）。

    - graph (text): 工作流画布配置（JSON）。

        包括Node、Edge等整个画布配置的JSON。
        - nodes (array[object]): 节点列表，参见 Node Schema。
        - edges (array[object]): 边列表，参见 Edge Schema。

    - created_by (uuid): 创建者ID。
    - created_at (timestamp): 创建时间。
    - updated_by (uuid): `可选` 最后更新者ID。
    - updated_at (timestamp): `可选` 最后更新时间。
    """

    __tablename__ = 'workflows'
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='workflow_pkey'),
        db.Index('workflow_version_idx', 'tenant_id', 'app_id', 'version'),
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    tenant_id = db.Column(StringUUID, nullable=False)
    app_id = db.Column(StringUUID, nullable=False)
    type = db.Column(db.String(255), nullable=False)
    version = db.Column(db.String(255), nullable=False)
    graph = db.Column(db.Text)
    features = db.Column(db.Text)
    created_by = db.Column(StringUUID, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    updated_by = db.Column(StringUUID)
    updated_at = db.Column(db.DateTime)
    _environment_variables = db.Column('environment_variables', db.Text, nullable=False, server_default='{}')
    _conversation_variables = db.Column('conversation_variables', db.Text, nullable=False, server_default='{}')

    @property
    def created_by_account(self):
        return db.session.get(Account, self.created_by)

    @property
    def updated_by_account(self):
        return db.session.get(Account, self.updated_by) if self.updated_by else None

    @property
    def graph_dict(self) -> Mapping[str, Any]:
        return json.loads(self.graph) if self.graph else {}

    @property
    def features_dict(self) -> Mapping[str, Any]:
        return json.loads(self.features) if self.features else {}

    def user_input_form(self, to_old_structure: bool = False) -> list:
        """
        根据工作流图生成用户输入表单。

        参数:
        - to_old_structure (bool): 是否将表单结构转换为旧版格式，默认为False。

        返回:
        - list: 用户输入表单的结构，可能是旧版或新版格式。
        """
        # 从graph中获取开始节点
        if not self.graph:
            return []

        graph_dict = self.graph_dict
        if 'nodes' not in graph_dict:
            return []

        start_node = next((node for node in graph_dict['nodes'] if node['data']['type'] == 'start'), None)
        if not start_node:
            return []

        # 从开始节点获取user_input_form
        variables = start_node.get('data', {}).get('variables', [])

        if to_old_structure:
            old_structure_variables = []
            for variable in variables:
                old_structure_variables.append({
                    variable['type']: variable
                })

            return old_structure_variables

        return variables

    @property
    def unique_hash(self) -> str:
        """
        Get hash of workflow.

        :return: hash
        """
        entity = {
            'graph': self.graph_dict,
            'features': self.features_dict
        }

        return helper.generate_text_hash(json.dumps(entity, sort_keys=True))

    @property
    def tool_published(self) -> bool:
        from models.tools import WorkflowToolProvider
        return db.session.query(WorkflowToolProvider).filter(
            WorkflowToolProvider.app_id == self.app_id
        ).first() is not None

    @property
    def environment_variables(self) -> Sequence[Variable]:
        # TODO: find some way to init `self._environment_variables` when instance created.
        if self._environment_variables is None:
            self._environment_variables = '{}'

        tenant_id = contexts.tenant_id.get()

        environment_variables_dict: dict[str, Any] = json.loads(self._environment_variables)
        results = [factory.build_variable_from_mapping(v) for v in environment_variables_dict.values()]

        # decrypt secret variables value
        decrypt_func = (
            lambda var: var.model_copy(
                update={'value': encrypter.decrypt_token(tenant_id=tenant_id, token=var.value)}
            )
            if isinstance(var, SecretVariable)
            else var
        )
        results = list(map(decrypt_func, results))
        return results

    @environment_variables.setter
    def environment_variables(self, value: Sequence[Variable]):
        tenant_id = contexts.tenant_id.get()

        value = list(value)
        if any(var for var in value if not var.id):
            raise ValueError('environment variable require a unique id')

        # Compare inputs and origin variables, if the value is HIDDEN_VALUE, use the origin variable value (only update `name`).
        origin_variables_dictionary = {var.id: var for var in self.environment_variables}
        for i, variable in enumerate(value):
            if variable.id in origin_variables_dictionary and variable.value == HIDDEN_VALUE:
                value[i] = origin_variables_dictionary[variable.id].model_copy(update={'name': variable.name})

        # encrypt secret variables value
        encrypt_func = (
            lambda var: var.model_copy(
                update={'value': encrypter.encrypt_token(tenant_id=tenant_id, token=var.value)}
            )
            if isinstance(var, SecretVariable)
            else var
        )
        encrypted_vars = list(map(encrypt_func, value))
        environment_variables_json = json.dumps(
            {var.name: var.model_dump() for var in encrypted_vars},
            ensure_ascii=False,
        )
        self._environment_variables = environment_variables_json

    def to_dict(self, *, include_secret: bool = False) -> Mapping[str, Any]:
        environment_variables = list(self.environment_variables)
        environment_variables = [
            v if not isinstance(v, SecretVariable) or include_secret else v.model_copy(update={'value': ''})
            for v in environment_variables
        ]

        result = {
            'graph': self.graph_dict,
            'features': self.features_dict,
            'environment_variables': [var.model_dump(mode='json') for var in environment_variables],
            'conversation_variables': [var.model_dump(mode='json') for var in self.conversation_variables],
        }
        return result

    @property
    def conversation_variables(self) -> Sequence[Variable]:
        # TODO: find some way to init `self._conversation_variables` when instance created.
        if self._conversation_variables is None:
            self._conversation_variables = '{}'

        variables_dict: dict[str, Any] = json.loads(self._conversation_variables)
        results = [factory.build_variable_from_mapping(v) for v in variables_dict.values()]
        return results

    @conversation_variables.setter
    def conversation_variables(self, value: Sequence[Variable]) -> None:
        self._conversation_variables = json.dumps(
            {var.name: var.model_dump() for var in value},
            ensure_ascii=False,
        )


class WorkflowRunTriggeredFrom(Enum):
    """
    Workflow Run Triggered From 枚举类
    用于定义工作流运行的触发来源
    """
    DEBUGGING = 'debugging'  # 来源于调试
    APP_RUN = 'app-run'  # 来源于应用运行

    @classmethod
    def value_of(cls, value: str) -> 'WorkflowRunTriggeredFrom':
        """
        根据给定的值获取枚举实例。

        :param value: 指定的触发来源字符串
        :return: 对应的枚举实例
        """
        for mode in cls:
            if mode.value == value:
                return mode
        # 如果给定的值不在枚举范围内，则抛出异常
        raise ValueError(f'invalid workflow run triggered from value {value}')

class WorkflowRunStatus(Enum):
    """
    工作流运行状态枚举

    描述工作流可能的运行状态，包括运行中、成功、失败和已停止。
    """
    RUNNING = 'running'    # 工作流正在运行
    SUCCEEDED = 'succeeded'  # 工作流运行成功
    FAILED = 'failed'      # 工作流运行失败
    STOPPED = 'stopped'    # 工作流已停止

    @classmethod
    def value_of(cls, value: str) -> 'WorkflowRunStatus':
        """
        根据给定的字符串值获取相应的枚举实例。

        :param value: 字符串值，代表想要获取的枚举实例的状态值。
        :return: 返回与给定状态值相匹配的枚举实例。
        """
        for mode in cls:
            if mode.value == value:
                return mode
        # 如果给定的状态值在枚举中不存在，则抛出异常
        raise ValueError(f'invalid workflow run status value {value}')

class WorkflowRun(db.Model):
    """
    工作流执行

    属性:
    - id (uuid) 执行ID
    - tenant_id (uuid) 工作空间ID
    - app_id (uuid) 应用ID
    - sequence_number (int) 自增序列号，从1开始，在应用内部递增
    - workflow_id (uuid) 工作流ID
    - type (string) 工作流类型
    - triggered_from (string) 触发源

        `debugging`：画布调试触发

        `app-run`：（已发布）应用执行触发

    - version (string) 版本
    - graph (text) 工作流画布配置（JSON格式）
    - inputs (text) 输入参数
    - status (string) 执行状态，`running` / `succeeded` / `failed` / `stopped`
    - outputs (text) `可选` 输出内容
    - error (string) `可选` 错误原因
    - elapsed_time (float) `可选` 耗时（秒）
    - total_tokens (int) `可选` 总共使用的令牌数
    - total_steps (int) 总步骤数（冗余，默认为0）
    - created_by_role (string) 创建者角色

        - `account`：控制台账户

        - `end_user`：终端用户

    - created_by (uuid) 创建者ID
    - created_at (timestamp) 创建时间
    - finished_at (timestamp) 完成时间
    """

    __tablename__ = 'workflow_runs'
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='workflow_run_pkey'),
        db.Index('workflow_run_triggerd_from_idx', 'tenant_id', 'app_id', 'triggered_from'),
        db.Index('workflow_run_tenant_app_sequence_idx', 'tenant_id', 'app_id', 'sequence_number'),
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    tenant_id = db.Column(StringUUID, nullable=False)
    app_id = db.Column(StringUUID, nullable=False)
    sequence_number = db.Column(db.Integer, nullable=False)
    workflow_id = db.Column(StringUUID, nullable=False)
    type = db.Column(db.String(255), nullable=False)
    triggered_from = db.Column(db.String(255), nullable=False)
    version = db.Column(db.String(255), nullable=False)
    graph = db.Column(db.Text)
    inputs = db.Column(db.Text)
    status = db.Column(db.String(255), nullable=False)
    outputs = db.Column(db.Text)
    error = db.Column(db.Text)
    elapsed_time = db.Column(db.Float, nullable=False, server_default=db.text('0'))
    total_tokens = db.Column(db.Integer, nullable=False, server_default=db.text('0'))
    total_steps = db.Column(db.Integer, server_default=db.text('0'))
    created_by_role = db.Column(db.String(255), nullable=False)
    created_by = db.Column(StringUUID, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    finished_at = db.Column(db.DateTime)

    @property
    def created_by_account(self):
        """
        获取创建者是账户的情况
        返回值:
            如果创建者角色为账户，则返回Account对象；否则返回None。
        """
        created_by_role = CreatedByRole.value_of(self.created_by_role)
        return db.session.get(Account, self.created_by) \
            if created_by_role == CreatedByRole.ACCOUNT else None

    @property
    def created_by_end_user(self):
        """
        获取创建者是终端用户的情况
        返回值:
            如果创建者角色为终端用户，则返回EndUser对象；否则返回None。
        """
        from models.model import EndUser
        created_by_role = CreatedByRole.value_of(self.created_by_role)
        return db.session.get(EndUser, self.created_by) \
            if created_by_role == CreatedByRole.END_USER else None

    @property
    def graph_dict(self):
        """
        将graph字段转换为字典格式
        返回值:
            如果graph字段存在，则返回其JSON解析后的字典；否则返回None。
        """
        return json.loads(self.graph) if self.graph else None

    @property
    def inputs_dict(self):
        """
        将inputs字段转换为字典格式
        返回值:
            如果inputs字段存在，则返回其JSON解析后的字典；否则返回None。
        """
        return json.loads(self.inputs) if self.inputs else None

    @property
    def outputs_dict(self):
        """
        将outputs字段转换为字典格式
        返回值:
            如果outputs字段存在，则返回其JSON解析后的字典；否则返回None。
        """
        return json.loads(self.outputs) if self.outputs else None

    @property
    def message(self) -> Optional['Message']:
        """
        获取与该工作流执行相关联的消息
        返回值:
            返回与之关联的第一条Message对象，如果没有则返回None。
        """
        from models.model import Message
        return db.session.query(Message).filter(
            Message.app_id == self.app_id,
            Message.workflow_run_id == self.id
        ).first()

    @property
    def workflow(self):
        """
        获取与该工作流执行相关联的工作流对象
        返回值:
            返回与该工作流执行相关联的工作流对象，如果没有找到则返回None。
        """
        return db.session.query(Workflow).filter(Workflow.id == self.workflow_id).first()

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'app_id': self.app_id,
            'sequence_number': self.sequence_number,
            'workflow_id': self.workflow_id,
            'type': self.type,
            'triggered_from': self.triggered_from,
            'version': self.version,
            'graph': self.graph_dict,
            'inputs': self.inputs_dict,
            'status': self.status,
            'outputs': self.outputs_dict,
            'error': self.error,
            'elapsed_time': self.elapsed_time,
            'total_tokens': self.total_tokens,
            'total_steps': self.total_steps,
            'created_by_role': self.created_by_role,
            'created_by': self.created_by,
            'created_at': self.created_at,
            'finished_at': self.finished_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'WorkflowRun':
        return cls(
            id=data.get('id'),
            tenant_id=data.get('tenant_id'),
            app_id=data.get('app_id'),
            sequence_number=data.get('sequence_number'),
            workflow_id=data.get('workflow_id'),
            type=data.get('type'),
            triggered_from=data.get('triggered_from'),
            version=data.get('version'),
            graph=json.dumps(data.get('graph')),
            inputs=json.dumps(data.get('inputs')),
            status=data.get('status'),
            outputs=json.dumps(data.get('outputs')),
            error=data.get('error'),
            elapsed_time=data.get('elapsed_time'),
            total_tokens=data.get('total_tokens'),
            total_steps=data.get('total_steps'),
            created_by_role=data.get('created_by_role'),
            created_by=data.get('created_by'),
            created_at=data.get('created_at'),
            finished_at=data.get('finished_at'),
        )


class WorkflowNodeExecutionTriggeredFrom(Enum):
    """
    工作流节点执行触发来源枚举
    """
    SINGLE_STEP = 'single-step'  # 由单步触发
    WORKFLOW_RUN = 'workflow-run'  # 由工作流运行触发

    @classmethod
    def value_of(cls, value: str) -> 'WorkflowNodeExecutionTriggeredFrom':
        """
        根据给定的值获取对应的枚举成员。

        :param value: 枚举成员的值
        :return: 对应的枚举成员
        """
        for mode in cls:
            if mode.value == value:
                return mode
        # 如果给定的值不存在于枚举中，则抛出异常
        raise ValueError(f'invalid workflow node execution triggered from value {value}')

class WorkflowNodeExecutionStatus(Enum):
    """
    工作流节点执行状态枚举
    """
    RUNNING = 'running'    # 执行中
    SUCCEEDED = 'succeeded'    # 成功
    FAILED = 'failed'      # 失败

    @classmethod
    def value_of(cls, value: str) -> 'WorkflowNodeExecutionStatus':
        """
        根据给定的值获取工作流节点执行状态。

        :param value: 状态值
        :return: 对应的工作流节点执行状态枚举实例
        """
        for mode in cls:
            if mode.value == value:
                return mode
        # 如果给定的值不在枚举中，则抛出异常
        raise ValueError(f'invalid workflow node execution status value {value}')

class WorkflowNodeExecution(db.Model):
    """
    工作流节点执行模型

    - id (uuid) 执行ID
    - tenant_id (uuid) 工作空间ID
    - app_id (uuid) 应用ID
    - workflow_id (uuid) 工作流ID
    - triggered_from (string) 触发源

        `single-step` 表示单步调试

        `workflow-run` 表示工作流执行（调试/用户执行）

    - workflow_run_id (uuid) `可选` 工作流运行ID

        单步调试时为Null。

    - index (int) 执行序列号，用于显示跟踪节点顺序
    - predecessor_node_id (string) `可选` 前驱节点ID，用于显示执行路径
    - node_id (string) 节点ID
    - node_type (string) 节点类型，如 `start`
    - title (string) 节点标题
    - inputs (json) 所有前驱节点变量内容，用于节点使用
    - process_data (json) 节点处理数据
    - outputs (json) `可选` 节点输出变量
    - status (string) 执行状态，`running` / `succeeded` / `failed`
    - error (string) `可选` 错误原因
    - elapsed_time (float) `可选` 消耗时间（秒）
    - execution_metadata (text) 元数据

        - total_tokens (int) `可选` 总共使用的令牌数

        - total_price (decimal) `可选` 总成本

        - currency (string) `可选` 货币类型，如 USD / RMB

    - created_at (timestamp) 运行时间
    - created_by_role (string) 创建者角色

        - `account` 控制台账户

        - `end_user` 终端用户

    - created_by (uuid) 运行者ID
    - finished_at (timestamp) 结束时间
    """

    __tablename__ = 'workflow_node_executions'
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='workflow_node_execution_pkey'),
        db.Index('workflow_node_execution_workflow_run_idx', 'tenant_id', 'app_id', 'workflow_id',
                 'triggered_from', 'workflow_run_id'),
        db.Index('workflow_node_execution_node_run_idx', 'tenant_id', 'app_id', 'workflow_id',
                 'triggered_from', 'node_id'),
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    tenant_id = db.Column(StringUUID, nullable=False)
    app_id = db.Column(StringUUID, nullable=False)
    workflow_id = db.Column(StringUUID, nullable=False)
    triggered_from = db.Column(db.String(255), nullable=False)
    workflow_run_id = db.Column(StringUUID)
    index = db.Column(db.Integer, nullable=False)
    predecessor_node_id = db.Column(db.String(255))
    node_id = db.Column(db.String(255), nullable=False)
    node_type = db.Column(db.String(255), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    inputs = db.Column(db.Text)
    process_data = db.Column(db.Text)
    outputs = db.Column(db.Text)
    status = db.Column(db.String(255), nullable=False)
    error = db.Column(db.Text)
    elapsed_time = db.Column(db.Float, nullable=False, server_default=db.text('0'))
    execution_metadata = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    created_by_role = db.Column(db.String(255), nullable=False)
    created_by = db.Column(StringUUID, nullable=False)
    finished_at = db.Column(db.DateTime)

    @property
    def created_by_account(self):
        """
        获取创建者为账户的信息
        :return: 账户信息或者None
        """
        created_by_role = CreatedByRole.value_of(self.created_by_role)
        return db.session.get(Account, self.created_by) \
            if created_by_role == CreatedByRole.ACCOUNT else None

    @property
    def created_by_end_user(self):
        """
        获取创建者为终端用户的信息
        :return: 终端用户信息或者None
        """
        from models.model import EndUser
        created_by_role = CreatedByRole.value_of(self.created_by_role)
        return db.session.get(EndUser, self.created_by) \
            if created_by_role == CreatedByRole.END_USER else None

    @property
    def inputs_dict(self):
        """
        将输入数据转换为字典格式
        :return: 输入数据的字典表示或者None
        """
        return json.loads(self.inputs) if self.inputs else None

    @property
    def outputs_dict(self):
        """
        将输出数据转换为字典格式
        :return: 输出数据的字典表示或者None
        """
        return json.loads(self.outputs) if self.outputs else None

    @property
    def process_data_dict(self):
        """
        将处理数据转换为字典格式
        :return: 处理数据的字典表示或者None
        """
        return json.loads(self.process_data) if self.process_data else None

    @property
    def execution_metadata_dict(self):
        """
        将执行元数据转换为字典格式
        :return: 执行元数据的字典表示或者None
        """
        return json.loads(self.execution_metadata) if self.execution_metadata else None

    @property
    def extras(self):
        from core.tools.tool_manager import ToolManager
        extras = {}
        if self.execution_metadata_dict:
            from core.workflow.entities.node_entities import NodeType
            if self.node_type == NodeType.TOOL.value and 'tool_info' in self.execution_metadata_dict:
                tool_info = self.execution_metadata_dict['tool_info']
                extras['icon'] = ToolManager.get_tool_icon(
                    tenant_id=self.tenant_id,
                    provider_type=tool_info['provider_type'],
                    provider_id=tool_info['provider_id']
                )

        return extras


class WorkflowAppLogCreatedFrom(Enum):
    """
    Workflow App Log Created From 枚举类
    用于定义工作流应用日志的来源
    """

    SERVICE_API = 'service-api'  # 来自服务API
    WEB_APP = 'web-app'  # 来自Web应用
    INSTALLED_APP = 'installed-app'  # 来自安装应用

    @classmethod
    def value_of(cls, value: str) -> 'WorkflowAppLogCreatedFrom':
        """
        根据给定的值获取枚举实例。

        :param value: 指定的来源值
        :return: 对应的枚举实例
        """
        for mode in cls:
            if mode.value == value:
                return mode
        # 如果给定的值不在枚举中，则抛出异常
        raise ValueError(f'invalid workflow app log created from value {value}')

class WorkflowAppLog(db.Model):
    """
    Workflow App执行日志，不包括workflow调试记录。

    属性:
    
    - id (uuid) 运行ID
    - tenant_id (uuid) 工作空间ID
    - app_id (uuid) App ID
    - workflow_id (uuid) 关联的Workflow ID
    - workflow_run_id (uuid) 关联的Workflow Run ID
    - created_from (string) 创建来源

        `service-api` App执行OpenAPI
        
        `web-app` WebApp
        
        `installed-app` 安装的App

    - created_by_role (string) 创建者角色

        - `account` 控制台账户

        - `end_user` 终端用户

    - created_by (uuid) 创建者ID，根据created_by_role依赖于用户表
    - created_at (timestamp) 创建时间
    """

    __tablename__ = 'workflow_app_logs'
    __table_args__ = (
        db.PrimaryKeyConstraint('id', name='workflow_app_log_pkey'),
        db.Index('workflow_app_log_app_idx', 'tenant_id', 'app_id'),
    )

    id = db.Column(StringUUID, server_default=db.text('uuid_generate_v4()'))
    tenant_id = db.Column(StringUUID, nullable=False)
    app_id = db.Column(StringUUID, nullable=False)
    workflow_id = db.Column(StringUUID, nullable=False)
    workflow_run_id = db.Column(StringUUID, nullable=False)
    created_from = db.Column(db.String(255), nullable=False)
    created_by_role = db.Column(db.String(255), nullable=False)
    created_by = db.Column(StringUUID, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text('CURRENT_TIMESTAMP(0)'))

    @property
    def workflow_run(self):
        return db.session.get(WorkflowRun, self.workflow_run_id)

    @property
    def created_by_account(self):
        """
        根据创建者角色查询创建者账户。
        
        返回值:
        - 如果创建者是账户，则返回Account对象；否则返回None。
        """
        created_by_role = CreatedByRole.value_of(self.created_by_role)
        return db.session.get(Account, self.created_by) \
            if created_by_role == CreatedByRole.ACCOUNT else None

    @property
    def created_by_end_user(self):
        """
        根据创建者角色查询创建者终端用户。
        
        返回值:
        - 如果创建者是终端用户，则返回EndUser对象；否则返回None。
        """
        from models.model import EndUser
        created_by_role = CreatedByRole.value_of(self.created_by_role)
        return db.session.get(EndUser, self.created_by) \
            if created_by_role == CreatedByRole.END_USER else None


class ConversationVariable(db.Model):
    __tablename__ = 'workflow__conversation_variables'

    id: Mapped[str] = db.Column(StringUUID, primary_key=True)
    conversation_id: Mapped[str] = db.Column(StringUUID, nullable=False, primary_key=True)
    app_id: Mapped[str] = db.Column(StringUUID, nullable=False, index=True)
    data = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, index=True, server_default=db.text('CURRENT_TIMESTAMP(0)'))
    updated_at = db.Column(db.DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    def __init__(self, *, id: str, app_id: str, conversation_id: str, data: str) -> None:
        self.id = id
        self.app_id = app_id
        self.conversation_id = conversation_id
        self.data = data

    @classmethod
    def from_variable(cls, *, app_id: str, conversation_id: str, variable: Variable) -> 'ConversationVariable':
        obj = cls(
            id=variable.id,
            app_id=app_id,
            conversation_id=conversation_id,
            data=variable.model_dump_json(),
        )
        return obj

    def to_variable(self) -> Variable:
        mapping = json.loads(self.data)
        return factory.build_variable_from_mapping(mapping)
