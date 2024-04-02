import logging
import time

import click
from celery import shared_task

from core.rag.datasource.vdb.vector_factory import Vector
from models.dataset import Dataset
from services.dataset_service import DatasetCollectionBindingService


@shared_task(queue='dataset')
def delete_annotation_index_task(annotation_id: str, app_id: str, tenant_id: str,
                                 collection_binding_id: str):
    """
    异步删除注解索引任务

    参数:
    - annotation_id: str, 要删除的注解ID
    - app_id: str, 应用ID
    - tenant_id: str, 租户ID
    - collection_binding_id: str, 数据集绑定ID

    返回值:
    无
    """
    # 记录开始删除应用注解索引的日志
    logging.info(click.style('Start delete app annotation index: {}'.format(app_id), fg='green'))
    start_at = time.perf_counter()  # 记录开始时间

    try:
        # 根据ID和类型获取数据集绑定信息
        dataset_collection_binding = DatasetCollectionBindingService.get_dataset_collection_binding_by_id_and_type(
            collection_binding_id,
            'annotation'
        )

        # 构造数据集对象
        dataset = Dataset(
            id=app_id,
            tenant_id=tenant_id,
            indexing_technique='high_quality',
            collection_binding_id=dataset_collection_binding.id
        )

        try:
            # 创建向量对象，并根据注解ID删除相应的索引
            vector = Vector(dataset, attributes=['doc_id', 'annotation_id', 'app_id'])
            vector.delete_by_metadata_field('annotation_id', annotation_id)
        except Exception:
            # 如果删除索引失败，记录异常日志
            logging.exception("Delete annotation index failed when annotation deleted.")
        end_at = time.perf_counter()  # 记录结束时间
        # 记录删除索引完成的日志，包括应用ID和执行时间
        logging.info(
            click.style('App annotations index deleted : {} latency: {}'.format(app_id, end_at - start_at),
                        fg='green'))
    except Exception as e:
        # 如果过程中出现任何异常，记录异常日志
        logging.exception("Annotation deleted index failed:{}".format(str(e)))

