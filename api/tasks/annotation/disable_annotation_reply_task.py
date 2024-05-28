import logging
import time

import click
from celery import shared_task
from werkzeug.exceptions import NotFound

from core.rag.datasource.vdb.vector_factory import Vector
from extensions.ext_database import db
from extensions.ext_redis import redis_client
from models.dataset import Dataset
from models.model import App, AppAnnotationSetting, MessageAnnotation


@shared_task(queue='dataset')
def disable_annotation_reply_task(job_id: str, app_id: str, tenant_id: str):
    """
    异步禁用注释回复任务
    :param job_id: 任务ID，字符串类型
    :param app_id: 应用ID，字符串类型
    :param tenant_id: 租户ID，字符串类型
    """

    # 开始删除应用注释索引的日志记录
    logging.info(click.style('Start delete app annotations index: {}'.format(app_id), fg='green'))
    start_at = time.perf_counter()

    # 查询应用信息
    app = db.session.query(App).filter(
        App.id == app_id,
        App.tenant_id == tenant_id,
        App.status == 'normal'
    ).first()
    annotations_count = db.session.query(MessageAnnotation).filter(MessageAnnotation.app_id == app_id).count()
    if not app:
        raise NotFound("App not found")

    # 查询应用注释设置信息
    app_annotation_setting = db.session.query(AppAnnotationSetting).filter(
        AppAnnotationSetting.app_id == app_id
    ).first()
    if not app_annotation_setting:
        raise NotFound("App annotation setting not found")

    # 准备相关Redis键值，用于标记任务状态
    disable_app_annotation_key = 'disable_app_annotation_{}'.format(str(app_id))
    disable_app_annotation_job_key = 'disable_app_annotation_job_{}'.format(str(job_id))

    try:

        # 初始化数据集对象，用于操作向量索引
        dataset = Dataset(
            id=app_id,
            tenant_id=tenant_id,
            indexing_technique='high_quality',
            collection_binding_id=app_annotation_setting.collection_binding_id
        )

        try:
            # 如果存在注释，则删除对应的向量索引
            if annotations_count > 0:
                vector = Vector(dataset, attributes=['doc_id', 'annotation_id', 'app_id'])
                vector.delete_by_metadata_field('app_id', app_id)
        except Exception:
            # 记录删除注释索引失败的日志
            logging.exception("Delete annotation index failed when annotation deleted.")
        # 标记禁用注释任务为完成
        redis_client.setex(disable_app_annotation_job_key, 600, 'completed')

        # 删除应用的注释设置，并提交数据库事务
        db.session.delete(app_annotation_setting)
        db.session.commit()

        end_at = time.perf_counter()
        # 记录完成删除操作的日志
        logging.info(
            click.style('App annotations index deleted : {} latency: {}'.format(app_id, end_at - start_at),
                        fg='green'))
    except Exception as e:
        # 记录批量删除索引失败的日志，并标记任务为错误
        logging.exception("Annotation batch deleted index failed:{}".format(str(e)))
        redis_client.setex(disable_app_annotation_job_key, 600, 'error')
        disable_app_annotation_error_key = 'disable_app_annotation_error_{}'.format(str(job_id))
        redis_client.setex(disable_app_annotation_error_key, 600, str(e))
    finally:
        # 清理相关Redis键值
        redis_client.delete(disable_app_annotation_key)
