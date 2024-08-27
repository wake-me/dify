import logging
import time

import click
from celery import shared_task

from core.rag.index_processor.index_processor_factory import IndexProcessorFactory
from extensions.ext_database import db
from extensions.ext_redis import redis_client
from models.dataset import Dataset, Document


@shared_task(queue="dataset")
def delete_segment_from_index_task(segment_id: str, index_node_id: str, dataset_id: str, document_id: str):
    """
    异步从索引中删除段落
    :param segment_id: 段落ID，字符串类型，用于标识要删除的段落
    :param index_node_id: 索引节点ID，字符串类型，标识段落所在的索引节点
    :param dataset_id: 数据集ID，字符串类型，指示段落所属的数据集
    :param document_id: 文档ID，字符串类型，指示段落所属的文档
    :return: 无返回值

    使用方法：delete_segment_from_index_task.delay(segment_id)
    """
    logging.info(click.style("Start delete segment from index: {}".format(segment_id), fg="green"))
    start_at = time.perf_counter()
    indexing_cache_key = "segment_{}_delete_indexing".format(segment_id)
    try:
        # 查询数据集信息
        dataset = db.session.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            logging.info(click.style("Segment {} has no dataset, pass.".format(segment_id), fg="cyan"))
            return

        # 查询文档信息
        dataset_document = db.session.query(Document).filter(Document.id == document_id).first()
        if not dataset_document:
            logging.info(click.style("Segment {} has no document, pass.".format(segment_id), fg="cyan"))
            return

        if not dataset_document.enabled or dataset_document.archived or dataset_document.indexing_status != "completed":
            logging.info(click.style("Segment {} document status is invalid, pass.".format(segment_id), fg="cyan"))
            return

        # 根据文档类型获取索引处理器，并使用它来清除索引
        index_type = dataset_document.doc_form
        index_processor = IndexProcessorFactory(index_type).init_index_processor()
        index_processor.clean(dataset, [index_node_id])

        # 记录删除操作完成的日志
        end_at = time.perf_counter()
        logging.info(
            click.style("Segment deleted from index: {} latency: {}".format(segment_id, end_at - start_at), fg="green")
        )
    except Exception:
        # 捕获并记录任何异常
        logging.exception("delete segment from index failed")
    finally:
        # 删除操作结束后，清除相关的缓存
        redis_client.delete(indexing_cache_key)
