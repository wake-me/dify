
from core.app.apps.base_app_queue_manager import AppQueueManager, PublishFrom
from core.app.entities.app_invoke_entities import InvokeFrom
from core.app.entities.queue_entities import QueueRetrieverResourcesEvent
from core.rag.models.document import Document
from extensions.ext_database import db
from models.dataset import DatasetQuery, DocumentSegment
from models.model import DatasetRetrieverResource


class DatasetIndexToolCallbackHandler:
    """数据集工具的回调处理器类。"""

    def __init__(self, queue_manager: AppQueueManager,
                 app_id: str,
                 message_id: str,
                 user_id: str,
                 invoke_from: InvokeFrom) -> None:
        """
        初始化数据集工具回调处理器。

        :param queue_manager: 应用队列管理器，用于处理队列消息。
        :param app_id: 应用的ID。
        :param message_id: 消息的ID。
        :param user_id: 用户的ID。
        :param invoke_from: 调用来源，标识是来自探索、调试器还是其他。
        """
        self._queue_manager = queue_manager
        self._app_id = app_id
        self._message_id = message_id
        self._user_id = user_id
        self._invoke_from = invoke_from

    def on_query(self, query: str, dataset_id: str) -> None:
        """
        处理查询请求。

        :param query: 查询内容。
        :param dataset_id: 数据集ID。
        """
        # 创建一个数据集查询对象并保存到数据库
        dataset_query = DatasetQuery(
            dataset_id=dataset_id,
            content=query,
            source='app',
            source_app_id=self._app_id,
            created_by_role=('account'
                             if self._invoke_from in [InvokeFrom.EXPLORE, InvokeFrom.DEBUGGER] else 'end_user'),
            created_by=self._user_id
        )

        db.session.add(dataset_query)
        db.session.commit()

    def on_tool_end(self, documents: list[Document]) -> None:
        """
        处理工具结束时的逻辑。

        :param documents: 结果文档列表。
        """
        for document in documents:
            # 更新文档段的命中计数
            query = db.session.query(DocumentSegment).filter(
                DocumentSegment.index_node_id == document.metadata['doc_id']
            )

            if 'dataset_id' in document.metadata:
                query = query.filter(DocumentSegment.dataset_id == document.metadata['dataset_id'])

            query.update(
                {DocumentSegment.hit_count: DocumentSegment.hit_count + 1},
                synchronize_session=False
            )

            db.session.commit()

    def return_retriever_resource_info(self, resource: list):
        """
        处理返回检索资源信息的逻辑。

        :param resource: 检索到的资源列表。
        """
        # 如果资源列表非空，则遍历资源，创建数据集检索资源对象并保存到数据库
        if resource and len(resource) > 0:
            for item in resource:
                dataset_retriever_resource = DatasetRetrieverResource(
                    message_id=self._message_id,
                    position=item.get('position'),
                    dataset_id=item.get('dataset_id'),
                    dataset_name=item.get('dataset_name'),
                    document_id=item.get('document_id'),
                    document_name=item.get('document_name'),
                    data_source_type=item.get('data_source_type'),
                    segment_id=item.get('segment_id'),
                    score=item.get('score') if 'score' in item else None,
                    hit_count=item.get('hit_count') if 'hit_count' else None,
                    word_count=item.get('word_count') if 'word_count' in item else None,
                    segment_position=item.get('segment_position') if 'segment_position' in item else None,
                    index_node_hash=item.get('index_node_hash') if 'index_node_hash' in item else None,
                    content=item.get('content'),
                    retriever_from=item.get('retriever_from'),
                    created_by=self._user_id
                )
                db.session.add(dataset_retriever_resource)
                db.session.commit()

        # 向队列发布检索资源事件
        self._queue_manager.publish(
            QueueRetrieverResourcesEvent(retriever_resources=resource),
            PublishFrom.APPLICATION_MANAGER
        )