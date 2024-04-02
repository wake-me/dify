import logging
import time

import click
from celery import shared_task

from core.rag.index_processor.index_processor_factory import IndexProcessorFactory
from extensions.ext_database import db
from models.dataset import Dataset, DocumentSegment


@shared_task(queue='dataset')
def clean_document_task(document_id: str, dataset_id: str, doc_form: str):
    """
    当文档被删除时，清理相应的文档数据。
    :param document_id: 文档ID
    :param dataset_id: 数据集ID
    :param doc_form: 文档形式或结构

    使用方法：clean_document_task.delay(document_id, dataset_id)
    """
    logging.info(click.style('Start clean document when document deleted: {}'.format(document_id), fg='green'))
    start_at = time.perf_counter()

    try:
        # 根据数据集ID查询数据集信息
        dataset = db.session.query(Dataset).filter(Dataset.id == dataset_id).first()
        # 检查数据集是否存在
        if not dataset:
            raise Exception('Document has no dataset')
        
        # 根据文档ID查询所有的文档段落
        segments = db.session.query(DocumentSegment).filter(DocumentSegment.document_id == document_id).all()
        # 如果存在文档段落，则进行清理操作
        if segments:
            index_node_ids = [segment.index_node_id for segment in segments]
            # 根据文档形式初始化索引处理器，并执行清理操作
            index_processor = IndexProcessorFactory(doc_form).init_index_processor()
            index_processor.clean(dataset, index_node_ids)

            # 删除所有的文档段落记录
            for segment in segments:
                db.session.delete(segment)

            db.session.commit()
            end_at = time.perf_counter()
            logging.info(
                click.style('Cleaned document when document deleted: {} latency: {}'.format(document_id, end_at - start_at), fg='green'))
    except Exception:
        logging.exception("Cleaned document when document deleted failed")
