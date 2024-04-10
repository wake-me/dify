from flask import request
from flask_login import current_user
from flask_restful import Resource, marshal, marshal_with, reqparse
from werkzeug.exceptions import Forbidden

from controllers.console import api
from controllers.console.app.error import NoFileUploadedError
from controllers.console.datasets.error import TooManyFilesError
from controllers.console.setup import setup_required
from controllers.console.wraps import account_initialization_required, cloud_edition_billing_resource_check
from extensions.ext_redis import redis_client
from fields.annotation_fields import (
    annotation_fields,
    annotation_hit_history_fields,
)
from libs.login import login_required
from services.annotation_service import AppAnnotationService


class AnnotationReplyActionApi(Resource):
    """
    处理与注释回复动作相关的API请求。

    要求：
    - 请求前必须进行设置
    - 用户必须登录
    - 账户必须初始化
    - 必须检查云版本和计费资源（针对注释功能）

    参数：
    - app_id: 应用的ID，类型为字符串
    - action: 操作类型，可以是'enable'（启用）或'disable'（禁用）

    返回值：
    - result: 操作结果，格式和内容依赖于具体的操作类型
    - 200: HTTP状态码，表示操作成功
    """

    @setup_required
    @login_required
    @account_initialization_required
    @cloud_edition_billing_resource_check('annotation')
    def post(self, app_id, action):
        """
        处理POST请求，根据传入的action启用或禁用应用的注释功能。

        检查当前用户在ta表中的角色是否为管理员或所有者，否则抛出Forbidden异常。

        参数:
        - app_id: 应用的ID，需要转换为字符串类型。
        - action: 操作类型，'enable' 或 'disable'。

        返回:
        - 操作结果和HTTP状态码200，如果操作不被支持，则抛出ValueError异常。
        """

        # 检查用户角色是否为管理员或所有者
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        app_id = str(app_id)
        parser = reqparse.RequestParser()
        # 解析请求体中的参数
        parser.add_argument('score_threshold', required=True, type=float, location='json')
        parser.add_argument('embedding_provider_name', required=True, type=str, location='json')
        parser.add_argument('embedding_model_name', required=True, type=str, location='json')
        args = parser.parse_args()

        # 根据action类型执行相应的操作
        if action == 'enable':
            result = AppAnnotationService.enable_app_annotation(args, app_id)
        elif action == 'disable':
            result = AppAnnotationService.disable_app_annotation(app_id)
        else:
            raise ValueError('Unsupported annotation reply action')
        return result, 200


