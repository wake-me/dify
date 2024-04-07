import logging
import time

import numpy as np
from sklearn.manifold import TSNE

from core.embedding.cached_embedding import CacheEmbedding
from core.model_manager import ModelManager
from core.model_runtime.entities.model_entities import ModelType
from core.rag.datasource.entity.embedding import Embeddings
from core.rag.datasource.retrieval_service import RetrievalService
from core.rag.models.document import Document
from extensions.ext_database import db
from models.account import Account
from models.dataset import Dataset, DatasetQuery, DocumentSegment

# 默认的检索模型配置
default_retrieval_model = {
    'search_method': 'semantic_search',  # 检索方法，默认为语义搜索
    'reranking_enable': False,  # 是否启用重排，默认不启用
    'reranking_model': {  # 重排模型的配置
        'reranking_provider_name': '',  # 重排模型提供者的名称
        'reranking_model_name': ''  # 重排模型的名称
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

        # 获取嵌入模型
        model_manager = ModelManager()
        embedding_model = model_manager.get_model_instance(
            tenant_id=dataset.tenant_id,
            model_type=ModelType.TEXT_EMBEDDING,
            provider=dataset.embedding_model_provider,
            model=dataset.embedding_model
        )

        embeddings = CacheEmbedding(embedding_model)

        # 使用指定的检索模型从数据集中检索文档
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

        # 生成并返回紧凑的检索响应
        return cls.compact_retrieve_response(dataset, embeddings, query, all_documents)

    @classmethod
    def compact_retrieve_response(cls, dataset: Dataset, embeddings: Embeddings, query: str, documents: list[Document]):
        """
        对给定的查询和文档集合，使用嵌入表示和TSNE算法获取查询和文档的紧凑检索响应。
        
        :param cls: 调用此方法的类，用于调用类方法 get_tsne_positions_from_embeddings。
        :param dataset: 数据集对象，用于查询文档段。
        :param embeddings: 嵌入模型，用于生成查询和文档的嵌入表示。
        :param query: 查询字符串，用于生成查询的嵌入表示。
        :param documents: 文档列表，每个文档包含页面内容和元数据。
        :return: 包含查询和相关文档记录的字典，其中每条记录包括文档段、得分和TSNE位置。
        """
        # 生成查询的嵌入表示
        text_embeddings = [
            embeddings.embed_query(query)
        ]

        # 生成文档的嵌入表示
        text_embeddings.extend(embeddings.embed_documents([document.page_content for document in documents]))

        # 从嵌入表示中获取TSNE位置数据
        tsne_position_data = cls.get_tsne_positions_from_embeddings(text_embeddings)

        # 获取查询的TSNE位置
        query_position = tsne_position_data.pop(0)

        # 初始化索引和记录列表
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
                "tsne_position": tsne_position_data[i]
            }

            # 将文档记录添加到结果列表
            records.append(record)

            i += 1

        # 构建并返回检索响应
        return {
            "query": {
                "content": query,
                "tsne_position": query_position,
            },
            "records": records
        }

    @classmethod
    def get_tsne_positions_from_embeddings(cls, embeddings: list):
        """
        从嵌入列表中获取t-SNE位置数据。
        
        参数:
        - embeddings: 嵌入列表，每个嵌入是一个向量。
        
        返回值:
        - tsne_position_data: 包含t-SNE位置的列表，每个位置是一个包含 'x' 和 'y' 键的字典。
        """
        embedding_length = len(embeddings)
        # 如果嵌入数量小于等于1，则直接返回原点位置
        if embedding_length <= 1:
            return [{'x': 0, 'y': 0}]

        # 向嵌入数据中添加少量噪声，防止数据点完全重合
        noise = np.random.normal(0, 1e-4, np.array(embeddings).shape)
        concatenate_data = np.array(embeddings) + noise
        # 将嵌入数据调整为合适的形状以供t-SNE处理
        concatenate_data = concatenate_data.reshape(embedding_length, -1)

        # 根据嵌入数量动态调整t-SNE的perplexity值
        perplexity = embedding_length / 2 + 1
        # 避免perplexity值过大或等于嵌入数量
        if perplexity >= embedding_length:
            perplexity = max(embedding_length - 1, 1)

        # 初始化t-SNE模型并应用到嵌入数据上
        tsne = TSNE(n_components=2, perplexity=perplexity, early_exaggeration=12.0)
        data_tsne = tsne.fit_transform(concatenate_data)

        # 将t-SNE转换结果转换为字典列表，便于后续处理和使用
        tsne_position_data = []
        for i in range(len(data_tsne)):
            tsne_position_data.append({'x': float(data_tsne[i][0]), 'y': float(data_tsne[i][1])})

        return tsne_position_data

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
