import logging
import time

from core.rag.datasource.retrieval_service import RetrievalService
from core.rag.models.document import Document
from core.rag.retrieval.retrival_methods import RetrievalMethod
from extensions.ext_database import db
from models.account import Account
from models.dataset import Dataset, DatasetQuery, DocumentSegment

# 默认的检索模型配置
default_retrieval_model = {
    'search_method': RetrievalMethod.SEMANTIC_SEARCH.value,
    'reranking_enable': False,
    'reranking_model': {
        'reranking_provider_name': '',
        'reranking_model_name': ''
    },
    'top_k': 2,  # 返回结果的数量，默认为2
    'score_threshold_enabled': False  # 是否启用得分阈值，默认不启用
}

class HitTestingService:
    @classmethod
    def retrieve(cls, dataset: Dataset, query: str, account: Account, retrieval_model: dict, limit: int = 10) -> dict:
        """
        根据提供的查询条件从数据集中检索记录。

        参数:
        - cls: 类的引用。
        - dataset: 数据集对象，用于检索的数据库集合。
        - query: 查询字符串，指定要检索的内容。
        - account: 账户对象，标识进行检索的账户。
        - retrieval_model: 检索模型字典，包含检索方法和其他相关配置。
        - limit: 检索结果的上限数量，默认为10。

        返回值:
        - 一个字典，包含查询结果和相关信息。
        """

        # 检查数据集可用文档和段落数量，若为0，则直接返回空记录列表
        if dataset.available_document_count == 0 or dataset.available_segment_count == 0:
            return {
                "query": {
                    "content": query,
                    "tsne_position": {'x': 0, 'y': 0},
                },
                "records": []
            }

        start = time.perf_counter()

        # 获取检索模型，未设置则使用默认模型
        if not retrieval_model:
            retrieval_model = dataset.retrieval_model if dataset.retrieval_model else default_retrieval_model

        all_documents = RetrievalService.retrieve(retrival_method=retrieval_model['search_method'],
                                                dataset_id=dataset.id,
                                                query=query,
                                                top_k=retrieval_model['top_k'],
                                                score_threshold=retrieval_model['score_threshold']
                                                if retrieval_model['score_threshold_enabled'] else None,
                                                reranking_model=retrieval_model['reranking_model']
                                                if retrieval_model['reranking_enable'] else None
                                                )

        end = time.perf_counter()
        # 记录检索执行时间
        logging.debug(f"Hit testing retrieve in {end - start:0.4f} seconds")

        # 将查询信息保存到数据库
        dataset_query = DatasetQuery(
            dataset_id=dataset.id,
            content=query,
            source='hit_testing',
            created_by_role='account',
            created_by=account.id
        )

        db.session.add(dataset_query)
        db.session.commit()

        return cls.compact_retrieve_response(dataset, query, all_documents)

    @classmethod
    def compact_retrieve_response(cls, dataset: Dataset, query: str, documents: list[Document]):
        i = 0
        records = []
        for document in documents:
            # 获取文档的元数据ID
            index_node_id = document.metadata['doc_id']

            # 查询文档段
            segment = db.session.query(DocumentSegment).filter(
                DocumentSegment.dataset_id == dataset.id,
                DocumentSegment.enabled == True,
                DocumentSegment.status == 'completed',
                DocumentSegment.index_node_id == index_node_id
            ).first()

            # 如果文档段不存在，则跳过当前文档
            if not segment:
                i += 1
                continue

            # 构建文档记录
            record = {
                "segment": segment,
                "score": document.metadata.get('score', None),
            }

            # 将文档记录添加到结果列表
            records.append(record)

            i += 1

        # 构建并返回检索响应
        return {
            "query": {
                "content": query,
            },
            "records": records
        }

    @classmethod
    def hit_testing_args_check(cls, args):
        """
        检查传入的参数是否符合hit testing的要求。
        
        参数:
        - cls: 通常表示类的引用，但在该函数中未使用，可以忽略。
        - args: 一个字典，必须包含'query'键，其值为待检测的查询字符串。
        
        返回值:
        - 无返回值，但会抛出ValueError异常，如果查询字符串为空或超过250个字符。
        """
        
        query = args['query']  # 提取查询字符串

        # 检查查询字符串是否为空或超过最大长度限制
        if not query or len(query) > 250:
            raise ValueError('Query is required and cannot exceed 250 characters')
