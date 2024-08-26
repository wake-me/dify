import math
import threading
from collections import Counter
from typing import Optional, cast

from flask import Flask, current_app

from core.app.app_config.entities import DatasetEntity, DatasetRetrieveConfigEntity
from core.app.entities.app_invoke_entities import InvokeFrom, ModelConfigWithCredentialsEntity
from core.callback_handler.index_tool_callback_handler import DatasetIndexToolCallbackHandler
from core.entities.agent_entities import PlanningStrategy
from core.memory.token_buffer_memory import TokenBufferMemory
from core.model_manager import ModelInstance, ModelManager
from core.model_runtime.entities.message_entities import PromptMessageTool
from core.model_runtime.entities.model_entities import ModelFeature, ModelType
from core.model_runtime.model_providers.__base.large_language_model import LargeLanguageModel
from core.ops.entities.trace_entity import TraceTaskName
from core.ops.ops_trace_manager import TraceQueueManager, TraceTask
from core.ops.utils import measure_time
from core.rag.data_post_processor.data_post_processor import DataPostProcessor
from core.rag.datasource.keyword.jieba.jieba_keyword_table_handler import JiebaKeywordTableHandler
from core.rag.datasource.retrieval_service import RetrievalService
from core.rag.models.document import Document
from core.rag.retrieval.retrival_methods import RetrievalMethod
from core.rag.retrieval.router.multi_dataset_function_call_router import FunctionCallMultiDatasetRouter
from core.rag.retrieval.router.multi_dataset_react_route import ReactMultiDatasetRouter
from core.tools.tool.dataset_retriever.dataset_multi_retriever_tool import DatasetMultiRetrieverTool
from core.tools.tool.dataset_retriever.dataset_retriever_base_tool import DatasetRetrieverBaseTool
from core.tools.tool.dataset_retriever.dataset_retriever_tool import DatasetRetrieverTool
from extensions.ext_database import db
from models.dataset import Dataset, DatasetQuery, DocumentSegment
from models.dataset import Document as DatasetDocument

default_retrieval_model = {
    'search_method': RetrievalMethod.SEMANTIC_SEARCH.value,
    'reranking_enable': False,
    'reranking_model': {
        'reranking_provider_name': '',
        'reranking_model_name': ''
    },
    'top_k': 2,
    'score_threshold_enabled': False
}


