import logging
from typing import Optional

from core.app.entities.app_invoke_entities import InvokeFrom
from core.rag.datasource.vdb.vector_factory import Vector
from extensions.ext_database import db
from models.dataset import Dataset
from models.model import App, AppAnnotationSetting, Message, MessageAnnotation
from services.annotation_service import AppAnnotationService
from services.dataset_service import DatasetCollectionBindingService

logger = logging.getLogger(__name__)


class AnnotationReplyFeature:
    def query(self, app_record: App,
              message: Message,
              query: str,
              user_id: str,
              invoke_from: InvokeFrom) -> Optional[MessageAnnotation]:
        """
        查询应用程序的注释以进行回复1
        :param app_record: 应用记录
        :param message: 消息
        :param query: 查询字符串
        :param user_id: 用户ID
        :param invoke_from: 调用来源
        :return: 可能的注释消息，如果没有找到则为None
        """
        # 从数据库查询应用的注释设置
        annotation_setting = db.session.query(AppAnnotationSetting).filter(
            AppAnnotationSetting.app_id == app_record.id).first()

        # 如果没有找到注释设置，直接返回None
        if not annotation_setting:
            return None

        # 获取注释设置的详细信息，包括得分阈值和嵌入模型信息
        collection_binding_detail = annotation_setting.collection_binding_detail

        try:
            # 处理得分阈值，默认为1
            score_threshold = annotation_setting.score_threshold or 1
            # 获取嵌入提供者和模型名称
            embedding_provider_name = collection_binding_detail.provider_name
            embedding_model_name = collection_binding_detail.model_name

            # 基于嵌入提供者和模型名称，获取数据集与集合绑定信息
            dataset_collection_binding = DatasetCollectionBindingService.get_dataset_collection_binding(
                embedding_provider_name,
                embedding_model_name,
                'annotation'
            )

            # 创建一个数据集对象，用于向量搜索
            dataset = Dataset(
                id=app_record.id,
                tenant_id=app_record.tenant_id,
                indexing_technique='high_quality',
                embedding_model_provider=embedding_provider_name,
                embedding_model=embedding_model_name,
                collection_binding_id=dataset_collection_binding.id
            )

            # 创建向量对象，用于查询
            vector = Vector(dataset, attributes=['doc_id', 'annotation_id', 'app_id'])

            # 执行向量搜索，获取匹配的文档
            documents = vector.search_by_vector(
                query=query,
                top_k=1,
                score_threshold=score_threshold,
                filter={
                    'group_id': [dataset.id]
                }
            )

            # 如果有找到文档，则处理并返回注释
            if documents:
                annotation_id = documents[0].metadata['annotation_id']
                score = documents[0].metadata['score']
                # 根据注释ID获取注释对象
                annotation = AppAnnotationService.get_annotation_by_id(annotation_id)
                if annotation:
                    # 根据调用来源，设置来源标志
                    if invoke_from in [InvokeFrom.SERVICE_API, InvokeFrom.WEB_APP]:
                        from_source = 'api'
                    else:
                        from_source = 'console'

                    # 添加注释历史记录
                    AppAnnotationService.add_annotation_history(annotation.id,
                                                                app_record.id,
                                                                annotation.question,
                                                                annotation.content,
                                                                query,
                                                                user_id,
                                                                message.id,
                                                                from_source,
                                                                score)

                    return annotation
        except Exception as e:
            # 如果查询过程中出现异常，记录警告日志，并返回None
            logger.warning(f'Query annotation failed, exception: {str(e)}.')
            return None

        # 如果没有找到匹配的注释，返回None
        return None
