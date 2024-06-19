import json
import logging

from flask import abort, request
from flask_restful import Resource, marshal_with, reqparse
from werkzeug.exceptions import Forbidden, InternalServerError, NotFound

import services
from controllers.console import api
from controllers.console.app.error import ConversationCompletedError, DraftWorkflowNotExist, DraftWorkflowNotSync
from controllers.console.app.wraps import get_app_model
from controllers.console.setup import setup_required
from controllers.console.wraps import account_initialization_required
from core.app.apps.base_app_queue_manager import AppQueueManager
from core.app.entities.app_invoke_entities import InvokeFrom
from fields.workflow_fields import workflow_fields
from fields.workflow_run_fields import workflow_run_node_execution_fields
from libs import helper
from libs.helper import TimestampField, uuid_value
from libs.login import current_user, login_required
from models.model import App, AppMode
from services.app_generate_service import AppGenerateService
from services.errors.app import WorkflowHashNotEqualError
from services.workflow_service import WorkflowService

logger = logging.getLogger(__name__)


class DraftWorkflowApi(Resource):
    # 要求登录、设置和账户初始化，并确认应用模式为高级聊天或工作流模式
    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.ADVANCED_CHAT, AppMode.WORKFLOW])
    # 使用工作流字段进行结果封装
    @marshal_with(workflow_fields)
    def get(self, app_model: App):
        """
        获取草稿工作流
        
        参数:
        app_model (App): 应用模型，用于确定要获取草稿工作流的具体应用。
        
        返回值:
        返回工作流对象，如果未找到，则抛出DraftWorkflowNotExist异常。
        """
        # The role of the current user in the ta table must be admin, owner, or editor
        if not current_user.is_editor:
            raise Forbidden()
        
        # fetch draft workflow by app_model
        workflow_service = WorkflowService()
        workflow = workflow_service.get_draft_workflow(app_model=app_model)

        if not workflow:
            raise DraftWorkflowNotExist()

        # 返回工作流，未找到时由前端初始化图表
        return workflow

    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.ADVANCED_CHAT, AppMode.WORKFLOW])
    def post(self, app_model: App):
        """
        同步草稿工作流
        
        该方法用于根据接收到的请求内容（JSON或纯文本），同步更新指定应用模型的工作流草稿。
        请求需要包含工作流的结构（graph）和特征（features）。
        成功更新后，返回操作成功信息和更新时间。
        
        参数:
        - app_model: App 实例，代表需要同步工作流的应用模型。
        
        返回值:
        - 一个包含操作结果和更新时间的字典。若操作失败，则返回相应的错误信息。
        """
        # The role of the current user in the ta table must be admin, owner, or editor
        if not current_user.is_editor:
            raise Forbidden()
        
        content_type = request.headers.get('Content-Type')

        # 根据请求头部的Content-Type解析请求体
        if 'application/json' in content_type:
            parser = reqparse.RequestParser()
            parser.add_argument('graph', type=dict, required=True, nullable=False, location='json')
            parser.add_argument('features', type=dict, required=True, nullable=False, location='json')
            parser.add_argument('hash', type=str, required=False, location='json')
            args = parser.parse_args()
        elif 'text/plain' in content_type:
            try:
                # 尝试解析纯文本格式的工作流和特征数据
                data = json.loads(request.data.decode('utf-8'))
                if 'graph' not in data or 'features' not in data:
                    raise ValueError('graph or features not found in data')

                if not isinstance(data.get('graph'), dict) or not isinstance(data.get('features'), dict):
                    raise ValueError('graph or features is not a dict')

                args = {
                    'graph': data.get('graph'),
                    'features': data.get('features'),
                    'hash': data.get('hash')
                }
            except json.JSONDecodeError:
                # 若解析失败，返回无效JSON数据错误
                return {'message': 'Invalid JSON data'}, 400
        else:
            # 支持的Content-Type类型外的请求，返回不支持的媒体类型错误
            abort(415)

        # 使用工作流服务同步更新草稿工作流
        workflow_service = WorkflowService()

        try:
            workflow = workflow_service.sync_draft_workflow(
                app_model=app_model,
                graph=args.get('graph'),
                features=args.get('features'),
                unique_hash=args.get('hash'),
                account=current_user
            )
        except WorkflowHashNotEqualError:
            raise DraftWorkflowNotSync()

        # 返回操作成功信息和更新时间
        return {
            "result": "success",
            "hash": workflow.unique_hash,
            "updated_at": TimestampField().format(workflow.updated_at or workflow.created_at)
        }


