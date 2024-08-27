import logging
import time

import click
from celery import shared_task

from core.rag.index_processor.index_processor_factory import IndexProcessorFactory
from core.rag.models.document import Document
from extensions.ext_database import db
from models.dataset import Dataset, DocumentSegment
from models.dataset import Document as DatasetDocument


@shared_task(queue="dataset")
def deal_dataset_vector_index_task(dataset_id: str, action: str):
    """
    异步处理数据集的向量索引任务。
    :param dataset_id: 数据集ID，用于标识需要处理的数据集。
    :param action: 操作类型，支持"add"添加索引或"remove"移除索引。
    使用方法：deal_dataset_vector_index_task.delay(dataset_id, action)
    """
    logging.info(click.style("Start deal dataset vector index: {}".format(dataset_id), fg="green"))
    start_at = time.perf_counter()

    try:
        dataset = Dataset.query.filter_by(id=dataset_id).first()

        # 数据集不存在时抛出异常
        if not dataset:
            raise Exception("Dataset not found")
        index_type = dataset.doc_form
        index_processor = IndexProcessorFactory(index_type).init_index_processor()
        
        # 根据操作类型执行相应的索引处理
        if action == "remove":
            # 移除索引
            index_processor.clean(dataset, None, with_keywords=False)
        elif action == "add":
            dataset_documents = (
                db.session.query(DatasetDocument)
                .filter(
                    DatasetDocument.dataset_id == dataset_id,
                    DatasetDocument.indexing_status == "completed",
                    DatasetDocument.enabled == True,
                    DatasetDocument.archived == False,
                )
                .all()
            )

            # 如果存在文档，则准备文档内容并添加到索引
            if dataset_documents:
                dataset_documents_ids = [doc.id for doc in dataset_documents]
                db.session.query(DatasetDocument).filter(DatasetDocument.id.in_(dataset_documents_ids)).update(
                    {"indexing_status": "indexing"}, synchronize_session=False
                )
                db.session.commit()

                for dataset_document in dataset_documents:
                    try:
                        # add from vector index
                        segments = (
                            db.session.query(DocumentSegment)
                            .filter(DocumentSegment.document_id == dataset_document.id, DocumentSegment.enabled == True)
                            .order_by(DocumentSegment.position.asc())
                            .all()
                        )
                        if segments:
                            documents = []
                            for segment in segments:
                                document = Document(
                                    page_content=segment.content,
                                    metadata={
                                        "doc_id": segment.index_node_id,
                                        "doc_hash": segment.index_node_hash,
                                        "document_id": segment.document_id,
                                        "dataset_id": segment.dataset_id,
                                    },
                                )

                                documents.append(document)
                            # save vector index
                            index_processor.load(dataset, documents, with_keywords=False)
                        db.session.query(DatasetDocument).filter(DatasetDocument.id == dataset_document.id).update(
                            {"indexing_status": "completed"}, synchronize_session=False
                        )
                        db.session.commit()
                    except Exception as e:
                        db.session.query(DatasetDocument).filter(DatasetDocument.id == dataset_document.id).update(
                            {"indexing_status": "error", "error": str(e)}, synchronize_session=False
                        )
                        db.session.commit()
        elif action == "update":
            dataset_documents = (
                db.session.query(DatasetDocument)
                .filter(
                    DatasetDocument.dataset_id == dataset_id,
                    DatasetDocument.indexing_status == "completed",
                    DatasetDocument.enabled == True,
                    DatasetDocument.archived == False,
                )
                .all()
            )
            # add new index
            if dataset_documents:
                # update document status
                dataset_documents_ids = [doc.id for doc in dataset_documents]
                db.session.query(DatasetDocument).filter(DatasetDocument.id.in_(dataset_documents_ids)).update(
                    {"indexing_status": "indexing"}, synchronize_session=False
                )
                db.session.commit()

                # clean index
                index_processor.clean(dataset, None, with_keywords=False)

                for dataset_document in dataset_documents:
                    # update from vector index
                    try:
                        segments = (
                            db.session.query(DocumentSegment)
                            .filter(DocumentSegment.document_id == dataset_document.id, DocumentSegment.enabled == True)
                            .order_by(DocumentSegment.position.asc())
                            .all()
                        )
                        if segments:
                            documents = []
                            for segment in segments:
                                document = Document(
                                    page_content=segment.content,
                                    metadata={
                                        "doc_id": segment.index_node_id,
                                        "doc_hash": segment.index_node_hash,
                                        "document_id": segment.document_id,
                                        "dataset_id": segment.dataset_id,
                                    },
                                )

                                documents.append(document)
                            # save vector index
                            index_processor.load(dataset, documents, with_keywords=False)
                        db.session.query(DatasetDocument).filter(DatasetDocument.id == dataset_document.id).update(
                            {"indexing_status": "completed"}, synchronize_session=False
                        )
                        db.session.commit()
                    except Exception as e:
                        db.session.query(DatasetDocument).filter(DatasetDocument.id == dataset_document.id).update(
                            {"indexing_status": "error", "error": str(e)}, synchronize_session=False
                        )
                        db.session.commit()

        end_at = time.perf_counter()
        logging.info(
            click.style("Deal dataset vector index: {} latency: {}".format(dataset_id, end_at - start_at), fg="green")
        )
    except Exception:
        # 记录异常日志
        logging.exception("Deal dataset vector index failed")
