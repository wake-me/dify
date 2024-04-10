from datetime import datetime

import pytz
from flask_login import current_user
from flask_restful import Resource, marshal_with, reqparse
from flask_restful.inputs import int_range
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload
from werkzeug.exceptions import NotFound

from controllers.console import api
from controllers.console.app import _get_app
from controllers.console.setup import setup_required
from controllers.console.wraps import account_initialization_required
from extensions.ext_database import db
from fields.conversation_fields import (
    conversation_detail_fields,
    conversation_message_detail_fields,
    conversation_pagination_fields,
    conversation_with_summary_pagination_fields,
)
from libs.helper import datetime_string
from libs.login import login_required
from models.model import Conversation, Message, MessageAnnotation


class CompletionConversationApi(Resource):
    """
    完成对话API资源类，用于处理对话完成相关的RESTful API请求。

    属性:
        - 无

    方法:
        - get: 根据提供的参数获取对话完成任务的对话列表。
    """

    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(conversation_pagination_fields)
    def get(self, app_id):
        """
        处理GET请求，根据提供的参数获取对话完成任务的对话列表。

        参数:
            - app_id(str): 应用的ID，用于标识请求的应用。

        返回:
            - conversations: 分页后的对话列表，包含对话的详细信息。
        """
        app_id = str(app_id)  # 确保app_id为字符串类型

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('keyword', type=str, location='args')
        parser.add_argument('start', type=datetime_string('%Y-%m-%d %H:%M'), location='args')
        parser.add_argument('end', type=datetime_string('%Y-%m-%d %H:%M'), location='args')
        parser.add_argument('annotation_status', type=str,
                            choices=['annotated', 'not_annotated', 'all'], default='all', location='args')
        parser.add_argument('page', type=int_range(1, 99999), default=1, location='args')
        parser.add_argument('limit', type=int_range(1, 100), default=20, location='args')
        args = parser.parse_args()

        # 获取应用信息
        app = _get_app(app_id, 'completion')

        # 构建初始查询
        query = db.select(Conversation).where(Conversation.app_id == app.id, Conversation.mode == 'completion')

        # 如果有关键词参数，则在对话内容或回答中搜索关键词
        if args['keyword']:
            query = query.join(
                Message, Message.conversation_id == Conversation.id
            ).filter(
                or_(
                    Message.query.ilike('%{}%'.format(args['keyword'])),
                    Message.answer.ilike('%{}%'.format(args['keyword']))
                )
            )

        # 获取当前用户账户信息和时区
        account = current_user
        timezone = pytz.timezone(account.timezone)
        utc_timezone = pytz.utc

        # 如果提供了开始时间参数，筛选开始时间后的对话
        if args['start']:
            start_datetime = datetime.strptime(args['start'], '%Y-%m-%d %H:%M')
            start_datetime = start_datetime.replace(second=0)

            start_datetime_timezone = timezone.localize(start_datetime)
            start_datetime_utc = start_datetime_timezone.astimezone(utc_timezone)

            query = query.where(Conversation.created_at >= start_datetime_utc)

        # 如果提供了结束时间参数，筛选结束时间前的对话
        if args['end']:
            end_datetime = datetime.strptime(args['end'], '%Y-%m-%d %H:%M')
            end_datetime = end_datetime.replace(second=59)

            end_datetime_timezone = timezone.localize(end_datetime)
            end_datetime_utc = end_datetime_timezone.astimezone(utc_timezone)

            query = query.where(Conversation.created_at < end_datetime_utc)

        # 根据注释状态筛选对话
        if args['annotation_status'] == "annotated":
            query = query.options(joinedload(Conversation.message_annotations)).join(
                MessageAnnotation, MessageAnnotation.conversation_id == Conversation.id
            )
        elif args['annotation_status'] == "not_annotated":
            query = query.outerjoin(
                MessageAnnotation, MessageAnnotation.conversation_id == Conversation.id
            ).group_by(Conversation.id).having(func.count(MessageAnnotation.id) == 0)

        # 按创建时间降序排列查询结果
        query = query.order_by(Conversation.created_at.desc())

        # 执行查询并进行分页
        conversations = db.paginate(
            query,
            page=args['page'],
            per_page=args['limit'],
            error_out=False
        )

        return conversations