class AdvancedChatDraftWorkflowRunApi(Resource):
    # 该类用于处理高级聊天草稿工作流的运行API请求
    
    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.ADVANCED_CHAT])
    def post(self, app_model: App):
        """
        执行草稿工作流
        
        该方法用于根据提供的参数执行高级聊天应用的草稿工作流。
        
        参数:
        - app_model: App 类型，代表当前被操作的应用模型
        
        返回值:
        - 返回执行工作流后的响应数据，格式化后的生成响应。
        
        异常:
        - NotFound: 对话不存在时抛出
        - ConversationCompletedError: 对话已完成时抛出
        - ValueError: 参数值无效时抛出
        - InternalServerError: 内部服务器错误时抛出
        """
        # The role of the current user in the ta table must be admin, owner, or editor
        if not current_user.is_editor:
            raise Forbidden()
        
        parser = reqparse.RequestParser()
        parser.add_argument('inputs', type=dict, location='json')
        parser.add_argument('query', type=str, required=True, location='json', default='')
        parser.add_argument('files', type=list, location='json')
        parser.add_argument('conversation_id', type=uuid_value, location='json')
        args = parser.parse_args()

        try:
            # 调用服务以生成工作流的响应
            response = AppGenerateService.generate(
                app_model=app_model,
                user=current_user,
                args=args,
                invoke_from=InvokeFrom.DEBUGGER,
                streaming=True
            )

            # 返回格式化后的生成响应
            return helper.compact_generate_response(response)
        except services.errors.conversation.ConversationNotExistsError:
            raise NotFound("Conversation Not Exists.")
        except services.errors.conversation.ConversationCompletedError:
            raise ConversationCompletedError()
        except ValueError as e:
            raise e
        except Exception as e:
            # 记录并抛出内部服务器错误
            logging.exception("internal server error.")
            raise InternalServerError()

class AdvancedChatDraftRunIterationNodeApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.ADVANCED_CHAT])
    def post(self, app_model: App, node_id: str):
        """
        Run draft workflow iteration node
        """
        # The role of the current user in the ta table must be admin, owner, or editor
        if not current_user.is_editor:
            raise Forbidden()
        
        parser = reqparse.RequestParser()
        parser.add_argument('inputs', type=dict, location='json')
        args = parser.parse_args()

        try:
            response = AppGenerateService.generate_single_iteration(
                app_model=app_model,
                user=current_user,
                node_id=node_id,
                args=args,
                streaming=True
            )

            return helper.compact_generate_response(response)
        except services.errors.conversation.ConversationNotExistsError:
            raise NotFound("Conversation Not Exists.")
        except services.errors.conversation.ConversationCompletedError:
            raise ConversationCompletedError()
        except ValueError as e:
            raise e
        except Exception as e:
            logging.exception("internal server error.")
            raise InternalServerError()

class WorkflowDraftRunIterationNodeApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.WORKFLOW])
    def post(self, app_model: App, node_id: str):
        """
        Run draft workflow iteration node
        """
        # The role of the current user in the ta table must be admin, owner, or editor
        if not current_user.is_editor:
            raise Forbidden()
        
        parser = reqparse.RequestParser()
        parser.add_argument('inputs', type=dict, location='json')
        args = parser.parse_args()

        try:
            response = AppGenerateService.generate_single_iteration(
                app_model=app_model,
                user=current_user,
                node_id=node_id,
                args=args,
                streaming=True
            )

            return helper.compact_generate_response(response)
        except services.errors.conversation.ConversationNotExistsError:
            raise NotFound("Conversation Not Exists.")
        except services.errors.conversation.ConversationCompletedError:
            raise ConversationCompletedError()
        except ValueError as e:
            raise e
        except Exception as e:
            logging.exception("internal server error.")
            raise InternalServerError()

