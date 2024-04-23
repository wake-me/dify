import logging
import random

from core.app.entities.app_invoke_entities import ModelConfigWithCredentialsEntity
from core.model_runtime.errors.invoke import InvokeBadRequestError
from core.model_runtime.model_providers.openai.moderation.moderation import OpenAIModerationModel
from extensions.ext_hosting_provider import hosting_configuration
from models.provider import ProviderType

logger = logging.getLogger(__name__)


def check_moderation(model_config: ModelConfigWithCredentialsEntity, text: str) -> bool:
    """
    检查提供的文本是否需要进行审核。
    
    :param model_config: 包含模型配置和认证信息的ModelConfigWithCredentialsEntity对象。
    :param text: 需要进行审核的文本字符串。
    :return: 布尔值，如果文本触发了审核条件，则返回True；否则返回False。
    """
    # 获取宿主服务的审核配置
    moderation_config = hosting_configuration.moderation_config
    # 检查是否启用了审核功能，以及是否配置了OpenAI提供者
    if (moderation_config and moderation_config.enabled is True
            and 'openai' in hosting_configuration.provider_map
            and hosting_configuration.provider_map['openai'].enabled is True
    ):
        # 获取模型配置的提供者类型和名称
        using_provider_type = model_config.provider_model_bundle.configuration.using_provider_type
        provider_name = model_config.provider
        # 检查是否使用了系统指定的提供者，并且该提供者在审核配置中被指定
        if using_provider_type == ProviderType.SYSTEM \
                and provider_name in moderation_config.providers:
            hosting_openai_config = hosting_configuration.provider_map['openai']

            # 将文本拆分成长度为2000字符的片段
            length = 2000
            text_chunks = [text[i:i + length] for i in range(0, len(text), length)]

            # 如果拆分后的文本片段为空，则直接返回True
            if len(text_chunks) == 0:
                return True

            # 随机选择一个文本片段进行审核
            text_chunk = random.choice(text_chunks)

            try:
                # 调用OpenAI审核模型进行文本审核
                model_type_instance = OpenAIModerationModel()
                moderation_result = model_type_instance.invoke(
                    model='text-moderation-stable',
                    credentials=hosting_openai_config.credentials,
                    text=text_chunk
                )

                # 如果审核结果为True，则返回True
                if moderation_result is True:
                    return True
            except Exception as ex:
                # 记录异常并抛出请求错误
                logger.exception(ex)
                raise InvokeBadRequestError('Rate limit exceeded, please try again later.')

    # 如果没有触发审核条件，则返回False
    return False
