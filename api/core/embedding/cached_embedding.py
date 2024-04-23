import base64
import logging
from typing import Optional, cast

import numpy as np
from sqlalchemy.exc import IntegrityError

from core.model_manager import ModelInstance
from core.model_runtime.entities.model_entities import ModelPropertyKey
from core.model_runtime.model_providers.__base.text_embedding_model import TextEmbeddingModel
from core.rag.datasource.entity.embedding import Embeddings
from extensions.ext_database import db
from extensions.ext_redis import redis_client
from libs import helper
from models.dataset import Embedding

logger = logging.getLogger(__name__)


class CacheEmbedding(Embeddings):
    """
    一个用于缓存嵌入的类，继承自Embeddings。

    参数:
    - model_instance: ModelInstance对象，表示要使用的模型实例。
    - user: 可选的字符串，表示执行嵌入的用户。

    返回:
    - 无
    """

    def __init__(self, model_instance: ModelInstance, user: Optional[str] = None) -> None:
        """
        初始化CacheEmbedding对象。

        参数:
        - model_instance: 要使用的模型实例。
        - user: 执行嵌入的用户，默认为None。

        返回:
        - 无
        """
        self._model_instance = model_instance
        self._user = user

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """
        批量嵌入搜索文档。
        
        参数:
        - texts: 包含待嵌入文本的列表。
        
        返回值:
        - 返回一个嵌入向量列表，每个嵌入向量以浮点数列表的形式表示。
        """

        # 初始化文本嵌入列表和待嵌入队列索引
        text_embeddings = [None for _ in range(len(texts))]
        embedding_queue_indices = []
        for i, text in enumerate(texts):
            # 尝试从数据库中获取已存在的嵌入向量
            hash = helper.generate_text_hash(text)
            embedding = db.session.query(Embedding).filter_by(model_name=self._model_instance.model,
                                                            hash=hash,
                                                            provider_name=self._model_instance.provider).first()
            if embedding:
                text_embeddings[i] = embedding.get_embedding()
            else:
                embedding_queue_indices.append(i)
        
        if embedding_queue_indices:
            # 对未嵌入的文本进行嵌入处理
            embedding_queue_texts = [texts[i] for i in embedding_queue_indices]
            embedding_queue_embeddings = []
            try:
                # 获取模型实例和模型架构，用于后续嵌入计算
                model_type_instance = cast(TextEmbeddingModel, self._model_instance.model_type_instance)
                model_schema = model_type_instance.get_model_schema(self._model_instance.model,
                                                                    self._model_instance.credentials)
                max_chunks = model_schema.model_properties[ModelPropertyKey.MAX_CHUNKS] \
                    if model_schema and ModelPropertyKey.MAX_CHUNKS in model_schema.model_properties else 1
                
                # 批量处理文本嵌入
                for i in range(0, len(embedding_queue_texts), max_chunks):
                    batch_texts = embedding_queue_texts[i:i + max_chunks]

                    embedding_result = self._model_instance.invoke_text_embedding(
                        texts=batch_texts,
                        user=self._user
                    )

                    # 对嵌入结果进行标准化处理，并存储
                    for vector in embedding_result.embeddings:
                        try:
                            normalized_embedding = (vector / np.linalg.norm(vector)).tolist()
                            embedding_queue_embeddings.append(normalized_embedding)
                        except IntegrityError:
                            db.session.rollback()
                        except Exception as e:
                            logging.exception('Failed transform embedding: ', e)
                # 将新嵌入的向量缓存到数据库
                cache_embeddings = []
                try:
                    for i, embedding in zip(embedding_queue_indices, embedding_queue_embeddings):
                        text_embeddings[i] = embedding
                        hash = helper.generate_text_hash(texts[i])
                        if hash not in cache_embeddings:
                            embedding_cache = Embedding(model_name=self._model_instance.model,
                                                        hash=hash,
                                                        provider_name=self._model_instance.provider)
                            embedding_cache.set_embedding(embedding)
                            db.session.add(embedding_cache)
                            cache_embeddings.append(hash)
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
            except Exception as ex:
                db.session.rollback()
                logger.error('Failed to embed documents: ', ex)
                raise ex

        return text_embeddings

    def embed_query(self, text: str) -> list[float]:
        """
        将查询文本嵌入到向量空间中。
        
        参数:
        text: str - 需要进行嵌入的文本字符串。
        
        返回值:
        list[float] - 文本的嵌入向量表示，以浮点数列表形式返回。
        """
        # 生成文本的哈希值，用作嵌入缓存的键
        hash = helper.generate_text_hash(text)
        embedding_cache_key = f'{self._model_instance.provider}_{self._model_instance.model}_{hash}'
        # 尝试从Redis缓存中获取嵌入向量，如果存在，则更新其过期时间并返回
        embedding = redis_client.get(embedding_cache_key)
        if embedding:
            redis_client.expire(embedding_cache_key, 600)
            return list(np.frombuffer(base64.b64decode(embedding), dtype="float"))
        try:
            # 如果缓存中不存在，通过模型实例计算嵌入向量
            embedding_result = self._model_instance.invoke_text_embedding(
                texts=[text],
                user=self._user
            )
            
            embedding_results = embedding_result.embeddings[0]
            # 归一化嵌入向量
            embedding_results = (embedding_results / np.linalg.norm(embedding_results)).tolist()
        except Exception as ex:
            raise ex

        try:
            # 将嵌入向量编码为Base64格式，存储到Redis缓存中
            embedding_vector = np.array(embedding_results)
            vector_bytes = embedding_vector.tobytes()
            encoded_vector = base64.b64encode(vector_bytes)
            encoded_str = encoded_vector.decode("utf-8")
            redis_client.setex(embedding_cache_key, 600, encoded_str)
        except IntegrityError:
            db.session.rollback()
        except:
            logging.exception('Failed to add embedding to redis')

        return embedding_results