class DatasetRetrieval:
    def __init__(self, application_generate_entity=None):
        self.application_generate_entity = application_generate_entity

    def retrieve(
            self, app_id: str, user_id: str, tenant_id: str,
            model_config: ModelConfigWithCredentialsEntity,
            config: DatasetEntity,
            query: str,
            invoke_from: InvokeFrom,
            show_retrieve_source: bool,
            hit_callback: DatasetIndexToolCallbackHandler,
            message_id: str,
            memory: Optional[TokenBufferMemory] = None,
    ) -> Optional[str]:
        """
        Retrieve dataset.
        :param app_id: app_id
        :param user_id: user_id
        :param tenant_id: tenant id
        :param model_config: model config
        :param config: dataset config
        :param query: query
        :param invoke_from: invoke from
        :param show_retrieve_source: show retrieve source
        :param hit_callback: hit callback
        :param message_id: message id
        :param memory: memory
        :return:
        """
        dataset_ids = config.dataset_ids
        if len(dataset_ids) == 0:
            return None
        retrieve_config = config.retrieve_config

        # check model is support tool calling
        model_type_instance = model_config.provider_model_bundle.model_type_instance
        model_type_instance = cast(LargeLanguageModel, model_type_instance)

        model_manager = ModelManager()
        model_instance = model_manager.get_model_instance(
            tenant_id=tenant_id,
            model_type=ModelType.LLM,
            provider=model_config.provider,
            model=model_config.model
        )

        # get model schema
        model_schema = model_type_instance.get_model_schema(
            model=model_config.model,
            credentials=model_config.credentials
        )

        if not model_schema:
            return None

        planning_strategy = PlanningStrategy.REACT_ROUTER
        features = model_schema.features
        if features:
            if ModelFeature.TOOL_CALL in features \
                    or ModelFeature.MULTI_TOOL_CALL in features:
                planning_strategy = PlanningStrategy.ROUTER
        available_datasets = []
        for dataset_id in dataset_ids:
            # get dataset from dataset id
            dataset = db.session.query(Dataset).filter(
                Dataset.tenant_id == tenant_id,
                Dataset.id == dataset_id
            ).first()

            # pass if dataset is not available
            if not dataset:
                continue

            # pass if dataset is not available
            if (dataset and dataset.available_document_count == 0
                    and dataset.available_document_count == 0):
                continue

            available_datasets.append(dataset)
        all_documents = []
        user_from = 'account' if invoke_from in [InvokeFrom.EXPLORE, InvokeFrom.DEBUGGER] else 'end_user'
        if retrieve_config.retrieve_strategy == DatasetRetrieveConfigEntity.RetrieveStrategy.SINGLE:
            all_documents = self.single_retrieve(
                app_id, tenant_id, user_id, user_from, available_datasets, query,
                model_instance,
                model_config, planning_strategy, message_id
            )
        elif retrieve_config.retrieve_strategy == DatasetRetrieveConfigEntity.RetrieveStrategy.MULTIPLE:
            all_documents = self.multiple_retrieve(
                app_id, tenant_id, user_id, user_from,
                available_datasets, query, retrieve_config.top_k,
                retrieve_config.score_threshold,
                retrieve_config.rerank_mode,
                retrieve_config.reranking_model,
                retrieve_config.weights,
                retrieve_config.reranking_enabled,
                message_id,
            )

        document_score_list = {}
        for item in all_documents:
            if item.metadata.get('score'):
                document_score_list[item.metadata['doc_id']] = item.metadata['score']

        document_context_list = []
        index_node_ids = [document.metadata['doc_id'] for document in all_documents]
        segments = DocumentSegment.query.filter(
            DocumentSegment.dataset_id.in_(dataset_ids),
            DocumentSegment.completed_at.isnot(None),
            DocumentSegment.status == 'completed',
            DocumentSegment.enabled == True,
            DocumentSegment.index_node_id.in_(index_node_ids)
        ).all()

        if segments:
            index_node_id_to_position = {id: position for position, id in enumerate(index_node_ids)}
            sorted_segments = sorted(segments,
                                     key=lambda segment: index_node_id_to_position.get(segment.index_node_id,
                                                                                       float('inf')))
            for segment in sorted_segments:
                if segment.answer:
                    document_context_list.append(f'question:{segment.get_sign_content()} answer:{segment.answer}')
                else:
                    document_context_list.append(segment.get_sign_content())
            if show_retrieve_source:
                context_list = []
                resource_number = 1
                for segment in sorted_segments:
                    dataset = Dataset.query.filter_by(
                        id=segment.dataset_id
                    ).first()
                    document = DatasetDocument.query.filter(DatasetDocument.id == segment.document_id,
                                                            DatasetDocument.enabled == True,
                                                            DatasetDocument.archived == False,
                                                            ).first()
                    if dataset and document:
                        source = {
                            'position': resource_number,
                            'dataset_id': dataset.id,
                            'dataset_name': dataset.name,
                            'document_id': document.id,
                            'document_name': document.name,
                            'data_source_type': document.data_source_type,
                            'segment_id': segment.id,
                            'retriever_from': invoke_from.to_source(),
                            'score': document_score_list.get(segment.index_node_id, None)
                        }

                        if invoke_from.to_source() == 'dev':
                            source['hit_count'] = segment.hit_count
                            source['word_count'] = segment.word_count
                            source['segment_position'] = segment.position
                            source['index_node_hash'] = segment.index_node_hash
                        if segment.answer:
                            source['content'] = f'question:{segment.content} \nanswer:{segment.answer}'
                        else:
                            source['content'] = segment.content
                        context_list.append(source)
                    resource_number += 1
                if hit_callback:
                    hit_callback.return_retriever_resource_info(context_list)

            return str("\n".join(document_context_list))
        return ''

    def single_retrieve(
            self, app_id: str,
            tenant_id: str,
            user_id: str,
            user_from: str,
            available_datasets: list,
            query: str,
            model_instance: ModelInstance,
            model_config: ModelConfigWithCredentialsEntity,
            planning_strategy: PlanningStrategy,
            message_id: Optional[str] = None,
    ):
        tools = []
        # 为每个可用数据集生成一个message_tool对象
        for dataset in available_datasets:
            description = dataset.description
            if not description:
                description = 'useful for when you want to answer queries about the ' + dataset.name

            description = description.replace('\n', '').replace('\r', '')
            message_tool = PromptMessageTool(
                name=dataset.id,
                description=description,
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                }
            )
            tools.append(message_tool)
        
        dataset_id = None
        # 根据规划策略选择数据集和调用相应的路由器
        if planning_strategy == PlanningStrategy.REACT_ROUTER:
            react_multi_dataset_router = ReactMultiDatasetRouter()
            dataset_id = react_multi_dataset_router.invoke(query, tools, model_config, model_instance,
                                                        user_id, tenant_id)

        elif planning_strategy == PlanningStrategy.ROUTER:
            function_call_router = FunctionCallMultiDatasetRouter()
            dataset_id = function_call_router.invoke(query, tools, model_config, model_instance)

        if dataset_id:
            # 根据选定的dataset_id获取检索模型配置
            dataset = db.session.query(Dataset).filter(
                Dataset.id == dataset_id
            ).first()
            if dataset:
                retrieval_model_config = dataset.retrieval_model \
                    if dataset.retrieval_model else default_retrieval_model

                # 获取检索参数
                top_k = retrieval_model_config['top_k']
                # 获取检索方法
                if dataset.indexing_technique == "economy":
                    retrival_method = 'keyword_search'
                else:
                    retrival_method = retrieval_model_config['search_method']
                # 获取重排名模型
                reranking_model = retrieval_model_config['reranking_model'] \
                    if retrieval_model_config['reranking_enable'] else None
                # 获取得分阈值
                score_threshold = .0
                score_threshold_enabled = retrieval_model_config.get("score_threshold_enabled")
                if score_threshold_enabled:
                    score_threshold = retrieval_model_config.get("score_threshold")

                with measure_time() as timer:
                    results = RetrievalService.retrieve(
                        retrival_method=retrival_method, dataset_id=dataset.id,
                        query=query,
                        top_k=top_k, score_threshold=score_threshold,
                        reranking_model=reranking_model,
                        reranking_mode=retrieval_model_config.get('reranking_mode', 'reranking_model'),
                        weights=retrieval_model_config.get('weights', None),
                    )
                self._on_query(query, [dataset_id], app_id, user_from, user_id)

                if results:
                    self._on_retrival_end(results, message_id, timer)

                return results
        return []

    def multiple_retrieve(
            self,
            app_id: str,
            tenant_id: str,
            user_id: str,
            user_from: str,
            available_datasets: list,
            query: str,
            top_k: int,
            score_threshold: float,
            reranking_mode: str,
            reranking_model: Optional[dict] = None,
            weights: Optional[dict] = None,
            reranking_enable: bool = True,
            message_id: Optional[str] = None,
    ):
        threads = []
        all_documents = []
        dataset_ids = [dataset.id for dataset in available_datasets]
        index_type = None
        for dataset in available_datasets:
            index_type = dataset.indexing_technique
            retrieval_thread = threading.Thread(target=self._retriever, kwargs={
                'flask_app': current_app._get_current_object(),
                'dataset_id': dataset.id,
                'query': query,
                'top_k': top_k,
                'all_documents': all_documents,
            })
            threads.append(retrieval_thread)
            retrieval_thread.start()
        for thread in threads:
            thread.join()

        with measure_time() as timer:
            if reranking_enable:
                # do rerank for searched documents
                data_post_processor = DataPostProcessor(
                    tenant_id, reranking_mode,
                    reranking_model, weights, False
                )

                all_documents = data_post_processor.invoke(
                    query=query,
                    documents=all_documents,
                    score_threshold=score_threshold,
                    top_n=top_k
                )
            else:
                if index_type == "economy":
                    all_documents = self.calculate_keyword_score(query, all_documents, top_k)
                elif index_type == "high_quality":
                    all_documents = self.calculate_vector_score(all_documents, top_k, score_threshold)

        self._on_query(query, dataset_ids, app_id, user_from, user_id)

        if all_documents:
            self._on_retrival_end(all_documents, message_id, timer)

        return all_documents

    def _on_retrival_end(
        self, documents: list[Document], message_id: Optional[str] = None, timer: Optional[dict] = None
    ) -> None:
        """Handle retrival end."""
        for document in documents:
            # 根据文档的doc_id查询对应的文档段落
            query = db.session.query(DocumentSegment).filter(
                DocumentSegment.index_node_id == document.metadata['doc_id']
            )

            # 如果文档元数据中包含dataset_id，则进一步筛选
            if 'dataset_id' in document.metadata:
                query = query.filter(DocumentSegment.dataset_id == document.metadata['dataset_id'])

            # 为查询到的文档段落的hit_count加1
            query.update(
                {DocumentSegment.hit_count: DocumentSegment.hit_count + 1},
                synchronize_session=False
            )

            # 提交数据库事务
            db.session.commit()

        # get tracing instance
        trace_manager: TraceQueueManager = self.application_generate_entity.trace_manager if self.application_generate_entity else None
        if trace_manager:
            trace_manager.add_trace_task(
                TraceTask(
                    TraceTaskName.DATASET_RETRIEVAL_TRACE,
                    message_id=message_id,
                    documents=documents,
                    timer=timer
                )
            )

    def _on_query(self, query: str, dataset_ids: list[str], app_id: str, user_from: str, user_id: str) -> None:
        """
        处理查询请求。
        
        :param query: 用户的查询内容，类型为字符串。
        :param dataset_ids: 查询目标的数据集ID列表，类型为字符串列表。
        :param app_id: 应用的ID，用于标识查询来源的应用。
        :param user_from: 用户身份，表示查询发起者的角色。
        :param user_id: 发起查询的用户ID。
        :return: 无返回值。
        """
        # 如果查询内容为空，则直接返回，不进行后续操作
        if not query:
            return
        dataset_queries = []
        for dataset_id in dataset_ids:
            # 创建数据集查询记录对象，并填充相关信息
            dataset_query = DatasetQuery(
                dataset_id=dataset_id,
                content=query,
                source='app',
                source_app_id=app_id,
                created_by_role=user_from,
                created_by=user_id
            )
            dataset_queries.append(dataset_query)
        if dataset_queries:
            db.session.add_all(dataset_queries)
        db.session.commit()

    def _retriever(self, flask_app: Flask, dataset_id: str, query: str, top_k: int, all_documents: list):
        """
        从指定数据集中检索与查询字符串相关的文档。
        
        :param flask_app: Flask应用实例，用于提供应用上下文。
        :param dataset_id: 数据集的唯一标识符。
        :param query: 用户的查询字符串。
        :param top_k: 需要检索出的文档数量。
        :param all_documents: 已检索到的文档列表，会在此基础上继续添加新的检索结果。
        :return: 更新后的文档列表。
        """
        with flask_app.app_context():
            # 从数据库中查询指定ID的数据集
            dataset = db.session.query(Dataset).filter(
                Dataset.id == dataset_id
            ).first()

            # 如果数据集不存在，则返回空列表
            if not dataset:
                return []

            # 获取检索模型，如果未设置，则使用默认模型
            retrieval_model = dataset.retrieval_model if dataset.retrieval_model else default_retrieval_model

            if dataset.indexing_technique == "economy":
                # 使用关键字表进行查询
                documents = RetrievalService.retrieve(retrival_method='keyword_search',
                                                    dataset_id=dataset.id,
                                                    query=query,
                                                    top_k=top_k
                                                    )
                if documents:
                    all_documents.extend(documents)
            else:
                if top_k > 0:
                    # 根据指定的检索模型从数据集中检索文档
                    documents = RetrievalService.retrieve(retrival_method=retrieval_model['search_method'],
                                                          dataset_id=dataset.id,
                                                          query=query,
                                                          top_k=top_k,
                                                          score_threshold=retrieval_model.get('score_threshold', .0)
                                                          if retrieval_model['score_threshold_enabled'] else None,
                                                          reranking_model=retrieval_model.get('reranking_model', None)
                                                          if retrieval_model['reranking_enable'] else None,
                                                          reranking_mode=retrieval_model.get('reranking_mode')
                                                          if retrieval_model.get('reranking_mode') else 'reranking_model',
                                                          weights=retrieval_model.get('weights', None),
                                                          )

                    all_documents.extend(documents)

    def to_dataset_retriever_tool(self, tenant_id: str,
                                dataset_ids: list[str],
                                retrieve_config: DatasetRetrieveConfigEntity,
                                return_resource: bool,
                                invoke_from: InvokeFrom,
                                hit_callback: DatasetIndexToolCallbackHandler) \
            -> Optional[list[DatasetRetrieverBaseTool]]:
        """
        将给定的参数转换为数据集检索工具。

        :param tenant_id: 租户ID。
        :param dataset_ids: 数据集ID列表。
        :param retrieve_config: 数据集检索配置实体。
        :param return_resource: 是否返回资源。
        :param invoke_from: 调用来源。
        :param hit_callback: 数据集索引工具回调处理器。
        :return: 数据集检索基础工具的可选列表。
        """
        tools = []  # 初始化检索工具列表
        available_datasets = []  # 初始化可用数据集列表

        # 遍历数据集ID以获取可用数据集
        for dataset_id in dataset_ids:
            # 根据数据集ID查询数据集信息
            dataset = db.session.query(Dataset).filter(
                Dataset.tenant_id == tenant_id,
                Dataset.id == dataset_id
            ).first()

            # 如果数据集不可用，则跳过
            if not dataset:
                continue

            # 如果数据集无可用文档，则跳过
            if (dataset and dataset.available_document_count == 0
                    and dataset.available_document_count == 0):
                continue

            available_datasets.append(dataset)  # 将可用数据集添加到列表

        # 根据检索策略配置检索工具
        if retrieve_config.retrieve_strategy == DatasetRetrieveConfigEntity.RetrieveStrategy.SINGLE:
            # 设置默认检索模型配置
            default_retrieval_model = {
                'search_method': RetrievalMethod.SEMANTIC_SEARCH.value,
                'reranking_enable': False,
                'reranking_model': {
                    'reranking_provider_name': '',
                    'reranking_model_name': ''
                },
                'top_k': 2,
                'score_threshold_enabled': False
            }

            # 遍历可用数据集配置检索工具
            for dataset in available_datasets:
                retrieval_model_config = dataset.retrieval_model \
                    if dataset.retrieval_model else default_retrieval_model

                # 获取top_k值
                top_k = retrieval_model_config['top_k']

                # 获取得分阈值
                score_threshold = None
                score_threshold_enabled = retrieval_model_config.get("score_threshold_enabled")
                if score_threshold_enabled:
                    score_threshold = retrieval_model_config.get("score_threshold")

                # 创建单个数据集检索工具实例
                tool = DatasetRetrieverTool.from_dataset(
                    dataset=dataset,
                    top_k=top_k,
                    score_threshold=score_threshold,
                    hit_callbacks=[hit_callback],
                    return_resource=return_resource,
                    retriever_from=invoke_from.to_source()
                )

                tools.append(tool)  # 将检索工具实例添加到列表
        elif retrieve_config.retrieve_strategy == DatasetRetrieveConfigEntity.RetrieveStrategy.MULTIPLE:
            # 创建多个数据集检索工具实例
            tool = DatasetMultiRetrieverTool.from_dataset(
                dataset_ids=[dataset.id for dataset in available_datasets],
                tenant_id=tenant_id,
                top_k=retrieve_config.top_k or 2,
                score_threshold=retrieve_config.score_threshold,
                hit_callbacks=[hit_callback],
                return_resource=return_resource,
                retriever_from=invoke_from.to_source(),
                reranking_provider_name=retrieve_config.reranking_model.get('reranking_provider_name'),
                reranking_model_name=retrieve_config.reranking_model.get('reranking_model_name')
            )

            tools.append(tool)  # 将多个数据集检索工具实例添加到列表

        return tools

    def calculate_keyword_score(self, query: str, documents: list[Document], top_k: int) -> list[Document]:
        """
        Calculate keywords scores
        :param query: search query
        :param documents: documents for reranking

        :return:
        """
        keyword_table_handler = JiebaKeywordTableHandler()
        query_keywords = keyword_table_handler.extract_keywords(query, None)
        documents_keywords = []
        for document in documents:
            # get the document keywords
            document_keywords = keyword_table_handler.extract_keywords(document.page_content, None)
            document.metadata['keywords'] = document_keywords
            documents_keywords.append(document_keywords)

        # Counter query keywords(TF)
        query_keyword_counts = Counter(query_keywords)

        # total documents
        total_documents = len(documents)

        # calculate all documents' keywords IDF
        all_keywords = set()
        for document_keywords in documents_keywords:
            all_keywords.update(document_keywords)

        keyword_idf = {}
        for keyword in all_keywords:
            # calculate include query keywords' documents
            doc_count_containing_keyword = sum(1 for doc_keywords in documents_keywords if keyword in doc_keywords)
            # IDF
            keyword_idf[keyword] = math.log((1 + total_documents) / (1 + doc_count_containing_keyword)) + 1

        query_tfidf = {}

        for keyword, count in query_keyword_counts.items():
            tf = count
            idf = keyword_idf.get(keyword, 0)
            query_tfidf[keyword] = tf * idf

        # calculate all documents' TF-IDF
        documents_tfidf = []
        for document_keywords in documents_keywords:
            document_keyword_counts = Counter(document_keywords)
            document_tfidf = {}
            for keyword, count in document_keyword_counts.items():
                tf = count
                idf = keyword_idf.get(keyword, 0)
                document_tfidf[keyword] = tf * idf
            documents_tfidf.append(document_tfidf)

        def cosine_similarity(vec1, vec2):
            intersection = set(vec1.keys()) & set(vec2.keys())
            numerator = sum(vec1[x] * vec2[x] for x in intersection)

            sum1 = sum(vec1[x] ** 2 for x in vec1.keys())
            sum2 = sum(vec2[x] ** 2 for x in vec2.keys())
            denominator = math.sqrt(sum1) * math.sqrt(sum2)

            if not denominator:
                return 0.0
            else:
                return float(numerator) / denominator

        similarities = []
        for document_tfidf in documents_tfidf:
            similarity = cosine_similarity(query_tfidf, document_tfidf)
            similarities.append(similarity)

        for document, score in zip(documents, similarities):
            # format document
            document.metadata['score'] = score
        documents = sorted(documents, key=lambda x: x.metadata['score'], reverse=True)
        return documents[:top_k] if top_k else documents

    def calculate_vector_score(self, all_documents: list[Document],
                               top_k: int, score_threshold: float) -> list[Document]:
        filter_documents = []
        for document in all_documents:
            if score_threshold is None or document.metadata['score'] >= score_threshold:
                filter_documents.append(document)
        if not filter_documents:
            return []
        filter_documents = sorted(filter_documents, key=lambda x: x.metadata['score'], reverse=True)
        return filter_documents[:top_k] if top_k else filter_documents