class AppAnnotationSettingDetailApi(Resource):
    """
    应用注解设置详情接口类，用于处理应用注解设置的获取请求
    
    Attributes:
        Resource: 继承自Flask-RESTful库的Resource类，用于创建RESTful API
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    def get(self, app_id):
        """
        获取指定应用的注解设置详情
        
        Args:
            app_id (int): 应用的ID，需要转换为字符串格式进行处理
            
        Returns:
            tuple: 包含应用注解设置详情和HTTP状态码的元组
                - 应用注解设置详情: 由AppAnnotationService.get_app_annotation_setting_by_app_id方法返回的具体设置信息
                - HTTP状态码: 成功时为200
        
        Raises:
            Forbidden: 如果当前用户不是管理员或所有者，则抛出权限禁止异常
        """
        
        # 检查当前用户是否具有管理员或所有者角色，否则抛出权限异常
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        app_id = str(app_id)  # 将app_id转换为字符串格式
        result = AppAnnotationService.get_app_annotation_setting_by_app_id(app_id)  # 获取指定应用的注解设置
        return result, 200  # 返回注解设置详情和状态码


class AppAnnotationSettingUpdateApi(Resource):
    """
    用于更新应用注解设置的API接口

    方法:
    post: 更新指定应用的注解设置

    参数:
    app_id (str): 应用的ID
    annotation_setting_id (str): 注解设置的ID

    返回值:
    返回更新结果和HTTP状态码200
    """

    @setup_required
    @login_required
    @account_initialization_required
    def post(self, app_id, annotation_setting_id):
        """
        检查权限，接收并处理更新应用注解设置的请求

        权限要求:
        当前用户在ta表中的角色必须是admin或owner
        """

        # 检查用户是否有权限进行操作
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        # 将传入的app_id和annotation_setting_id转换为字符串格式
        app_id = str(app_id)
        annotation_setting_id = str(annotation_setting_id)

        # 解析请求体中的参数
        parser = reqparse.RequestParser()
        parser.add_argument('score_threshold', required=True, type=float, location='json')
        args = parser.parse_args()

        # 调用服务层方法，更新应用的注解设置
        result = AppAnnotationService.update_app_annotation_setting(app_id, annotation_setting_id, args)
        return result, 200

class AnnotationReplyActionStatusApi(Resource):
    """
    获取注释回复动作状态的API接口类

    资源类：用于处理与注释回复动作状态相关的RESTful API请求
    """
    @setup_required
    @login_required
    @account_initialization_required
    @cloud_edition_billing_resource_check('annotation')
    def get(self, app_id, job_id, action):
        """
        处理获取注释回复动作状态的GET请求

        参数:
        app_id: 应用ID，字符串类型，用于标识请求的应用
        job_id: 任务ID，字符串类型，用于标识请求的任务
        action: 动作标识，字符串类型，标识具体的注释回复动作

        返回值:
        一个包含任务ID、任务状态和错误信息（如果有）的字典，以及HTTP状态码200
        如果任务不存在或用户权限不足，则抛出相应的异常
        """
        # 检查当前用户是否为管理员或所有者
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        job_id = str(job_id)
        app_annotation_job_key = '{}_app_annotation_job_{}'.format(action, str(job_id))
        cache_result = redis_client.get(app_annotation_job_key)
        if cache_result is None:
            # 如果缓存中没有任务状态，表示任务不存在
            raise ValueError("The job is not exist.")

        job_status = cache_result.decode()
        error_msg = ''
        if job_status == 'error':
            # 如果任务状态为错误，尝试从Redis获取错误信息
            app_annotation_error_key = '{}_app_annotation_error_{}'.format(action, str(job_id))
            error_msg = redis_client.get(app_annotation_error_key).decode()

        return {
            'job_id': job_id,
            'job_status': job_status,
            'error_msg': error_msg
        }, 200


class AnnotationListApi(Resource):
    """
    提供应用注解列表的API接口
    
    Attributes:
        Resource: 继承自Flask-RESTful的Resource类，用于创建RESTful资源
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    def get(self, app_id):
        """
        获取指定应用的注解列表
        
        Args:
            app_id (int): 应用的ID，用于查询特定应用的注解列表
            
        Returns:
            response (dict): 包含注解列表、是否有更多、限制数、总数量和页码的字典，以及HTTP状态码200
            
        Raises:
            Forbidden: 如果当前用户不是管理员或所有者，则抛出权限禁止异常
        """
        
        # 检查当前用户是否具有管理员或所有者角色
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        # 从请求参数中获取页码和限制数，并提供默认值；获取搜索关键字
        page = request.args.get('page', default=1, type=int)
        limit = request.args.get('limit', default=20, type=int)
        keyword = request.args.get('keyword', default=None, type=str)

        app_id = str(app_id)
        # 调用服务层方法，根据应用ID、页码、限制数和关键字获取注解列表及总数量
        annotation_list, total = AppAnnotationService.get_annotation_list_by_app_id(app_id, page, limit, keyword)
        
        # 构建并返回响应数据
        response = {
            'data': marshal(annotation_list, annotation_fields),  # 使用字段映射注解列表
            'has_more': len(annotation_list) == limit,  # 判断是否还有更多数据
            'limit': limit,
            'total': total,
            'page': page
        }
        return response, 200


class AnnotationExportApi(Resource):
    """
    注解导出API类，用于处理应用注解的导出请求。

    Attributes:
        Resource: 指定了该类继承自Flask-RESTful库中的Resource类，以便于处理RESTful API请求。
    """

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, app_id):
        """
        处理应用注解的导出请求。

        Args:
            app_id (int): 应用的ID，用于指定要导出注解的应用。

        Returns:
            tuple: 包含注解数据的响应字典和HTTP状态码200。

        Raises:
            Forbidden: 如果当前用户不是管理员或应用所有者，则抛出权限禁止异常。
        """
        # 检查当前用户是否具有管理员或所有者角色
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        app_id = str(app_id)  # 将app_id转换为字符串格式
        # 根据应用ID导出注解列表
        annotation_list = AppAnnotationService.export_annotation_list_by_app_id(app_id)
        # 构建响应字典，包含经过格式化的注解列表
        response = {
            'data': marshal(annotation_list, annotation_fields)
        }
        return response, 200