class CompletionConversationDetailApi(Resource):
    """
    完成对话详情的API接口类，提供了获取对话详情和删除对话的功能。

    Attributes:
        conversation_message_detail_fields (Field): 用于定义返回结果的字段，
            通过装饰器`marshal_with`指定。
    """

    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(conversation_message_detail_fields)
    def get(self, app_id, conversation_id):
        """
        获取指定应用和对话的详细信息。

        Args:
            app_id (int): 应用的ID。
            conversation_id (int): 对话的ID。

        Returns:
            根据`conversation_message_detail_fields`定义的字段返回对话详细信息。
        """
        app_id = str(app_id)  # 将传入的app_id转换为字符串
        conversation_id = str(conversation_id)  # 将传入的conversation_id转换为字符串

        # 获取指定类型的对话
        return _get_conversation(app_id, conversation_id, 'completion')

    @setup_required
    @login_required
    @account_initialization_required
    def delete(self, app_id, conversation_id):
        """
        删除指定的对话。

        Args:
            app_id (int): 应用的ID。
            conversation_id (int): 对话的ID。

        Returns:
            删除成功返回状态码204，无内容返回。
        """
        app_id = str(app_id)  # 将传入的app_id转换为字符串
        conversation_id = str(conversation_id)  # 将传入的conversation_id转换为字符串

        # 获取指定的应用
        app = _get_app(app_id, 'chat')

        # 查询指定ID和应用下的对话
        conversation = db.session.query(Conversation) \
            .filter(Conversation.id == conversation_id, Conversation.app_id == app.id).first()

        if not conversation:
            # 如果对话不存在，抛出异常
            raise NotFound("Conversation Not Exists.")

        # 标记对话为已删除，并提交数据库事务
        conversation.is_deleted = True
        db.session.commit()

        # 返回删除成功的消息
        return {'result': 'success'}, 204


class ChatConversationApi(Resource):
    """
    聊天对话API，用于获取和管理应用中的聊天对话。

    方法:
        - get: 根据提供的参数获取对话列表。
    """

    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(conversation_with_summary_pagination_fields)
    def get(self, app_id):
        """
        获取符合条件的聊天对话列表。

        参数:
            - app_id: 应用的唯一标识符。

        返回:
            - 符合查询条件的对话列表，分页返回。
        """
        app_id = str(app_id)  # 确保app_id为字符串类型

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('keyword', type=str, location='args')
        parser.add_argument('start', type=datetime_string('%Y-%m-%d %H:%M'), location='args')
        parser.add_argument('end', type=datetime_string('%Y-%m-%d %H:%M'), location='args')
        parser.add_argument('annotation_status', type=str,
                            choices=['annotated', 'not_annotated', 'all'], default='all', location='args')
        parser.add_argument('message_count_gte', type=int_range(1, 99999), required=False, location='args')
        parser.add_argument('page', type=int_range(1, 99999), required=False, default=1, location='args')
        parser.add_argument('limit', type=int_range(1, 100), required=False, default=20, location='args')
        args = parser.parse_args()

        # 获取应用信息
        app = _get_app(app_id, 'chat')

        # 构建初始查询
        query = db.select(Conversation).where(Conversation.app_id == app.id, Conversation.mode == 'chat')

        # 如果有关键词，则在对话、消息或介绍中进行匹配
        if args['keyword']:
            query = query.join(
                Message, Message.conversation_id == Conversation.id
            ).filter(
                or_(
                    Message.query.ilike('%{}%'.format(args['keyword'])),
                    Message.answer.ilike('%{}%'.format(args['keyword'])),
                    Conversation.name.ilike('%{}%'.format(args['keyword'])),
                    Conversation.introduction.ilike('%{}%'.format(args['keyword'])),
                ),
            )

        # 获取当前用户时区并转换为UTC时区以便进行时间比较
        account = current_user
        timezone = pytz.timezone(account.timezone)
        utc_timezone = pytz.utc

        # 如果指定了开始时间，则筛选该时间之后的对话
        if args['start']:
            start_datetime = datetime.strptime(args['start'], '%Y-%m-%d %H:%M')
            start_datetime = start_datetime.replace(second=0)

            start_datetime_timezone = timezone.localize(start_datetime)
            start_datetime_utc = start_datetime_timezone.astimezone(utc_timezone)

            query = query.where(Conversation.created_at >= start_datetime_utc)

        # 如果指定了结束时间，则筛选该时间之前的对话
        if args['end']:
            end_datetime = datetime.strptime(args['end'], '%Y-%m-%d %H:%M')
            end_datetime = end_datetime.replace(second=59)

            end_datetime_timezone = timezone.localize(end_datetime)
            end_datetime_utc = end_datetime_timezone.astimezone(utc_timezone)

            query = query.where(Conversation.created_at < end_datetime_utc)

        # 根据注释状态筛选对话
        if args['annotation_status'] == "annotated":
            query = query.options(joinedload(Conversation.message_annotations)).join(
                MessageAnnotation, MessageAnnotation.conversation_id == Conversation.id
            )
        elif args['annotation_status'] == "not_annotated":
            query = query.outerjoin(
                MessageAnnotation, MessageAnnotation.conversation_id == Conversation.id
            ).group_by(Conversation.id).having(func.count(MessageAnnotation.id) == 0)

        # 如果指定了消息数量大于等于的条件，则进行筛选
        if args['message_count_gte'] and args['message_count_gte'] >= 1:
            query = (
                query.options(joinedload(Conversation.messages))
                .join(Message, Message.conversation_id == Conversation.id)
                .group_by(Conversation.id)
                .having(func.count(Message.id) >= args['message_count_gte'])
            )

        # 按创建时间降序排列
        query = query.order_by(Conversation.created_at.desc())

        # 进行分页并返回结果
        conversations = db.paginate(
            query,
            page=args['page'],
            per_page=args['limit'],
            error_out=False
        )

        return conversations


