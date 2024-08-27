import datetime
import logging
import time

import click
from celery import shared_task
from werkzeug.exceptions import NotFound

from core.indexing_runner import DocumentIsPausedException, IndexingRunner
from core.rag.index_processor.index_processor_factory import IndexProcessorFactory
from extensions.ext_database import db
from models.dataset import Dataset, Document, DocumentSegment


@shared_task(queue="dataset")
def document_indexing_update_task(dataset_id: str, document_id: str):
    """
    异步更新文档索引任务。
    
    :param dataset_id: 数据集ID，字符串类型，用于标识文档所属的数据集。
    :param document_id: 文档ID，字符串类型，用于标识需要更新索引的文档。
    
    使用方法：document_indexing_update_task.delay(dataset_id, document_id)
    """
    logging.info(click.style("Start update document: {}".format(document_id), fg="green"))
    start_at = time.perf_counter()

    document = db.session.query(Document).filter(Document.id == document_id, Document.dataset_id == dataset_id).first()

    # 如果文档不存在，则抛出未找到异常
    if not document:
        raise NotFound("Document not found")

    document.indexing_status = "parsing"
    document.processing_started_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    db.session.commit()

    # 删除文档的所有段落和索引
    try:
        # 获取数据集对象
        dataset = db.session.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            raise Exception("Dataset not found")

        # 根据文档形式获取索引处理器
        index_type = document.doc_form
        index_processor = IndexProcessorFactory(index_type).init_index_processor()

        # 查询并获取文档的所有段落，进而获取段落对应的索引节点ID
        segments = db.session.query(DocumentSegment).filter(DocumentSegment.document_id == document_id).all()
        if segments:
            index_node_ids = [segment.index_node_id for segment in segments]

            # delete from vector index
            index_processor.clean(dataset, index_node_ids)

            for segment in segments:
                db.session.delete(segment)
            db.session.commit()
        end_at = time.perf_counter()
        # 记录删除文档段落和索引的日志
        logging.info(
            click.style(
                "Cleaned document when document update data source or process rule: {} latency: {}".format(
                    document_id, end_at - start_at
                ),
                fg="green",
            )
        )
    except Exception:
        # 记录异常日志
        logging.exception("Cleaned document when document update data source or process rule failed")

    try:
        # 初始化索引运行器并执行索引任务
        indexing_runner = IndexingRunner()
        indexing_runner.run([document])
        end_at = time.perf_counter()
        logging.info(click.style("update document: {} latency: {}".format(document.id, end_at - start_at), fg="green"))
    except DocumentIsPausedException as ex:
        logging.info(click.style(str(ex), fg="yellow"))
    except Exception:
        # 忽略其他异常
        pass
