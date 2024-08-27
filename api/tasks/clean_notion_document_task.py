import logging
import time

import click
from celery import shared_task

from core.rag.index_processor.index_processor_factory import IndexProcessorFactory
from extensions.ext_database import db
from models.dataset import Dataset, Document, DocumentSegment


@shared_task(queue="dataset")
def clean_notion_document_task(document_ids: list[str], dataset_id: str):
    """
    当从Notion文档导入的数据被删除时，清理相应的文档。
    :param document_ids: 需要被清理的文档ID列表
    :param dataset_id: 对应的数据集ID

    使用方法: clean_notion_document_task.delay(document_ids, dataset_id)
    """
    logging.info(
        click.style("Start clean document when import form notion document deleted: {}".format(dataset_id), fg="green")
    )
    start_at = time.perf_counter()

    try:
        # 根据数据集ID查询数据集信息
        dataset = db.session.query(Dataset).filter(Dataset.id == dataset_id).first()

        if not dataset:
            raise Exception("Document has no dataset")
        index_type = dataset.doc_form
        index_processor = IndexProcessorFactory(index_type).init_index_processor()
        for document_id in document_ids:
            document = db.session.query(Document).filter(Document.id == document_id).first()
            db.session.delete(document)
            
            # 查询与该文档关联的文档段，并获取所有索引节点ID
            segments = db.session.query(DocumentSegment).filter(DocumentSegment.document_id == document_id).all()
            index_node_ids = [segment.index_node_id for segment in segments]
            
            # 使用索引处理器清理关联的索引节点
            index_processor.clean(dataset, index_node_ids)
            
            # 从数据库会话中删除所有关联的文档段
            for segment in segments:
                db.session.delete(segment)
        db.session.commit()
        end_at = time.perf_counter()
        logging.info(
            click.style(
                "Clean document when import form notion document deleted end :: {} latency: {}".format(
                    dataset_id, end_at - start_at
                ),
                fg="green",
            )
        )
    except Exception:
        logging.exception("Cleaned document when import form notion document deleted  failed")
