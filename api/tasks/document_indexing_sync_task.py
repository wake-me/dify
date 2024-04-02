import datetime
import logging
import time

import click
from celery import shared_task
from werkzeug.exceptions import NotFound

from core.indexing_runner import DocumentIsPausedException, IndexingRunner
from core.rag.extractor.notion_extractor import NotionExtractor
from core.rag.index_processor.index_processor_factory import IndexProcessorFactory
from extensions.ext_database import db
from models.dataset import Dataset, Document, DocumentSegment
from models.source import DataSourceBinding


@shared_task(queue='dataset')
def document_indexing_sync_task(dataset_id: str, document_id: str):
    """
    异步更新文档索引任务。
    
    :param dataset_id: 数据集ID，字符串类型，用于标识文档所属的数据集。
    :param document_id: 文档ID，字符串类型，用于标识需要更新索引的文档。
    
    使用方法：document_indexing_sync_task.delay(dataset_id, document_id)
    """
    # 记录开始同步文档的日志
    logging.info(click.style('Start sync document: {}'.format(document_id), fg='green'))
    start_at = time.perf_counter()

    # 从数据库查询文档信息
    document = db.session.query(Document).filter(
        Document.id == document_id,
        Document.dataset_id == dataset_id
    ).first()

    # 如果文档不存在，则抛出异常
    if not document:
        raise NotFound('Document not found')

    # 获取文档的数据源信息
    data_source_info = document.data_source_info_dict
    # 针对Notion导入的文档类型进行处理
    if document.data_source_type == 'notion_import':
        # 检查Notion页面信息是否完整
        if not data_source_info or 'notion_page_id' not in data_source_info \
                or 'notion_workspace_id' not in data_source_info:
            raise ValueError("no notion page found")
        
        # 提取页面和工作区ID等信息
        workspace_id = data_source_info['notion_workspace_id']
        page_id = data_source_info['notion_page_id']
        page_type = data_source_info['type']
        page_edited_time = data_source_info['last_edited_time']

        # 查询与Notion数据源的绑定信息
        data_source_binding = DataSourceBinding.query.filter(
            db.and_(
                DataSourceBinding.tenant_id == document.tenant_id,
                DataSourceBinding.provider == 'notion',
                DataSourceBinding.disabled == False,
                DataSourceBinding.source_info['workspace_id'] == f'"{workspace_id}"'
            )
        ).first()
        
        # 如果找不到绑定信息，则抛出异常
        if not data_source_binding:
            raise ValueError('Data source binding not found.')

        # 初始化Notion数据加载器
        loader = NotionExtractor(
            notion_workspace_id=workspace_id,
            notion_obj_id=page_id,
            notion_page_type=page_type,
            notion_access_token=data_source_binding.access_token,
            tenant_id=document.tenant_id
        )

        # 获取Notion页面的最新编辑时间
        last_edited_time = loader.get_notion_last_edited_time()

        # 检查页面是否被更新
        if last_edited_time != page_edited_time:
            # 更新文档的索引状态和开始处理的时间
            document.indexing_status = 'parsing'
            document.processing_started_at = datetime.datetime.utcnow()
            db.session.commit()

            # 删除文档的所有段落和索引
            try:
                dataset = db.session.query(Dataset).filter(Dataset.id == dataset_id).first()
                if not dataset:
                    raise Exception('Dataset not found')
                index_type = document.doc_form
                index_processor = IndexProcessorFactory(index_type).init_index_processor()

                # 查询并获取所有文档段落信息，准备删除
                segments = db.session.query(DocumentSegment).filter(DocumentSegment.document_id == document_id).all()
                index_node_ids = [segment.index_node_id for segment in segments]

                # 从向量索引中删除文档段落对应的节点
                index_processor.clean(dataset, index_node_ids)

                # 删除数据库中的段落记录
                for segment in segments:
                    db.session.delete(segment)

                # 记录清理文档段落和索引的日志
                end_at = time.perf_counter()
                logging.info(
                    click.style('Cleaned document when document update data source or process rule: {} latency: {}'.format(document_id, end_at - start_at), fg='green'))
            except Exception:
                logging.exception("Cleaned document when document update data source or process rule failed")

            # 重新运行文档索引任务
            try:
                indexing_runner = IndexingRunner()
                indexing_runner.run([document])
                end_at = time.perf_counter()
                # 记录更新文档索引的日志
                logging.info(click.style('update document: {} latency: {}'.format(document.id, end_at - start_at), fg='green'))
            except DocumentIsPausedException as ex:
                # 如果文档被暂停，则记录日志
                logging.info(click.style(str(ex), fg='yellow'))
            except Exception:
                # 其他异常，直接忽略
                pass