class ChatConversationDetailApi(Resource):
    """
    聊天对话详情的API接口类，提供获取对话详情和删除对话的功能。

    Attributes:
        conversation_detail_fields (Field): 用于定义返回对话详情时的字段。
    """

    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(conversation_detail_fields)
    def get(self, app_id, conversation_id):
        """
        获取指定应用和对话的详细信息。
        
        Args:
            app_id (int): 应用的ID。
            conversation_id (int): 对话的ID。
        
        Returns:
            conversation (dict): 包含指定对话详细信息的字典。
        """
        app_id = str(app_id)  # 将传入的app_id转换为字符串
        conversation_id = str(conversation_id)  # 将传入的conversation_id转换为字符串

        # 获取指定的对话信息
        return _get_conversation(app_id, conversation_id, 'chat')

    @setup_required
    @login_required
    @account_initialization_required
    def delete(self, app_id, conversation_id):
        """
        删除指定的对话记录。
        
        Args:
            app_id (int): 应用的ID。
            conversation_id (int): 对话的ID。
        
        Returns:
            result (dict): 包含删除操作结果信息的字典。
        """
        app_id = str(app_id)  # 将传入的app_id转换为字符串
        conversation_id = str(conversation_id)  # 将传入的conversation_id转换为字符串

        # 获取应用信息
        app = _get_app(app_id, 'chat')

        # 查询指定对话记录
        conversation = db.session.query(Conversation) \
            .filter(Conversation.id == conversation_id, Conversation.app_id == app.id).first()

        if not conversation:
            # 如果对话不存在，抛出异常
            raise NotFound("Conversation Not Exists.")

        # 标记对话为已删除，并提交数据库事务
        conversation.is_deleted = True
        db.session.commit()

        # 返回删除成功的消息
        return {'result': 'success'}, 204


api.add_resource(CompletionConversationApi, '/apps/<uuid:app_id>/completion-conversations')
api.add_resource(CompletionConversationDetailApi, '/apps/<uuid:app_id>/completion-conversations/<uuid:conversation_id>')
api.add_resource(ChatConversationApi, '/apps/<uuid:app_id>/chat-conversations')
api.add_resource(ChatConversationDetailApi, '/apps/<uuid:app_id>/chat-conversations/<uuid:conversation_id>')


def _get_conversation(app_id, conversation_id, mode):
    """
    获取指定的对话信息。
    
    参数:
    app_id: 应用的唯一标识符。
    conversation_id: 对话的唯一标识符。
    mode: 模式或状态，用于获取应用或对话时的额外筛选条件。
    
    返回值:
    返回查询到的Conversation对象。
    
    抛出:
    NotFound: 如果指定的对话不存在则抛出异常。
    """
    # 获取应用信息
    app = _get_app(app_id, mode)

    # 从数据库中查询指定ID和对应APP的对话信息
    conversation = db.session.query(Conversation) \
        .filter(Conversation.id == conversation_id, Conversation.app_id == app.id).first()

    if not conversation:
        # 如果对话不存在，则抛出异常
        raise NotFound("Conversation Not Exists.")

    if not conversation.read_at:
        # 如果对话未被标记为已读，则更新为已读状态，并记录当前用户ID
        conversation.read_at = datetime.utcnow()
        conversation.read_account_id = current_user.id
        db.session.commit()

    return conversation
