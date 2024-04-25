import base64
import copy
import time
from typing import Optional, Union

import numpy as np
import tiktoken
from openai import AzureOpenAI

from core.model_runtime.entities.model_entities import AIModelEntity, PriceType
from core.model_runtime.entities.text_embedding_entities import EmbeddingUsage, TextEmbeddingResult
from core.model_runtime.errors.validate import CredentialsValidateFailedError
from core.model_runtime.model_providers.__base.text_embedding_model import TextEmbeddingModel
from core.model_runtime.model_providers.azure_openai._common import _CommonAzureOpenAI
from core.model_runtime.model_providers.azure_openai._constant import EMBEDDING_BASE_MODELS, AzureBaseModel


class AzureOpenAITextEmbeddingModel(_CommonAzureOpenAI, TextEmbeddingModel):

    def _invoke(self, model: str, credentials: dict,
                texts: list[str], user: Optional[str] = None) \
            -> TextEmbeddingResult:
        """
        调用指定的模型，为输入的文本列表生成文本嵌入结果。
        
        :param model: 模型名称，指定使用的文本嵌入模型。
        :param credentials: 包含模型认证信息的字典。
        :param texts: 待处理的文本列表。
        :param user: 可选参数，指定用户的标识。
        :return: 返回一个包含文本嵌入结果、使用情况和模型名称的TextEmbeddingResult对象。
        """
        # 根据认证信息初始化Azure OpenAI客户端
        base_model_name = credentials['base_model_name']
        credentials_kwargs = self._to_credential_kwargs(credentials)
        client = AzureOpenAI(**credentials_kwargs)

        # 准备额外的模型调用参数
        extra_model_kwargs = {}
        if user:
            extra_model_kwargs['user'] = user
        extra_model_kwargs['encoding_format'] = 'base64'

        # 根据模型和认证信息确定上下文大小和最大分批大小
        context_size = self._get_context_size(model, credentials)
        max_chunks = self._get_max_chunks(model, credentials)

        # 初始化嵌入列表、标记列表、索引列表和已使用的标记数
        embeddings: list[list[float]] = [[] for _ in range(len(texts))]
        tokens = []
        indices = []
        used_tokens = 0

        # 尝试获取模型的编码方式
        try:
            enc = tiktoken.encoding_for_model(base_model_name)
        except KeyError:
            enc = tiktoken.get_encoding("cl100k_base")

        # 对每个文本进行编码，并分割为合适大小的块
        for i, text in enumerate(texts):
            token = enc.encode(
                text
            )
            for j in range(0, len(token), context_size):
                tokens += [token[j: j + context_size]]
                indices += [i]

        # 批量获取嵌入向量
        batched_embeddings = []
        _iter = range(0, len(tokens), max_chunks)

        for i in _iter:
            embeddings_batch, embedding_used_tokens = self._embedding_invoke(
                model=model,
                client=client,
                texts=tokens[i: i + max_chunks],
                extra_model_kwargs=extra_model_kwargs
            )

            used_tokens += embedding_used_tokens
            batched_embeddings += embeddings_batch

        # 根据原始索引组织嵌入向量和每个文本的标记数
        results: list[list[list[float]]] = [[] for _ in range(len(texts))]
        num_tokens_in_batch: list[list[int]] = [[] for _ in range(len(texts))]
        for i in range(len(indices)):
            results[indices[i]].append(batched_embeddings[i])
            num_tokens_in_batch[indices[i]].append(len(tokens[i]))

        # 计算每个文本的平均嵌入向量
        for i in range(len(texts)):
            _result = results[i]
            if len(_result) == 0:
                embeddings_batch, embedding_used_tokens = self._embedding_invoke(
                    model=model,
                    client=client,
                    texts="",
                    extra_model_kwargs=extra_model_kwargs
                )

                used_tokens += embedding_used_tokens
                average = embeddings_batch[0]
            else:
                average = np.average(_result, axis=0, weights=num_tokens_in_batch[i])
            embeddings[i] = (average / np.linalg.norm(average)).tolist()

        # 计算使用情况
        usage = self._calc_response_usage(
            model=model,
            credentials=credentials,
            tokens=used_tokens
        )

        # 返回嵌入结果、使用情况和模型名称
        return TextEmbeddingResult(
            embeddings=embeddings,
            usage=usage,
            model=base_model_name
        )

    def get_num_tokens(self, model: str, credentials: dict, texts: list[str]) -> int:
        """
        计算给定文本列表中所有文本的令牌总数。
        
        参数:
        model: 字符串，指定用于编码的模型名称。
        credentials: 字典，包含模型基础名称的凭证信息。
        texts: 字符串列表，待计算令牌数的文本列表。
        
        返回值:
        整数，所有文本中令牌的总数量。
        """
        if len(texts) == 0:  # 如果文本列表为空，直接返回0
            return 0

        try:
            enc = tiktoken.encoding_for_model(credentials['base_model_name'])  # 尝试根据凭证信息获取模型的编码器
        except KeyError:
            enc = tiktoken.get_encoding("cl100k_base")  # 如果凭证信息中无基础模型名称，使用默认编码器

        total_num_tokens = 0
        for text in texts:
            # 对每段文本进行编码并计算令牌数，累加到总数中
            tokenized_text = enc.encode(text)
            total_num_tokens += len(tokenized_text)

        return total_num_tokens

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        验证提供的凭证信息是否有效。

        参数:
        - model: 字符串，指定要使用的模型名称。
        - credentials: 字典，包含访问所需的各种凭证信息。

        返回值:
        - 无。如果验证失败，将抛出 CredentialsValidateFailedError 异常。
        """
        # 检查必需的凭证信息是否存在
        if 'openai_api_base' not in credentials:
            raise CredentialsValidateFailedError('Azure OpenAI API Base Endpoint is required')

        if 'openai_api_key' not in credentials:
            raise CredentialsValidateFailedError('Azure OpenAI API key is required')

        if 'base_model_name' not in credentials:
            raise CredentialsValidateFailedError('Base Model Name is required')

        # 验证基础模型名称的有效性
        if not self._get_ai_model_entity(credentials['base_model_name'], model):
            raise CredentialsValidateFailedError(f'Base Model Name {credentials["base_model_name"]} is invalid')

        try:
            # 准备凭证参数，并创建 AzureOpenAI 客户端
            credentials_kwargs = self._to_credential_kwargs(credentials)
            client = AzureOpenAI(**credentials_kwargs)

            # 使用提供的模型和客户端进行简单的调用以验证凭证有效性
            self._embedding_invoke(
                model=model,
                client=client,
                texts=['ping'],
                extra_model_kwargs={}
            )
        except Exception as ex:
            # 如果在验证过程中出现任何异常，则抛出凭证验证失败异常
            raise CredentialsValidateFailedError(str(ex))

    def get_customizable_model_schema(self, model: str, credentials: dict) -> Optional[AIModelEntity]:
        """
        获取可定制模型的架构。

        参数:
        model (str): 模型名称。
        credentials (dict): 凭证信息，需要包含基础模型名称。

        返回:
        Optional[AIModelEntity]: 如果找到对应模型，返回 AIModelEntity 实例；否则返回 None。
        """
        # 根据提供的凭证信息获取 AI 模型实体
        ai_model_entity = self._get_ai_model_entity(credentials['base_model_name'], model)
        return ai_model_entity.entity

    @staticmethod
    def _embedding_invoke(model: str, client: AzureOpenAI, texts: Union[list[str], str],
                        extra_model_kwargs: dict) -> tuple[list[list[float]], int]:
        """
        调用Azure OpenAI服务，为给定的文本生成嵌入表示。

        参数:
        - model: 指定使用的模型名称或路径。
        - client: AzureOpenAI的客户端实例，用于与服务进行交互。
        - texts: 需要进行嵌入处理的文本，可以是单个字符串或字符串列表。
        - extra_model_kwargs: 传递给模型的额外参数字典，例如嵌入格式。

        返回值:
        - 一个元组，包含嵌入列表和处理的总tokens数。嵌入列表中的每个项都是浮点数列表。
        """
        # 创建嵌入
        response = client.embeddings.create(
            input=texts,
            model=model,
            **extra_model_kwargs,
        )

        if 'encoding_format' in extra_model_kwargs and extra_model_kwargs['encoding_format'] == 'base64':
            # 如果指定编码格式为base64，则解码嵌入数据
            return ([list(np.frombuffer(base64.b64decode(data.embedding), dtype="float32")) for data in response.data],
                    response.usage.total_tokens)

        # 默认返回未经过解码的嵌入数据和总tokens数
        return [data.embedding for data in response.data], response.usage.total_tokens

    def _calc_response_usage(self, model: str, credentials: dict, tokens: int) -> EmbeddingUsage:
        """
        计算并返回嵌入使用情况的详细信息。

        参数:
        model: str - 使用的模型名称。
        credentials: dict - 访问模型所需的认证信息。
        tokens: int - 请求的嵌入令牌数量。

        返回值:
        EmbeddingUsage - 包含使用情况详情的对象，如令牌数量、总价格、单位价格等。
        """
        # 获取输入价格信息
        input_price_info = self.get_price(
            model=model,
            credentials=credentials,
            price_type=PriceType.INPUT,
            tokens=tokens
        )

        # 根据获取的价格信息，构造嵌入使用情况对象
        usage = EmbeddingUsage(
            tokens=tokens,
            total_tokens=tokens,
            unit_price=input_price_info.unit_price,
            price_unit=input_price_info.unit,
            total_price=input_price_info.total_amount,
            currency=input_price_info.currency,
            latency=time.perf_counter() - self.started_at  # 计算延迟时间
        )

        return usage

    @staticmethod
    def _get_ai_model_entity(base_model_name: str, model: str) -> AzureBaseModel:
        """
        根据基础模型名称和模型名称获取AI模型实体。
        
        参数:
        - base_model_name: str，基础模型的名称。
        - model: str，模型的名称。
        
        返回值:
        - AzureBaseModel，如果找到匹配的基础模型实体，则返回修改后的实体副本；否则返回None。
        """
        # 遍历所有嵌入式基础模型实体，查找匹配的基础模型名称
        for ai_model_entity in EMBEDDING_BASE_MODELS:
            if ai_model_entity.base_model_name == base_model_name:
                # 如果找到匹配项，创建该实体的深拷贝
                ai_model_entity_copy = copy.deepcopy(ai_model_entity)
                # 更新模型和标签信息
                ai_model_entity_copy.entity.model = model
                ai_model_entity_copy.entity.label.en_US = model
                ai_model_entity_copy.entity.label.zh_Hans = model
                # 返回更新后的实体副本
                return ai_model_entity_copy

        # 如果没有找到匹配的基础模型名称，返回None
        return None
