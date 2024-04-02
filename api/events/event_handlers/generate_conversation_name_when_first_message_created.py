from core.generator.llm_generator import LLMGenerator
from events.message_event import message_was_created
from extensions.ext_database import db


@message_was_created.connect
def handle(sender, **kwargs):
    """
    当消息创建时连接到此函数，用于处理自动生成对话名称的逻辑。
    
    参数:
    - sender: 创建的消息对象。
    - **kwargs: 关键字参数，包括对话(conversation)、是否为第一条消息(is_first_message)、额外信息(extras)等。
    
    返回值:
    - 无。
    """
    message = sender
    conversation = kwargs.get('conversation')
    is_first_message = kwargs.get('is_first_message')
    extras = kwargs.get('extras', {})

    auto_generate_conversation_name = True
    # 判断是否自动生成对话名称
    if extras:
        auto_generate_conversation_name = extras.get('auto_generate_conversation_name', True)

    # 当且仅当为第一条消息且设置为自动生成对话名称时，尝试生成对话名称
    if auto_generate_conversation_name and is_first_message:
        if conversation.mode == 'chat':
            app_model = conversation.app
            if not app_model:
                return

            # 尝试根据应用模型和查询内容生成对话名称
            try:
                name = LLMGenerator.generate_conversation_name(app_model.tenant_id, message.query)
                conversation.name = name
            except:
                # 生成对话名称失败时，不做处理
                pass
                
            # 合并对话对象到会话并提交更改
            db.session.merge(conversation)
            db.session.commit()