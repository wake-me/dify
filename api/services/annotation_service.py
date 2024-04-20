import datetime
import uuid

import pandas as pd
from flask_login import current_user
from sqlalchemy import or_
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import NotFound

from extensions.ext_database import db
from extensions.ext_redis import redis_client
from models.model import App, AppAnnotationHitHistory, AppAnnotationSetting, Message, MessageAnnotation
from services.feature_service import FeatureService
from tasks.annotation.add_annotation_to_index_task import add_annotation_to_index_task
from tasks.annotation.batch_import_annotations_task import batch_import_annotations_task
from tasks.annotation.delete_annotation_index_task import delete_annotation_index_task
from tasks.annotation.disable_annotation_reply_task import disable_annotation_reply_task
from tasks.annotation.enable_annotation_reply_task import enable_annotation_reply_task
from tasks.annotation.update_annotation_to_index_task import update_annotation_to_index_task


class AppAnnotationService:
    """
    应用注解服务类，提供了与应用注解相关的各种操作，
    包括从消息创建或更新注解、启用/禁用应用注解功能、获取指定应用下的注解列表、导出注解列表、直接插入或更新注解、删除注解、批量导入注解，
    以及获取注解命中历史记录和查询单个注解详情等功能。

    方法：
    - up_insert_app_annotation_from_message：根据消息内容创建或更新注解信息
    - enable_app_annotation：启用应用注解功能并启动异步任务
    - disable_app_annotation：禁用应用注解功能并启动异步任务
    - get_annotation_list_by_app_id：按页获取指定应用下的注解列表
    - export_annotation_list_by_app_id：导出指定应用的所有注解信息
    - insert_app_annotation_directly：直接插入新的注解信息
    - update_app_annotation_directly：直接更新已存在的注解信息
    - delete_app_annotation：删除指定的注解信息
    - batch_import_app_annotations：批量导入应用注解数据
    - get_annotation_hit_histories：获取指定注解的命中历史记录
    - get_annotation_by_id：通过ID获取单个注解信息
    - add_annotation_history：添加注解命中历史记录
    - get_app_annotation_setting_by_app_id：获取指定应用的注解设置信息
    - update_app_annotation_setting：更新指定应用的注解设置信息
    """
    
    @classmethod
    def up_insert_app_annotation_from_message(cls, args: dict, app_id: str) -> MessageAnnotation:
        """
        根据消息内容插入或更新应用注释。
        
        :param cls: 类名，用于调用数据库会话等。
        :param args: 包含注释内容和问题的字典。
        :param app_id: 应用的唯一标识符。
        :return: 返回创建或更新的MessageAnnotation对象。
        """
        # 获取应用信息
        app = db.session.query(App).filter(
            App.id == app_id,
            App.tenant_id == current_user.current_tenant_id,
            App.status == 'normal'
        ).first()

        if not app:
            raise NotFound("App not found")
        if 'message_id' in args and args['message_id']:
            message_id = str(args['message_id'])
            # 获取消息信息
            message = db.session.query(Message).filter(
                Message.id == message_id,
                Message.app_id == app.id
            ).first()

            if not message:
                raise NotFound("Message Not Exists.")

            annotation = message.annotation
            # 保存消息注释
            if annotation:
                annotation.content = args['answer']
                annotation.question = args['question']
            else:
                annotation = MessageAnnotation(
                    app_id=app.id,
                    conversation_id=message.conversation_id,
                    message_id=message.id,
                    content=args['answer'],
                    question=args['question'],
                    account_id=current_user.id
                )
        else:
            annotation = MessageAnnotation(
                app_id=app.id,
                content=args['answer'],
                question=args['question'],
                account_id=current_user.id
            )
        db.session.add(annotation)
        db.session.commit()
        # 如果启用了注释回复，则将注释添加到索引中
        annotation_setting = db.session.query(AppAnnotationSetting).filter(
            AppAnnotationSetting.app_id == app_id).first()
        if annotation_setting:
            add_annotation_to_index_task.delay(annotation.id, args['question'], current_user.current_tenant_id,
                                            app_id, annotation_setting.collection_binding_id)
        return annotation

    @classmethod
    def enable_app_annotation(cls, args: dict, app_id: str) -> dict:
        """
        启用应用注解功能。

        参数:
        - cls: 类名，用于指示函数属于哪个类，此参数在实际使用中可能未被使用。
        - args: 字典类型，包含执行任务所需的参数，例如得分阈值、嵌入提供者名称和嵌入模型名称。
        - app_id: 字符串类型，指定要启用注解功能的应用ID。

        返回值:
        - 一个字典，包含任务ID和任务状态。如果任务已经存在，则返回正在处理中的任务ID；如果任务不存在，则创建新任务并返回等待状态的任务ID。
        """
        # 构造缓存键并尝试从Redis获取缓存结果
        enable_app_annotation_key = 'enable_app_annotation_{}'.format(str(app_id))
        cache_result = redis_client.get(enable_app_annotation_key)
        if cache_result is not None:
            # 如果缓存中有结果，则表示任务已经启动，返回相关信息
            return {
                'job_id': cache_result,
                'job_status': 'processing'
            }

        # 如果缓存中无结果，则创建新任务
        job_id = str(uuid.uuid4())
        enable_app_annotation_job_key = 'enable_app_annotation_job_{}'.format(str(job_id))
        # 设置任务等待状态，并发送批量添加段落任务
        redis_client.setnx(enable_app_annotation_job_key, 'waiting')
        # 调用异步任务，传递相关参数
        enable_annotation_reply_task.delay(str(job_id), app_id, current_user.id, current_user.current_tenant_id,
                                        args['score_threshold'],
                                        args['embedding_provider_name'], args['embedding_model_name'])
        # 返回新创建任务的ID和状态
        return {
            'job_id': job_id,
            'job_status': 'waiting'
        }

    @classmethod
    def disable_app_annotation(cls, app_id: str) -> dict:
        disable_app_annotation_key = 'disable_app_annotation_{}'.format(str(app_id))
        cache_result = redis_client.get(disable_app_annotation_key)
        if cache_result is not None:
            return {
                'job_id': cache_result,
                'job_status': 'processing'
            }

        # async job
        job_id = str(uuid.uuid4())
        disable_app_annotation_job_key = 'disable_app_annotation_job_{}'.format(str(job_id))
        # send batch add segments task
        redis_client.setnx(disable_app_annotation_job_key, 'waiting')
        disable_annotation_reply_task.delay(str(job_id), app_id, current_user.current_tenant_id)
        return {
            'job_id': job_id,
            'job_status': 'waiting'
        }

    @classmethod
    def get_annotation_list_by_app_id(cls, app_id: str, page: int, limit: int, keyword: str):
        """
        根据应用ID获取注释列表，支持分页和关键字搜索。

        参数:
        - cls: 类的引用，用于调用本类的方法或属性。
        - app_id: str，要查询的应用的ID。
        - page: int，要查询的页码。
        - limit: int，每页显示的记录数。
        - keyword: str，搜索关键字，可选。

        返回值:
        - annotations.items: 查询到的注释对象列表。
        - annotations.total: 符合条件的总记录数。
        """
        # 查询应用信息
        app = db.session.query(App).filter(
            App.id == app_id,
            App.tenant_id == current_user.current_tenant_id,
            App.status == 'normal'
        ).first()

        if not app:
            raise NotFound("App not found")  # 应用不存在时抛出异常
        if keyword:
            # 带关键字的查询
            annotations = (db.session.query(MessageAnnotation)
                        .filter(MessageAnnotation.app_id == app_id)
                        .filter(
                or_(
                    MessageAnnotation.question.ilike('%{}%'.format(keyword)),
                    MessageAnnotation.content.ilike('%{}%'.format(keyword))
                )
            )
                        .order_by(MessageAnnotation.created_at.desc())
                        .paginate(page=page, per_page=limit, max_per_page=100, error_out=False))
        else:
            # 不带关键字的查询
            annotations = (db.session.query(MessageAnnotation)
                        .filter(MessageAnnotation.app_id == app_id)
                        .order_by(MessageAnnotation.created_at.desc())
                        .paginate(page=page, per_page=limit, max_per_page=100, error_out=False))
        return annotations.items, annotations.total

    @classmethod
    def export_annotation_list_by_app_id(cls, app_id: str):
        """
        根据应用ID导出注释列表
        
        参数:
        - cls: 类名，用于指示方法属于哪个类（通常由IDE自动生成，这里可忽略）
        - app_id: str，要查询注释的应用的ID
        
        返回值:
        - annotations: 查询到的注释列表
        
        抛出:
        - NotFound: 如果指定的应用不存在，则抛出异常
        """
        # 查询应用信息
        app = db.session.query(App).filter(
            App.id == app_id,
            App.tenant_id == current_user.current_tenant_id,
            App.status == 'normal'
        ).first()

        if not app:
            # 如果应用不存在，则抛出未找到异常
            raise NotFound("App not found")
        
        # 查询并返回该应用的所有注释，按创建时间降序排列
        annotations = (db.session.query(MessageAnnotation)
                    .filter(MessageAnnotation.app_id == app_id)
                    .order_by(MessageAnnotation.created_at.desc()).all())
        return annotations

    @classmethod
    def insert_app_annotation_directly(cls, args: dict, app_id: str) -> MessageAnnotation:
        """
        直接插入应用注释信息
        
        :param cls: 类名，用于调用数据库会话等
        :param args: 包含注释内容的字典，应包含'answer'和'question'键
        :param app_id: 应用的唯一标识符
        :return: 返回创建的MessageAnnotation对象
        """
        # 根据提供的app_id查询应用信息
        app = db.session.query(App).filter(
            App.id == app_id,
            App.tenant_id == current_user.current_tenant_id,
            App.status == 'normal'
        ).first()

        # 如果应用不存在，则抛出未找到异常
        if not app:
            raise NotFound("App not found")

        # 创建消息注释对象
        annotation = MessageAnnotation(
            app_id=app.id,
            content=args['answer'],
            question=args['question'],
            account_id=current_user.id
        )
        # 将注释对象添加到数据库会话并提交
        db.session.add(annotation)
        db.session.commit()

        # 检查是否启用了注释索引，如果是，则异步任务将其添加到索引中
        annotation_setting = db.session.query(AppAnnotationSetting).filter(
            AppAnnotationSetting.app_id == app_id).first()
        if annotation_setting:
            add_annotation_to_index_task.delay(annotation.id, args['question'], current_user.current_tenant_id,
                                               app_id, annotation_setting.collection_binding_id)
        return annotation

    @classmethod
    def update_app_annotation_directly(cls, args: dict, app_id: str, annotation_id: str):
        """
        直接更新应用的注释内容。

        参数:
        - args: 一个字典，包含要更新的注释的答案和问题。
        - app_id: 字符串，指定要更新注释的应用的ID。
        - annotation_id: 字符串，指定要更新的注释的ID。

        返回值:
        - 更新后的注释对象。
        
        抛出:
        - NotFound: 如果指定的应用或注释不存在。
        """

        # 查询指定的应用信息
        app = db.session.query(App).filter(
            App.id == app_id,
            App.tenant_id == current_user.current_tenant_id,
            App.status == 'normal'
        ).first()

        if not app:
            raise NotFound("App not found")

        # 查询指定的注释信息
        annotation = db.session.query(MessageAnnotation).filter(MessageAnnotation.id == annotation_id).first()

        if not annotation:
            raise NotFound("Annotation not found")

        # 更新注释的内容和问题
        annotation.content = args['answer']
        annotation.question = args['question']

        db.session.commit()
        # 如果启用了注释回复，将注释添加到索引中
        app_annotation_setting = db.session.query(AppAnnotationSetting).filter(
            AppAnnotationSetting.app_id == app_id
        ).first()

        if app_annotation_setting:
            # 异步任务，将注释添加到索引
            update_annotation_to_index_task.delay(annotation.id, annotation.question,
                                                  current_user.current_tenant_id,
                                                  app_id, app_annotation_setting.collection_binding_id)

        return annotation

    @classmethod
    def delete_app_annotation(cls, app_id: str, annotation_id: str):
        """
        删除特定应用中的注释。

        参数:
        - app_id: 要删除注释的应用的ID，类型为字符串。
        - annotation_id: 要删除的注释的ID，类型为字符串。

        异常:
        - NotFound: 如果指定的应用或注释不存在，则抛出此异常。
        """
        # 查询指定的应用信息
        app = db.session.query(App).filter(
            App.id == app_id,
            App.tenant_id == current_user.current_tenant_id,
            App.status == 'normal'
        ).first()

        if not app:
            raise NotFound("App not found")

        # 查询指定的注释信息
        annotation = db.session.query(MessageAnnotation).filter(MessageAnnotation.id == annotation_id).first()

        if not annotation:
            raise NotFound("Annotation not found")

        # 删除注释
        db.session.delete(annotation)

        # 查询并删除与该注释相关的所有命中历史记录
        annotation_hit_histories = (db.session.query(AppAnnotationHitHistory)
                                    .filter(AppAnnotationHitHistory.annotation_id == annotation_id)
                                    .all()
                                    )
        if annotation_hit_histories:
            for annotation_hit_history in annotation_hit_histories:
                db.session.delete(annotation_hit_history)

        # 提交数据库事务
        db.session.commit()

        # 如果启用了注释回复功能，则删除注释索引
        app_annotation_setting = db.session.query(AppAnnotationSetting).filter(
            AppAnnotationSetting.app_id == app_id
        ).first()

        if app_annotation_setting:
            # 异步任务，删除注释索引
            delete_annotation_index_task.delay(annotation.id, app_id,
                                            current_user.current_tenant_id,
                                            app_annotation_setting.collection_binding_id)

    @classmethod
    def batch_import_app_annotations(cls, app_id, file: FileStorage) -> dict:
        """
        批量导入应用注释

        参数:
        cls - 类名，用于调用当前类的方法或属性
        app_id - 应用的唯一标识符
        file - 包含注释数据的CSV文件

        返回值:
        返回一个字典，包含任务ID和任务状态
        {
            'job_id': 任务ID,
            'job_status': 任务状态（例如：'waiting'）
        }

        抛出:
        NotFound - 如果应用不存在
        ValueError - 如果CSV文件为空或注释数量超过订阅限制
        """

        # 获取应用信息
        app = db.session.query(App).filter(
            App.id == app_id,
            App.tenant_id == current_user.current_tenant_id,
            App.status == 'normal'
        ).first()

        if not app:
            raise NotFound("App not found")

        try:
            # 读取并处理CSV文件，跳过第一行（标题行）
            df = pd.read_csv(file)
            result = []
            for index, row in df.iterrows():
                content = {
                    'question': row[0],
                    'answer': row[1]
                }
                result.append(content)
            if len(result) == 0:
                raise ValueError("The CSV file is empty.")
            
            # 检查注释数量是否超过订阅限制
            features = FeatureService.get_features(current_user.current_tenant_id)
            if features.billing.enabled:
                annotation_quota_limit = features.annotation_quota_limit
                if annotation_quota_limit.limit < len(result) + annotation_quota_limit.size:
                    raise ValueError("The number of annotations exceeds the limit of your subscription.")
            
            # 创建异步任务
            job_id = str(uuid.uuid4())
            indexing_cache_key = 'app_annotation_batch_import_{}'.format(str(job_id))
            # 设置异步任务缓存标识，初始化为'waiting'
            redis_client.setnx(indexing_cache_key, 'waiting')
            # 调用异步任务，导入注释
            batch_import_annotations_task.delay(str(job_id), result, app_id,
                                                current_user.current_tenant_id, current_user.id)
        except Exception as e:
            return {
                'error_msg': str(e)
            }
        return {
            'job_id': job_id,
            'job_status': 'waiting'
        }

    @classmethod
    def get_annotation_hit_histories(cls, app_id: str, annotation_id: str, page, limit):
        """
        获取指定注释的命中历史记录。

        参数:
        - cls: 类的引用
        - app_id: 字符串，应用的唯一标识符
        - annotation_id: 字符串，注释的唯一标识符
        - page: 整数，要获取的页码
        - limit: 整数，每页的记录数量限制

        返回值:
        - 一个元组，包含两个元素：
        - items: 注释命中历史记录列表
        - total: 总记录数
        """
        # 查询应用信息
        app = db.session.query(App).filter(
            App.id == app_id,
            App.tenant_id == current_user.current_tenant_id,
            App.status == 'normal'
        ).first()

        if not app:
            raise NotFound("App not found")  # 应用不存在时抛出异常

        # 查询注释信息
        annotation = db.session.query(MessageAnnotation).filter(MessageAnnotation.id == annotation_id).first()

        if not annotation:
            raise NotFound("Annotation not found")  # 注释不存在时抛出异常

        # 查询注释的命中历史记录，并进行分页
        annotation_hit_histories = (db.session.query(AppAnnotationHitHistory)
                                    .filter(AppAnnotationHitHistory.app_id == app_id,
                                            AppAnnotationHitHistory.annotation_id == annotation_id,
                                            )
                                    .order_by(AppAnnotationHitHistory.created_at.desc())
                                    .paginate(page=page, per_page=limit, max_per_page=100, error_out=False))
        return annotation_hit_histories.items, annotation_hit_histories.total

    @classmethod
    def get_annotation_by_id(cls, annotation_id: str) -> MessageAnnotation | None:
        """
        通过注释ID获取注释信息
        
        :param cls: 类名，用于调用数据库会话
        :param annotation_id: 注释的唯一标识符，类型为字符串
        :return: 返回找到的MessageAnnotation对象，如果没有找到则返回None
        """
        # 从数据库中查询指定ID的注释信息
        annotation = db.session.query(MessageAnnotation).filter(MessageAnnotation.id == annotation_id).first()

        # 如果未找到对应的注释，则返回None
        if not annotation:
            return None
        return annotation

    @classmethod
    def add_annotation_history(cls, annotation_id: str, app_id: str, annotation_question: str,
                                annotation_content: str, query: str, user_id: str,
                                message_id: str, from_source: str, score: float):
        """
        向注释历史中添加一条记录。

        参数:
        - cls: 类的引用
        - annotation_id: 注释的唯一标识符，类型为字符串
        - app_id: 应用的唯一标识符，类型为字符串
        - annotation_question: 注释的问题，类型为字符串
        - annotation_content: 注释的内容，类型为字符串
        - query: 查询字符串，类型为字符串
        - user_id: 用户的唯一标识符，类型为字符串
        - message_id: 消息的唯一标识符，类型为字符串
        - from_source: 来源信息，类型为字符串
        - score: 分数，类型为浮点数

        返回值:
        无
        """
        # 增加注释的命中次数
        db.session.query(MessageAnnotation).filter(
            MessageAnnotation.id == annotation_id
        ).update(
            {MessageAnnotation.hit_count: MessageAnnotation.hit_count + 1},
            synchronize_session=False
        )

        # 创建注释命中历史对象，并加入到数据库会话中
        annotation_hit_history = AppAnnotationHitHistory(
            annotation_id=annotation_id,
            app_id=app_id,
            account_id=user_id,
            question=query,
            source=from_source,
            score=score,
            message_id=message_id,
            annotation_question=annotation_question,
            annotation_content=annotation_content
        )
        db.session.add(annotation_hit_history)
        db.session.commit()  # 提交数据库会话，使更改永久保存

    @classmethod
    def get_app_annotation_setting_by_app_id(cls, app_id: str):
        """
        根据应用ID获取应用的注解设置信息
        
        :param cls: 类名，用于指示方法属于哪个类（此部分在实际代码中可能不需要）
        :param app_id: 应用的唯一标识符
        :return: 返回一个包含注解设置的字典。如果注解设置启用，则字典包含详细设置信息；如果未启用，则只返回一个包含"enabled"键的字典。
        """
        # 从数据库中查询指定ID、租户ID和状态为正常的应用信息
        app = db.session.query(App).filter(
            App.id == app_id,
            App.tenant_id == current_user.current_tenant_id,
            App.status == 'normal'
        ).first()

        # 如果应用不存在，则抛出未找到的异常
        if not app:
            raise NotFound("App not found")

        # 查询指定应用ID的注解设置信息
        annotation_setting = db.session.query(AppAnnotationSetting).filter(
            AppAnnotationSetting.app_id == app_id).first()
        if annotation_setting:
            # 如果注解设置存在，获取并返回其详细信息
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
        # 如果注解设置不存在，返回未启用的状态信息
        return {
            "enabled": False
        }

    @classmethod
    def update_app_annotation_setting(cls, app_id: str, annotation_setting_id: str, args: dict):
        """
        更新应用的注解设置。

        参数:
        - cls: 类名，用于指示方法属于哪个类（通常由IDE自动生成）。
        - app_id: 字符串，指定要更新注解设置的应用的ID。
        - annotation_setting_id: 字符串，指定要更新的注解设置的ID。
        - args: 字典，包含要更新的注解设置的具体参数，至少包含'score_threshold'键。

        返回值:
        - 一个字典，包含更新后的注解设置的ID、启用状态、得分阈值和嵌入模型详情。
        
        抛出:
        - NotFound: 如果指定的应用或注解设置不存在。
        """

        # 从数据库获取应用信息
        app = db.session.query(App).filter(
            App.id == app_id,
            App.tenant_id == current_user.current_tenant_id,
            App.status == 'normal'
        ).first()

        if not app:
            raise NotFound("App not found")

        # 从数据库获取注解设置信息
        annotation_setting = db.session.query(AppAnnotationSetting).filter(
            AppAnnotationSetting.app_id == app_id,
            AppAnnotationSetting.id == annotation_setting_id,
        ).first()
        if not annotation_setting:
            raise NotFound("App annotation not found")
        
        # 更新注解设置的参数
        annotation_setting.score_threshold = args['score_threshold']
        annotation_setting.updated_user_id = current_user.id
        annotation_setting.updated_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        db.session.add(annotation_setting)
        db.session.commit()

        # 准备返回的信息
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
