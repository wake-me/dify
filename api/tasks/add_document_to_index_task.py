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
from models.dataset import Document as DatasetDocument
from models.dataset import DocumentSegment


@shared_task(queue='dataset')
def add_document_to_index_task(dataset_document_id: str):
    """
    异步将文档添加到索引中
    :param dataset_document_id: 文档的唯一标识符

    使用方法: add_document_to_index.delay(document_id)
    """
    # 记录开始添加文档到索引的日志，并显示进度信息
    logging.info(click.style('Start add document to index: {}'.format(dataset_document_id), fg='green'))
    start_at = time.perf_counter()

    # 从数据库中查询文档，确认其存在性
    dataset_document = db.session.query(DatasetDocument).filter(DatasetDocument.id == dataset_document_id).first()
    if not dataset_document:
        raise NotFound('Document not found')

    # 仅处理已完成索引状态的文档
    if dataset_document.indexing_status != 'completed':
        return

    # 设置缓存键名，用于标识当前文档的索引过程
    indexing_cache_key = 'document_{}_indexing'.format(dataset_document.id)

    try:
        # 查询并组织文档的各个段落
        segments = db.session.query(DocumentSegment).filter(
            DocumentSegment.document_id == dataset_document.id,
            DocumentSegment.enabled == True
        ) \
            .order_by(DocumentSegment.position.asc()).all()

        documents = []
        for segment in segments:
            document = Document(
                page_content=segment.content,
                metadata={
                    "doc_id": segment.index_node_id,
                    "doc_hash": segment.index_node_hash,
                    "document_id": segment.document_id,
                    "dataset_id": segment.dataset_id,
                }
            )

            documents.append(document)

        # 获取文档所属的数据集，并根据数据集的类型初始化索引处理器
        dataset = dataset_document.dataset

        if not dataset:
            raise Exception('Document has no dataset')

        index_type = dataset.doc_form
        index_processor = IndexProcessorFactory(index_type).init_index_processor()
        index_processor.load(dataset, documents)

        # 记录文档添加到索引完成的日志，并显示执行时间
        end_at = time.perf_counter()
        logging.info(
            click.style('Document added to index: {} latency: {}'.format(dataset_document.id, end_at - start_at), fg='green'))
    except Exception as e:
        # 处理添加文档到索引过程中出现的异常，并更新文档状态
        logging.exception("add document to index failed")
        dataset_document.enabled = False
        dataset_document.disabled_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        dataset_document.status = 'error'
        dataset_document.error = str(e)
        db.session.commit()
    finally:
        # 无论成功或失败，最后都清除相关缓存
        redis_client.delete(indexing_cache_key)
