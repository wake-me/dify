import logging
import time

import click
from celery import shared_task
from werkzeug.exceptions import NotFound

from core.indexing_runner import DocumentIsPausedException, IndexingRunner
from extensions.ext_database import db
from models.dataset import Document


@shared_task(queue='dataset')
def recover_document_indexing_task(dataset_id: str, document_id: str):
    """
    异步恢复文档索引任务。
    :param dataset_id: 数据集ID，字符串类型，用于标识文档所属的数据集。
    :param document_id: 文档ID，字符串类型，用于唯一标识需要恢复索引的文档。
    
    使用方法：recover_document_indexing_task.delay(dataset_id, document_id)
    """
    # 记录开始恢复文档索引的时间
    logging.info(click.style('Recover document: {}'.format(document_id), fg='green'))
    start_at = time.perf_counter()

    # 从数据库中查询指定ID的文档
    document = db.session.query(Document).filter(
        Document.id == document_id,
        Document.dataset_id == dataset_id
    ).first()

    # 如果文档不存在，则抛出未找到文档的异常
    if not document:
        raise NotFound('Document not found')

    try:
        # 初始化索引运行器
        indexing_runner = IndexingRunner()
        # 根据文档的索引状态执行相应的恢复操作
        if document.indexing_status in ["waiting", "parsing", "cleaning"]:
            indexing_runner.run([document])
        elif document.indexing_status == "splitting":
            indexing_runner.run_in_splitting_status(document)
        elif document.indexing_status == "indexing":
            indexing_runner.run_in_indexing_status(document)
        # 记录处理文档结束时间，并计算延迟
        end_at = time.perf_counter()
        logging.info(click.style('Processed document: {} latency: {}'.format(document.id, end_at - start_at), fg='green'))
    except DocumentIsPausedException as ex:
        # 如果文档处于暂停状态，记录信息
        logging.info(click.style(str(ex), fg='yellow'))
    except Exception:
        # 捕获并忽略其他异常
        pass
