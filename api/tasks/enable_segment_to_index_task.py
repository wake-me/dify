import datetime
import logging
import time

import click
from celery import shared_task
from werkzeug.exceptions import NotFound

from core.rag.index_processor.index_processor_factory import IndexProcessorFactory
from core.rag.models.document import Document
from extensions.ext_database import db
from extensions.ext_redis import redis_client
from models.dataset import DocumentSegment


@shared_task(queue='dataset')
def enable_segment_to_index_task(segment_id: str):
    """
    异步启用段落至索引任务。
    :param segment_id: 段落的唯一标识符。
    
    使用方法: enable_segment_to_index_task.delay(segment_id)
    """
    # 记录开始启用段落至索引的任务
    logging.info(click.style('Start enable segment to index: {}'.format(segment_id), fg='green'))
    start_at = time.perf_counter()

    # 从数据库查询段落信息
    segment = db.session.query(DocumentSegment).filter(DocumentSegment.id == segment_id).first()
    if not segment:
        raise NotFound('Segment not found')

    # 检查段落的状态是否为完成
    if segment.status != 'completed':
        raise NotFound('Segment is not completed, enable action is not allowed.')

    # 构造索引缓存的键名
    indexing_cache_key = 'segment_{}_indexing'.format(segment.id)

    try:
        # 准备文档内容和元数据以供索引
        document = Document(
            page_content=segment.content,
            metadata={
                "doc_id": segment.index_node_id,
                "doc_hash": segment.index_node_hash,
                "document_id": segment.document_id,
                "dataset_id": segment.dataset_id,
            }
        )

        # 获取段落所属的数据库集
        dataset = segment.dataset

        # 如果段落没有所属的数据库集，则跳过
        if not dataset:
            logging.info(click.style('Segment {} has no dataset, pass.'.format(segment.id), fg='cyan'))
            return

        # 获取段落所属的文档
        dataset_document = segment.document

        # 如果段落没有所属的文档，则跳过
        if not dataset_document:
            logging.info(click.style('Segment {} has no document, pass.'.format(segment.id), fg='cyan'))
            return

        # 检查文档的状态是否有效
        if not dataset_document.enabled or dataset_document.archived or dataset_document.indexing_status != 'completed':
            logging.info(click.style('Segment {} document status is invalid, pass.'.format(segment.id), fg='cyan'))
            return

        # 初始化索引处理器，并加载文档进行索引
        index_processor = IndexProcessorFactory(dataset_document.doc_form).init_index_processor()
        index_processor.load(dataset, [document])

        end_at = time.perf_counter()
        # 记录任务完成，包括执行时间
        logging.info(click.style('Segment enabled to index: {} latency: {}'.format(segment.id, end_at - start_at), fg='green'))
    except Exception as e:
        # 如果在索引过程中出现异常，记录异常，并更新段落状态为错误
        logging.exception("enable segment to index failed")
        segment.enabled = False
        segment.disabled_at = datetime.datetime.utcnow()
        segment.status = 'error'
        segment.error = str(e)
        db.session.commit()
    finally:
        # 无论成功或失败，最后都清除索引缓存
        redis_client.delete(indexing_cache_key)
