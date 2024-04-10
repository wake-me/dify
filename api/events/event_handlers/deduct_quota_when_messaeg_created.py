from core.app.entities.app_invoke_entities import AgentChatAppGenerateEntity, ChatAppGenerateEntity
from core.entities.provider_entities import QuotaUnit
from events.message_event import message_was_created
from extensions.ext_database import db
from models.provider import Provider, ProviderType


@message_was_created.connect
def handle(sender, **kwargs):
    """
    当消息被创建时连接到此函数，用于处理消息创建事件。
    
    :param sender: 发送者对象，即创建消息的对象。
    :param **kwargs: 关键字参数，包含应用生成实体等额外信息。
    """
    message = sender
    application_generate_entity = kwargs.get('application_generate_entity')

    if not isinstance(application_generate_entity, ChatAppGenerateEntity | AgentChatAppGenerateEntity):
        return

    model_config = application_generate_entity.model_config
    provider_model_bundle = model_config.provider_model_bundle
    provider_configuration = provider_model_bundle.configuration

    # 检查是否使用系统提供商类型，如果不是，则不进行处理
    if provider_configuration.using_provider_type != ProviderType.SYSTEM:
        return

    system_configuration = provider_configuration.system_configuration

    # 查找当前配额单位和限制
    quota_unit = None
    for quota_configuration in system_configuration.quota_configurations:
        if quota_configuration.quota_type == system_configuration.current_quota_type:
            quota_unit = quota_configuration.quota_unit
            
            # 如果配额无限，则不进行处理
            if quota_configuration.quota_limit == -1:
                return

            break

    # 计算已使用的配额
    used_quota = None
    if quota_unit:
        if quota_unit == QuotaUnit.TOKENS:
            # 如果配额单位是TOKENS，则根据消息和答案的TOKEN数量计算使用量
            used_quota = message.message_tokens + message.answer_tokens
        elif quota_unit == QuotaUnit.CREDITS:
            # 如果配额单位是CREDITS，使用量默认为1，但如果模型是gpt-4，则使用量为20
            used_quota = 1
            if 'gpt-4' in model_config.model:
                used_quota = 20
        else:
            # 对于其他配额单位，默认使用量为1
            used_quota = 1

    # 更新配额使用情况
    if used_quota is not None:
        # 在数据库中更新配额使用情况
        db.session.query(Provider).filter(
            Provider.tenant_id == application_generate_entity.app_config.tenant_id,
            Provider.provider_name == model_config.provider,
            Provider.provider_type == ProviderType.SYSTEM.value,
            Provider.quota_type == system_configuration.current_quota_type.value,
            Provider.quota_limit > Provider.quota_used
        ).update({'quota_used': Provider.quota_used + used_quota})
        db.session.commit()