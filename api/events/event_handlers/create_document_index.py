import datetime
import logging
import time

import click
from werkzeug.exceptions import NotFound

from core.indexing_runner import DocumentIsPausedException, IndexingRunner
from events.event_handlers.document_index_event import document_index_created
from extensions.ext_database import db
from models.dataset import Document


@document_index_created.connect
def handle(sender, **kwargs):
    """
    处理文档索引创建的信号。
    
    当文档索引创建事件被触发时，此函数将查询相应的文档，并将其提交给索引器进行处理。
    
    参数:
    - sender: 事件的发送者，通常是触发索引创建的文档集ID。
    - **kwargs: 关键字参数，可能包含'document_ids'，表示需要索引的文档ID列表。
    
    返回值:
    - 无
    """
    dataset_id = sender
    document_ids = kwargs.get('document_ids', None)
    documents = []
    start_at = time.perf_counter()  # 记录处理开始时间
    
    # 遍历每个文档ID，查询文档并更新其索引状态
    for document_id in document_ids:
        logging.info(click.style('Start process document: {}'.format(document_id), fg='green'))

        # 根据文档ID查询文档
        document = db.session.query(Document).filter(
            Document.id == document_id,
            Document.dataset_id == dataset_id
        ).first()

        if not document:
            raise NotFound('Document not found')  # 如果文档不存在，则抛出异常

        # 更新文档的索引状态和处理开始时间
        document.indexing_status = 'parsing'
        document.processing_started_at = datetime.datetime.utcnow()
        documents.append(document)
        db.session.add(document)  # 将更新的文档加入到会话中
    db.session.commit()  # 提交会话，保存对文档的更改

    try:
        indexing_runner = IndexingRunner()  # 创建索引运行器实例
        indexing_runner.run(documents)  # 执行索引处理
        end_at = time.perf_counter()  # 记录处理结束时间
        logging.info(click.style('Processed dataset: {} latency: {}'.format(dataset_id, end_at - start_at), fg='green'))
    except DocumentIsPausedException as ex:
        logging.info(click.style(str(ex), fg='yellow'))  # 如果文档处理被暂停，则记录信息
    except Exception:
        pass  # 忽略其他异常，不进行处理