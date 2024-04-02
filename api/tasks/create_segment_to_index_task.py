import datetime
import logging
import time
from typing import Optional

import click
from celery import shared_task
from werkzeug.exceptions import NotFound

from core.rag.index_processor.index_processor_factory import IndexProcessorFactory
from core.rag.models.document import Document
from extensions.ext_database import db
from extensions.ext_redis import redis_client
from models.dataset import DocumentSegment


@shared_task(queue='dataset')
def create_segment_to_index_task(segment_id: str, keywords: Optional[list[str]] = None):
    """
    异步创建将段落索引到数据库的任务。
    
    :param segment_id: 段落的唯一标识符。
    :param keywords: 关键词列表，用于搜索索引（可选）。
    使用方法：create_segment_to_index_task.delay(segment_id)
    """

    # 记录开始创建索引的日志，并测量执行时间
    logging.info(click.style('Start create segment to index: {}'.format(segment_id), fg='green'))
    start_at = time.perf_counter()

    # 从数据库查询段落信息
    segment = db.session.query(DocumentSegment).filter(DocumentSegment.id == segment_id).first()
    if not segment:
        raise NotFound('Segment not found')

    # 检查段落的状态是否为等待索引
    if segment.status != 'waiting':
        return

    # 设置缓存键名，用于标识段落是否正在索引
    indexing_cache_key = 'segment_{}_indexing'.format(segment.id)

    try:
        # 更新段落状态为正在索引，并设置索引开始时间
        update_params = {
            DocumentSegment.status: "indexing",
            DocumentSegment.indexing_at: datetime.datetime.utcnow()
        }
        DocumentSegment.query.filter_by(id=segment.id).update(update_params)
        db.session.commit()
        
        # 准备文档内容和元数据，用于索引
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

        # 检查段落是否属于一个有效的数据集
        if not dataset:
            logging.info(click.style('Segment {} has no dataset, pass.'.format(segment.id), fg='cyan'))
            return

        # 获取数据集关联的文档
        dataset_document = segment.document

        # 检查数据集文档的有效性
        if not dataset_document:
            logging.info(click.style('Segment {} has no document, pass.'.format(segment.id), fg='cyan'))
            return

        # 进一步检查文档的索引状态是否有效
        if not dataset_document.enabled or dataset_document.archived or dataset_document.indexing_status != 'completed':
            logging.info(click.style('Segment {} document status is invalid, pass.'.format(segment.id), fg='cyan'))
            return

        # 根据数据集的文档形式选择索引处理器
        index_type = dataset.doc_form
        index_processor = IndexProcessorFactory(index_type).init_index_processor()
        index_processor.load(dataset, [document])

        # 更新段落状态为完成索引，并记录完成时间
        update_params = {
            DocumentSegment.status: "completed",
            DocumentSegment.completed_at: datetime.datetime.utcnow()
        }
        DocumentSegment.query.filter_by(id=segment.id).update(update_params)
        db.session.commit()

        # 记录创建索引完成的日志，包括执行时间
        end_at = time.perf_counter()
        logging.info(click.style('Segment created to index: {} latency: {}'.format(segment.id, end_at - start_at), fg='green'))
    except Exception as e:
        # 记录异常日志，并更新段落状态为错误
        logging.exception("create segment to index failed")
        segment.enabled = False
        segment.disabled_at = datetime.datetime.utcnow()
        segment.status = 'error'
        segment.error = str(e)
        db.session.commit()
    finally:
        # 无论成功或失败，最后都清除缓存
        redis_client.delete(indexing_cache_key)