class AnnotationCreateApi(Resource):
    """
    创建注解的API接口类
    
    此类提供了创建应用注解的功能，需要用户登录、账号初始化且是管理员或所有者角色，
    并且检查云端版本和计费资源。仅支持POST方法。
    
    参数:
    - app_id: 应用的ID，必须是字符串格式
    
    返回值:
    - 插入的注解信息
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    @cloud_edition_billing_resource_check('annotation')
    @marshal_with(annotation_fields)
    def post(self, app_id):
        """
        创建一个新的应用注解
        
        检查用户权限，确保只有管理员或所有者可以创建注解。解析请求中的注解内容并插入数据库。
        
        参数:
        - app_id: 应用的ID，将被转换为字符串格式
        
        返回:
        - 插入的注解信息
        """
        # 检查当前用户是否为管理员或所有者
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        app_id = str(app_id)  # 确保app_id是字符串格式
        parser = reqparse.RequestParser()  # 创建请求解析器
        parser.add_argument('question', required=True, type=str, location='json')  # 添加问题参数
        parser.add_argument('answer', required=True, type=str, location='json')  # 添加答案参数
        args = parser.parse_args()  # 解析请求参数
        # 直接插入应用注解到数据库
        annotation = AppAnnotationService.insert_app_annotation_directly(args, app_id)
        return annotation


class AnnotationUpdateDeleteApi(Resource):
    """
    处理应用注解的更新与删除的API接口类。
    
    方法:
    - post: 更新指定应用的注解。
    - delete: 删除指定应用的注解。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    @cloud_edition_billing_resource_check('annotation')
    @marshal_with(annotation_fields)
    def post(self, app_id, annotation_id):
        """
        更新应用的注解。
        
        参数:
        - app_id: 应用的ID，字符串类型。
        - annotation_id: 注解的ID，字符串类型。
        
        请求体参数:
        - question: 更新的问句，字符串类型。
        - answer: 更新的答案，字符串类型。
        
        返回值:
        - 更新后的注解信息。
        
        异常:
        - Forbidden: 当前用户不是管理员或所有者时引发。
        """
        
        # 检查用户角色是否为管理员或所有者
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        app_id = str(app_id)
        annotation_id = str(annotation_id)
        parser = reqparse.RequestParser()
        parser.add_argument('question', required=True, type=str, location='json')
        parser.add_argument('answer', required=True, type=str, location='json')
        args = parser.parse_args()
        # 直接更新应用的注解
        annotation = AppAnnotationService.update_app_annotation_directly(args, app_id, annotation_id)
        return annotation

    @setup_required
    @login_required
    @account_initialization_required
    def delete(self, app_id, annotation_id):
        """
        删除指定应用的注解。
        
        参数:
        - app_id: 应用的ID，字符串类型。
        - annotation_id: 注解的ID，字符串类型。
        
        返回值:
        - 删除操作的结果信息，以及HTTP状态码200。
        
        异常:
        - Forbidden: 当前用户不是管理员或所有者时引发。
        """
        
        # 检查用户角色是否为管理员或所有者
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        app_id = str(app_id)
        annotation_id = str(annotation_id)
        # 删除指定的应用注解
        AppAnnotationService.delete_app_annotation(app_id, annotation_id)
        return {'result': 'success'}, 200


class AnnotationBatchImportApi(Resource):
    """
    处理批量导入注解的API请求。

    要求：
    - 请求方法：POST
    - 路径参数：app_id（应用ID）
    - 请求体：包含一个名为'file'的文件字段，该文件为CSV格式。

    返回值：
    - 批量导入注解的结果。

    错误处理：
    - 如果用户角色不是管理员或所有者，则抛出Forbidden异常。
    - 如果请求中没有上传文件，抛出NoFileUploadedError异常。
    - 如果请求中上传了多个文件，抛出TooManyFilesError异常。
    - 如果上传的文件类型不是CSV，抛出ValueError异常。
    """

    @setup_required
    @login_required
    @account_initialization_required
    @cloud_edition_billing_resource_check('annotation')
    def post(self, app_id):
        # 检查当前用户是否具有管理员或所有者角色
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        app_id = str(app_id)
        # 从请求中获取文件
        file = request.files['file']
        # 检查是否上传了文件
        if 'file' not in request.files:
            raise NoFileUploadedError()

        # 检查是否上传了多个文件
        if len(request.files) > 1:
            raise TooManyFilesError()
        # 检查文件类型是否为CSV
        if not file.filename.endswith('.csv'):
            raise ValueError("Invalid file type. Only CSV files are allowed")
        # 批量导入应用注解
        return AppAnnotationService.batch_import_app_annotations(app_id, file)


