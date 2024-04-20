import datetime
import logging
import time

import click
from celery import shared_task
from flask import current_app

from core.indexing_runner import DocumentIsPausedException, IndexingRunner
from extensions.ext_database import db
from models.dataset import Dataset, Document
from services.feature_service import FeatureService


@shared_task(queue='dataset')
def document_indexing_task(dataset_id: str, document_ids: list):
    """
    异步处理文档索引任务。
    
    :param dataset_id: 数据集ID，用于标识待处理文档所属的数据集。
    :param document_ids: 待处理的文档ID列表。
    
    使用方法：document_indexing_task.delay(dataset_id, document_id)
    """
    documents = []
    start_at = time.perf_counter()  # 记录任务开始时间

    # 从数据库获取数据集信息
    dataset = db.session.query(Dataset).filter(Dataset.id == dataset_id).first()

    # 检查文档数量是否超过限制
    features = FeatureService.get_features(dataset.tenant_id)
    try:
        # 检查是否超过批量上传限制
        if features.billing.enabled:
            vector_space = features.vector_space
            count = len(document_ids)
            batch_upload_limit = int(current_app.config['BATCH_UPLOAD_LIMIT'])
            if count > batch_upload_limit:
                raise ValueError(f"You have reached the batch upload limit of {batch_upload_limit}.")
            # 检查是否超过订阅的文档数量限制
            if 0 < vector_space.limit <= vector_space.size:
                raise ValueError("Your total number of documents plus the number of uploads have exceeded the limit of "
                                 "your subscription.")
    except Exception as e:
        # 如果检测到错误，更新相关文档的状态
        for document_id in document_ids:
            document = db.session.query(Document).filter(
                Document.id == document_id,
                Document.dataset_id == dataset_id
            ).first()
            if document:
                document.indexing_status = 'error'
                document.error = str(e)
                document.stopped_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                db.session.add(document)
        db.session.commit()
        return

    # 更新文档状态为处理中，并收集待索引的文档
    for document_id in document_ids:
        logging.info(click.style('Start process document: {}'.format(document_id), fg='green'))

        document = db.session.query(Document).filter(
            Document.id == document_id,
            Document.dataset_id == dataset_id
        ).first()

        if document:
            document.indexing_status = 'parsing'
            document.processing_started_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            documents.append(document)
            db.session.add(document)
    db.session.commit()  # 提交数据库更改

    try:
        # 执行文档索引任务
        indexing_runner = IndexingRunner()
        indexing_runner.run(documents)
        end_at = time.perf_counter()  # 记录任务完成时间
        # 记录任务执行情况
        logging.info(click.style('Processed dataset: {} latency: {}'.format(dataset_id, end_at - start_at), fg='green'))
    except DocumentIsPausedException as ex:
        # 如果文档处理被暂停，记录信息
        logging.info(click.style(str(ex), fg='yellow'))
    except Exception:
        # 吞掉其他异常，不做处理
        pass