class DraftWorkflowRunApi(Resource):
    # 草稿工作流运行API
    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.WORKFLOW])
    def post(self, app_model: App):
        """
        Run draft workflow
        """
        # The role of the current user in the ta table must be admin, owner, or editor
        if not current_user.is_editor:
            raise Forbidden()
        
        parser = reqparse.RequestParser()
        parser.add_argument('inputs', type=dict, required=True, nullable=False, location='json')
        parser.add_argument('files', type=list, required=False, location='json')
        args = parser.parse_args()

        try:
            # 调用服务生成工作流运行实例
            response = AppGenerateService.generate(
                app_model=app_model,
                user=current_user,
                args=args,
                invoke_from=InvokeFrom.DEBUGGER,
                streaming=True
            )

            # 返回处理后的生成响应
            return helper.compact_generate_response(response)
        except ValueError as e:
            # 抛出值错误异常
            raise e
        except Exception as e:
            # 记录内部服务器错误日志，并抛出内部服务器错误异常
            logging.exception("internal server error.")
            raise InternalServerError()


class WorkflowTaskStopApi(Resource):
    # 此类用于处理工作流任务停止的API请求
    
    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.ADVANCED_CHAT, AppMode.WORKFLOW])
    def post(self, app_model: App, task_id: str):
        """
        Stop workflow task
        """
        # The role of the current user in the ta table must be admin, owner, or editor
        if not current_user.is_editor:
            raise Forbidden()
        
        AppQueueManager.set_stop_flag(task_id, InvokeFrom.DEBUGGER, current_user.id)

        return {
            "result": "success"
        }

class DraftWorkflowNodeRunApi(Resource):
    # 该类用于处理草稿工作流节点的运行API请求
    
    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.ADVANCED_CHAT, AppMode.WORKFLOW])
    @marshal_with(workflow_run_node_execution_fields)
    def post(self, app_model: App, node_id: str):
        """
        Run draft workflow node
        """
        # The role of the current user in the ta table must be admin, owner, or editor
        if not current_user.is_editor:
            raise Forbidden()
        
        parser = reqparse.RequestParser()
        # 解析请求中的输入参数
        parser.add_argument('inputs', type=dict, required=True, nullable=False, location='json')
        args = parser.parse_args()

        # 使用工作流服务来执行指定的草稿工作流节点
        workflow_service = WorkflowService()
        workflow_node_execution = workflow_service.run_draft_workflow_node(
            app_model=app_model,
            node_id=node_id,
            user_inputs=args.get('inputs'),
            account=current_user
        )

        return workflow_node_execution


class PublishedWorkflowApi(Resource):
    """
    发布的工作流API资源类，提供获取和发布工作流的功能。

    方法:
    - get: 获取发布的工作流
    - post: 发布工作流
    """

    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.ADVANCED_CHAT, AppMode.WORKFLOW])
    @marshal_with(workflow_fields)
    def get(self, app_model: App):
        """
        获取发布的工作流。

        参数:
        - app_model: 应用模型，用于确定要获取工作流的应用。

        返回值:
        - 返回找到的工作流对象，如果未找到则返回None。
        """
        # The role of the current user in the ta table must be admin, owner, or editor
        if not current_user.is_editor:
            raise Forbidden()
        
        # fetch published workflow by app_model
        workflow_service = WorkflowService()
        workflow = workflow_service.get_published_workflow(app_model=app_model)

        # 返回工作流
        return workflow

    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.ADVANCED_CHAT, AppMode.WORKFLOW])
    def post(self, app_model: App):
        """
        发布工作流。

        参数:
        - app_model: 应用模型，指定要发布工作流的应用。

        返回值:
        - 包含发布结果和创建时间的字典。
        """
        # The role of the current user in the ta table must be admin, owner, or editor
        if not current_user.is_editor:
            raise Forbidden()
        
        workflow_service = WorkflowService()
        workflow = workflow_service.publish_workflow(app_model=app_model, account=current_user)

        # 返回发布成功的信息及创建时间
        return {
            "result": "success",
            "created_at": TimestampField().format(workflow.created_at)
        }


class DefaultBlockConfigsApi(Resource):
    # 该类用于处理与默认区块配置相关的API请求

    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.ADVANCED_CHAT, AppMode.WORKFLOW])
    def get(self, app_model: App):
        """
        Get default block config
        """
        # The role of the current user in the ta table must be admin, owner, or editor
        if not current_user.is_editor:
            raise Forbidden()
        
        # Get default block configs
        workflow_service = WorkflowService()
        return workflow_service.get_default_block_configs()


