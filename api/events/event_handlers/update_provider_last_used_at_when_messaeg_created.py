from datetime import datetime

from core.entities.application_entities import ApplicationGenerateEntity
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
    # 从kwargs中获取application_generate_entity实例
    application_generate_entity: ApplicationGenerateEntity = kwargs.get('application_generate_entity')

    # 更新数据库中对应的Provider记录的last_used字段为当前时间
    db.session.query(Provider).filter(
        Provider.tenant_id == application_generate_entity.tenant_id,
        Provider.provider_name == application_generate_entity.app_orchestration_config_entity.model_config.provider
    ).update({'last_used': datetime.utcnow()})
    # 提交数据库事务
    db.session.commit()