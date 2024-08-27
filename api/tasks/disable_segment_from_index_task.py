import logging
import time

import click
from celery import shared_task
from werkzeug.exceptions import NotFound

from core.rag.index_processor.index_processor_factory import IndexProcessorFactory
from extensions.ext_database import db
from extensions.ext_redis import redis_client
from models.dataset import DocumentSegment


@shared_task(queue="dataset")
def disable_segment_from_index_task(segment_id: str):
    """
    异步从索引中禁用指定的段落
    :param segment_id: 段落的唯一标识符

    使用方法: disable_segment_from_index_task.delay(segment_id)
    """
    logging.info(click.style("Start disable segment from index: {}".format(segment_id), fg="green"))
    start_at = time.perf_counter()

    # 从数据库查询段落信息
    segment = db.session.query(DocumentSegment).filter(DocumentSegment.id == segment_id).first()
    if not segment:
        raise NotFound("Segment not found")

    if segment.status != "completed":
        raise NotFound("Segment is not completed , disable action is not allowed.")

    indexing_cache_key = "segment_{}_indexing".format(segment.id)

    try:
        # 获取段落所属的数据集
        dataset = segment.dataset

        # 如果段落没有所属的数据集，则记录日志并退出
        if not dataset:
            logging.info(click.style("Segment {} has no dataset, pass.".format(segment.id), fg="cyan"))
            return

        # 获取段落关联的文档
        dataset_document = segment.document

        # 如果段落没有关联的文档，则记录日志并退出
        if not dataset_document:
            logging.info(click.style("Segment {} has no document, pass.".format(segment.id), fg="cyan"))
            return

        if not dataset_document.enabled or dataset_document.archived or dataset_document.indexing_status != "completed":
            logging.info(click.style("Segment {} document status is invalid, pass.".format(segment.id), fg="cyan"))
            return

        # 根据文档形式获取索引处理器，并使用该处理器清除段落的索引
        index_type = dataset_document.doc_form
        index_processor = IndexProcessorFactory(index_type).init_index_processor()
        index_processor.clean(dataset, [segment.index_node_id])

        # 记录从索引中移除段落的日志，包括执行时间
        end_at = time.perf_counter()
        logging.info(
            click.style("Segment removed from index: {} latency: {}".format(segment.id, end_at - start_at), fg="green")
        )
    except Exception:
        # 如果处理过程中发生异常，则记录异常日志，并将段落重新标记为可用
        logging.exception("remove segment from index failed")
        segment.enabled = True
        db.session.commit()
    finally:
        # 无论成功或失败，最后都删除段落索引的缓存
        redis_client.delete(indexing_cache_key)