class DefaultBlockConfigApi(Resource):
    # 该类用于处理默认区块配置的API请求
    
    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.ADVANCED_CHAT, AppMode.WORKFLOW])
    def get(self, app_model: App, block_type: str):
        """
        获取默认区块配置
        
        该方法用于根据指定的区块类型和应用模型，获取默认的区块配置。
        
        参数:
        - app_model: App, 表示应用模型，决定了获取的区块配置适用于哪种类型的应用。
        - block_type: str, 表示区块的类型，用于指定要获取哪种类型的区块配置。
        
        返回值:
        - 返回一个包含默认区块配置的数据。
        """
        # The role of the current user in the ta table must be admin, owner, or editor
        if not current_user.is_editor:
            raise Forbidden()
        
        parser = reqparse.RequestParser()
        parser.add_argument('q', type=str, location='args')  # 解析查询参数q，用于指定过滤条件
        args = parser.parse_args()

        filters = None
        if args.get('q'):
            try:
                filters = json.loads(args.get('q'))  # 尝试将查询参数q解析为JSON格式的过滤条件
            except json.JSONDecodeError:
                raise ValueError('Invalid filters')  # 如果解析失败，则抛出无效过滤条件的错误
        
        # 通过工作流服务获取默认区块配置
        workflow_service = WorkflowService()
        return workflow_service.get_default_block_config(
            node_type=block_type,
            filters=filters
        )


class ConvertToWorkflowApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.CHAT, AppMode.COMPLETION])
    def post(self, app_model: App):
        """
        Convert basic mode of chatbot app to workflow mode
        Convert expert mode of chatbot app to workflow mode
        Convert Completion App to Workflow App
        """
        # The role of the current user in the ta table must be admin, owner, or editor
        if not current_user.is_editor:
            raise Forbidden()
        
        if request.data:
            # 解析请求中携带的参数
            parser = reqparse.RequestParser()
            parser.add_argument('name', type=str, required=False, nullable=True, location='json')
            parser.add_argument('icon', type=str, required=False, nullable=True, location='json')
            parser.add_argument('icon_background', type=str, required=False, nullable=True, location='json')
            args = parser.parse_args()
        else:
            args = {}

        # 执行转换操作
        workflow_service = WorkflowService()
        new_app_model = workflow_service.convert_to_workflow(
            app_model=app_model,
            account=current_user,
            args=args
        )

        # 返回新应用的ID
        return {
            'new_app_id': new_app_model.id,
        }


api.add_resource(DraftWorkflowApi, '/apps/<uuid:app_id>/workflows/draft')
api.add_resource(AdvancedChatDraftWorkflowRunApi, '/apps/<uuid:app_id>/advanced-chat/workflows/draft/run')
api.add_resource(DraftWorkflowRunApi, '/apps/<uuid:app_id>/workflows/draft/run')
api.add_resource(WorkflowTaskStopApi, '/apps/<uuid:app_id>/workflow-runs/tasks/<string:task_id>/stop')
api.add_resource(DraftWorkflowNodeRunApi, '/apps/<uuid:app_id>/workflows/draft/nodes/<string:node_id>/run')
api.add_resource(AdvancedChatDraftRunIterationNodeApi, '/apps/<uuid:app_id>/advanced-chat/workflows/draft/iteration/nodes/<string:node_id>/run')
api.add_resource(WorkflowDraftRunIterationNodeApi, '/apps/<uuid:app_id>/workflows/draft/iteration/nodes/<string:node_id>/run')
api.add_resource(PublishedWorkflowApi, '/apps/<uuid:app_id>/workflows/publish')
api.add_resource(DefaultBlockConfigsApi, '/apps/<uuid:app_id>/workflows/default-workflow-block-configs')
api.add_resource(DefaultBlockConfigApi, '/apps/<uuid:app_id>/workflows/default-workflow-block-configs'
                                        '/<string:block_type>')
api.add_resource(ConvertToWorkflowApi, '/apps/<uuid:app_id>/convert-to-workflow')
