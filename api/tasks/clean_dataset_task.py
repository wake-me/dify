'''
Author: fanwenqi hi.fanwenqi@gmail.com
Date: 2024-04-20 10:03:01
LastEditors: fanwenqi hi.fanwenqi@gmail.com
LastEditTime: 2024-04-20 12:43:41
FilePath: /dify/api/tasks/clean_dataset_task.py
Description: 这是默认设置,请设置`customMade`, 打开koroFileHeader查看配置 进行设置: https://github.com/OBKoro1/koro1FileHeader/wiki/%E9%85%8D%E7%BD%AE
'''
import logging
import time

import click
from celery import shared_task

from core.rag.index_processor.index_processor_factory import IndexProcessorFactory
from extensions.ext_database import db
from models.dataset import (
    AppDatasetJoin,
    Dataset,
    DatasetProcessRule,
    DatasetQuery,
    Document,
    DocumentSegment,
)


@shared_task(queue='dataset')
def clean_dataset_task(dataset_id: str, tenant_id: str, indexing_technique: str,
                       index_struct: str, collection_binding_id: str, doc_form: str):
    """
    当数据集被删除时，清理相应数据集的任务。
    :param dataset_id: 数据集ID
    :param tenant_id: 租户ID
    :param indexing_technique: 索引技术
    :param index_struct: 索引结构字典
    :param collection_binding_id: 集合绑定ID
    :param doc_form: 数据集格式

    使用方法：clean_dataset_task.delay(dataset_id, tenant_id, indexing_technique, index_struct)
    """
    # 记录开始清理数据集的日志
    logging.info(click.style('Start clean dataset when dataset deleted: {}'.format(dataset_id), fg='green'))
    start_at = time.perf_counter()

    try:
        # 初始化数据集对象
        dataset = Dataset(
            id=dataset_id,
            tenant_id=tenant_id,
            indexing_technique=indexing_technique,
            index_struct=index_struct,
            collection_binding_id=collection_binding_id,
        )
        
        # 查询与数据集相关的文档和片段
        documents = db.session.query(Document).filter(Document.dataset_id == dataset_id).all()
        segments = db.session.query(DocumentSegment).filter(DocumentSegment.dataset_id == dataset_id).all()

        # 若未找到相关文档，则记录日志并返回
        if documents is None or len(documents) == 0:
            logging.info(click.style('No documents found for dataset: {}'.format(dataset_id), fg='green'))
        else:
            logging.info(click.style('Cleaning documents for dataset: {}'.format(dataset_id), fg='green'))
            index_processor = IndexProcessorFactory(doc_form).init_index_processor()
            index_processor.clean(dataset, None)

            for document in documents:
                db.session.delete(document)

            for segment in segments:
                db.session.delete(segment)

        # 删除与数据集相关的处理规则、查询和应用数据集关联
        db.session.query(DatasetProcessRule).filter(DatasetProcessRule.dataset_id == dataset_id).delete()
        db.session.query(DatasetQuery).filter(DatasetQuery.dataset_id == dataset_id).delete()
        db.session.query(AppDatasetJoin).filter(AppDatasetJoin.dataset_id == dataset_id).delete()

        # 提交数据库事务
        db.session.commit()

        end_at = time.perf_counter()
        # 记录清理完成的日志，包括执行时间
        logging.info(
            click.style('Cleaned dataset when dataset deleted: {} latency: {}'.format(dataset_id, end_at - start_at), fg='green'))
    except Exception:
        # 记录清理失败的异常日志
        logging.exception("Cleaned dataset when dataset deleted failed")
