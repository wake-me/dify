from datetime import datetime, timezone

from core.app.entities.app_invoke_entities import AgentChatAppGenerateEntity, ChatAppGenerateEntity
from events.message_event import message_was_created
from extensions.ext_database import db
from models.provider import Provider


@message_was_created.connect
def handle(sender, **kwargs):
    """
    当消息被创建时连接到handle函数。
    
    参数:
    - sender: 创建消息的实体。
    - **kwargs: 关键字参数，包括'application_generate_entity'等。
    
    返回值: 无。
    """
    message = sender
    application_generate_entity = kwargs.get('application_generate_entity')

    if not isinstance(application_generate_entity, ChatAppGenerateEntity | AgentChatAppGenerateEntity):
        return

    # 更新数据库中对应的Provider记录的last_used字段为当前时间
    db.session.query(Provider).filter(
        Provider.tenant_id == application_generate_entity.app_config.tenant_id,
        Provider.provider_name == application_generate_entity.model_conf.provider
    ).update({'last_used': datetime.now(timezone.utc).replace(tzinfo=None)})
    db.session.commit()