class AnnotationBatchImportStatusApi(Resource):
    """
    用于查询批处理注释导入状态的API接口类。
    
    要求用户已登录、账号已初始化，并且在云版本中已经开通了注释功能。
    """
    @setup_required
    @login_required
    @account_initialization_required
    @cloud_edition_billing_resource_check('annotation')
    def get(self, app_id, job_id):
        """
        查询特定应用和任务的批处理注释导入状态。
        
        :param app_id: 应用ID，用于指定查询的应用。
        :param job_id: 任务ID，用于指定查询的任务。
        :return: 返回任务状态和错误信息（如果有），以及HTTP状态码200。
        """
        # 检查当前用户是否为管理员或所有者
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        job_id = str(job_id)
        # 构造缓存键并从Redis获取批处理导入状态
        indexing_cache_key = 'app_annotation_batch_import_{}'.format(str(job_id))
        cache_result = redis_client.get(indexing_cache_key)
        if cache_result is None:
            # 如果缓存中无数据，表示任务不存在
            raise ValueError("The job is not exist.")
        job_status = cache_result.decode()
        error_msg = ''
        # 如果任务状态为错误，获取错误信息
        if job_status == 'error':
            indexing_error_msg_key = 'app_annotation_batch_import_error_msg_{}'.format(str(job_id))
            error_msg = redis_client.get(indexing_error_msg_key).decode()

        # 返回任务状态和错误信息（如果有）
        return {
            'job_id': job_id,
            'job_status': job_status,
            'error_msg': error_msg
        }, 200


class AnnotationHitHistoryListApi(Resource):
    """
    提供获取注解命中历史列表的API接口
    
    Attributes:
        Resource: 继承自Flask RESTful库的Resource类，用于创建资源的抽象基类。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    def get(self, app_id, annotation_id):
        """
        获取指定应用和注解的命中历史列表。
        
        Args:
            app_id (int): 应用的ID。
            annotation_id (int): 注解的ID。
        
        Returns:
            dict: 包含注解命中历史列表的数据、是否还有更多、限制数、总数量和页码的信息。
        
        Raises:
            Forbidden: 如果当前用户不是管理员或所有者，则抛出权限禁止异常。
        """
        
        # 检查当前用户是否具有管理员或所有者角色
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        # 从请求参数中获取页码和限制数量，默认值分别为1和20
        page = request.args.get('page', default=1, type=int)
        limit = request.args.get('limit', default=20, type=int)
        app_id = str(app_id)
        annotation_id = str(annotation_id)
        
        # 调用服务层获取注解命中历史列表和总数
        annotation_hit_history_list, total = AppAnnotationService.get_annotation_hit_histories(app_id, annotation_id,
                                                                                               page, limit)
        
        # 构建并返回响应数据
        response = {
            'data': marshal(annotation_hit_history_list, annotation_hit_history_fields),
            'has_more': len(annotation_hit_history_list) == limit,
            'limit': limit,
            'total': total,
            'page': page
        }
        return response

api.add_resource(AnnotationReplyActionApi, '/apps/<uuid:app_id>/annotation-reply/<string:action>')
api.add_resource(AnnotationReplyActionStatusApi,
                 '/apps/<uuid:app_id>/annotation-reply/<string:action>/status/<uuid:job_id>')
api.add_resource(AnnotationListApi, '/apps/<uuid:app_id>/annotations')
api.add_resource(AnnotationExportApi, '/apps/<uuid:app_id>/annotations/export')
api.add_resource(AnnotationUpdateDeleteApi, '/apps/<uuid:app_id>/annotations/<uuid:annotation_id>')
api.add_resource(AnnotationBatchImportApi, '/apps/<uuid:app_id>/annotations/batch-import')
api.add_resource(AnnotationBatchImportStatusApi, '/apps/<uuid:app_id>/annotations/batch-import-status/<uuid:job_id>')
api.add_resource(AnnotationHitHistoryListApi, '/apps/<uuid:app_id>/annotations/<uuid:annotation_id>/hit-histories')
api.add_resource(AppAnnotationSettingDetailApi, '/apps/<uuid:app_id>/annotation-setting')
api.add_resource(AppAnnotationSettingUpdateApi, '/apps/<uuid:app_id>/annotation-settings/<uuid:annotation_setting_id>')
