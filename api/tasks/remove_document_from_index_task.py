import logging
import time

import click
from celery import shared_task
from werkzeug.exceptions import NotFound

from core.rag.index_processor.index_processor_factory import IndexProcessorFactory
from extensions.ext_database import db
from extensions.ext_redis import redis_client
from models.dataset import Document, DocumentSegment


@shared_task(queue='dataset')
def remove_document_from_index_task(document_id: str):
    """
    异步从索引中移除文档
    :param document_id: 文档ID

    使用方法: remove_document_from_index.delay(document_id)
    """
    # 记录开始移除文档索引的日志
    logging.info(click.style('Start remove document segments from index: {}'.format(document_id), fg='green'))
    start_at = time.perf_counter()

    # 从数据库中查询文档，如果文档不存在，则抛出异常
    document = db.session.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise NotFound('Document not found')

    # 如果文档的索引状态不是"已完成"，则直接返回
    if document.indexing_status != 'completed':
        return

    # 准备清除文档索引的缓存键名
    indexing_cache_key = 'document_{}_indexing'.format(document.id)

    try:
        # 获取文档所属的数据集
        dataset = document.dataset
        if not dataset:
            raise Exception('Document has no dataset')

        # 根据文档类型初始化索引处理器
        index_processor = IndexProcessorFactory(document.doc_form).init_index_processor()

        # 查询文档的所有段落，并准备需要从索引中移除的节点ID列表
        segments = db.session.query(DocumentSegment).filter(DocumentSegment.document_id == document.id).all()
        index_node_ids = [segment.index_node_id for segment in segments]
        if index_node_ids:
            try:
                # 清除索引中与文档相关的数据
                index_processor.clean(dataset, index_node_ids)
            except Exception:
                # 记录清除操作失败的日志
                logging.exception(f"clean dataset {dataset.id} from index failed")

        # 记录移除文档索引操作完成的日志
        end_at = time.perf_counter()
        logging.info(
            click.style('Document removed from index: {} latency: {}'.format(document.id, end_at - start_at), fg='green'))
    except Exception:
        # 记录移除文档索引失败的日志
        logging.exception("remove document from index failed")
        # 如果文档未被归档，则将文档启用状态设置为True，并提交数据库更改
        if not document.archived:
            document.enabled = True
            db.session.commit()
    finally:
        # 删除文档索引操作的缓存记录
        redis_client.delete(indexing_cache_key)