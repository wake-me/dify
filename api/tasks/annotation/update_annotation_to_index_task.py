import logging
import time

import click
from celery import shared_task

from core.rag.datasource.vdb.vector_factory import Vector
from core.rag.models.document import Document
from models.dataset import Dataset
from services.dataset_service import DatasetCollectionBindingService


@shared_task(queue='dataset')
def update_annotation_to_index_task(annotation_id: str, question: str, tenant_id: str, app_id: str,
                                    collection_binding_id: str):
    """
    更新注释的索引。
    :param annotation_id: 注释ID
    :param question: 问题文本
    :param tenant_id: 租户ID
    :param app_id: 应用ID
    :param collection_binding_id: 嵌入绑定ID

    使用方法：clean_dataset_task.delay(dataset_id, tenant_id, indexing_technique, index_struct)
    """
    # 开始更新索引的日志记录
    logging.info(click.style('Start update index for annotation: {}'.format(annotation_id), fg='green'))
    start_at = time.perf_counter()

    try:
        # 根据ID和类型获取数据集与集合绑定关系
        dataset_collection_binding = DatasetCollectionBindingService.get_dataset_collection_binding_by_id_and_type(
            collection_binding_id,
            'annotation'
        )

        # 创建数据集实例
        dataset = Dataset(
            id=app_id,
            tenant_id=tenant_id,
            indexing_technique='high_quality',  # 使用高质量索引技术
            embedding_model_provider=dataset_collection_binding.provider_name,  # 设置嵌入模型提供者
            embedding_model=dataset_collection_binding.model_name,  # 设置嵌入模型名称
            collection_binding_id=dataset_collection_binding.id  # 设置集合绑定ID
        )

        # 创建文档实例
        document = Document(
            page_content=question,  # 文档内容为问题文本
            metadata={  # 设置文档元数据
                "annotation_id": annotation_id,
                "app_id": app_id,
                "doc_id": annotation_id
            }
        )
        # 创建向量实例并配置索引
        vector = Vector(dataset, attributes=['doc_id', 'annotation_id', 'app_id'])
        vector.delete_by_metadata_field('annotation_id', annotation_id)  # 根据注释ID删除旧索引
        vector.add_texts([document])  # 添加新文档到索引
        end_at = time.perf_counter()
        # 记录索引构建成功日志
        logging.info(
            click.style(
                'Build index successful for annotation: {} latency: {}'.format(annotation_id, end_at - start_at),
                fg='green'))
    except Exception:
        # 记录索引构建失败异常日志
        logging.exception("Build index for annotation failed")
