from core.app.app_config.features.file_upload.manager import FileUploadConfigManager
from core.file.message_file_parser import MessageFileParser
from core.model_manager import ModelInstance
from core.model_runtime.entities.message_entities import (
    AssistantPromptMessage,
    ImagePromptMessageContent,
    PromptMessage,
    PromptMessageRole,
    TextPromptMessageContent,
    UserPromptMessage,
)
from extensions.ext_database import db
from models.model import AppMode, Conversation, Message


class TokenBufferMemory:
    def __init__(self, conversation: Conversation, model_instance: ModelInstance) -> None:
        """
        初始化TokenBufferMemory类的实例。
        :param conversation: 对话对象，用于获取对话相关数据。
        :param model_instance: 模型实例，用于与特定的模型交互。
        """
        self.conversation = conversation
        self.model_instance = model_instance

    def get_history_prompt_messages(self, max_token_limit: int = 2000,
                                    message_limit: int = 10) -> list[PromptMessage]:
        """
        获取历史提示消息。
        :param max_token_limit: 最大令牌限制，用于控制消息数量以避免超出模型处理能力。
        :param message_limit: 消息限制，用于控制获取的历史消息数量。
        :return: 返回过滤和处理后的提示消息列表。
        """
        app_record = self.conversation.app

        # 从数据库查询限定数量的非空消息，并按创建时间倒序处理
        messages = db.session.query(Message).filter(
            Message.conversation_id == self.conversation.id,
            Message.answer != ''
        ).order_by(Message.created_at.desc()).limit(message_limit).all()

        messages = list(reversed(messages))
        message_file_parser = MessageFileParser(
            tenant_id=app_record.tenant_id,
            app_id=app_record.id
        )

        prompt_messages = []
        for message in messages:
            files = message.message_files
            # 根据对话模式处理文件配置
            if files:
                if self.conversation.mode not in [AppMode.ADVANCED_CHAT.value, AppMode.WORKFLOW.value]:
                    file_extra_config = FileUploadConfigManager.convert(message.app_model_config.to_dict())
                else:
                    file_extra_config = FileUploadConfigManager.convert(
                        message.workflow_run.workflow.features_dict,
                        is_vision=False
                    )

                # 文件处理与消息构建
                if file_extra_config:
                    file_objs = message_file_parser.transform_message_files(
                        files,
                        file_extra_config
                    )
                else:
                    file_objs = []

                if not file_objs:
                    prompt_messages.append(UserPromptMessage(content=message.query))
                else:
                    prompt_message_contents = [TextPromptMessageContent(data=message.query)]
                    for file_obj in file_objs:
                        prompt_message_contents.append(file_obj.prompt_message_content)

                    prompt_messages.append(UserPromptMessage(content=prompt_message_contents))
            else:
                prompt_messages.append(UserPromptMessage(content=message.query))

            # 添加助手回复消息
            prompt_messages.append(AssistantPromptMessage(content=message.answer))

        if not prompt_messages:
            return []

        # prune the chat message if it exceeds the max token limit
        curr_message_tokens = self.model_instance.get_llm_num_tokens(
            prompt_messages
        )

        if curr_message_tokens > max_token_limit:
            pruned_memory = []
            # 从消息列表前端开始删除，直到令牌数符合限制或消息列表为空
            while curr_message_tokens > max_token_limit and prompt_messages:
                pruned_memory.append(prompt_messages.pop(0))
                curr_message_tokens = self.model_instance.get_llm_num_tokens(
                    prompt_messages
                )

        return prompt_messages

    def get_history_prompt_text(self, human_prefix: str = "Human",
                                ai_prefix: str = "Assistant",
                                max_token_limit: int = 2000,
                                message_limit: int = 10) -> str:
        """
        获取历史对话提示文本。
        :param human_prefix: 人类前缀，默认为 "Human"
        :param ai_prefix: AI前缀，默认为 "Assistant"
        :param max_token_limit: 最大令牌限制，默认为 2000
        :param message_limit: 消息限制，默认为 10
        :return: 返回格式化后的对话历史文本字符串
        """
        # 获取历史对话消息
        prompt_messages = self.get_history_prompt_messages(
            max_token_limit=max_token_limit,
            message_limit=message_limit
        )

        string_messages = []
        for m in prompt_messages:
            # 根据消息角色分配前缀
            if m.role == PromptMessageRole.USER:
                role = human_prefix
            elif m.role == PromptMessageRole.ASSISTANT:
                role = ai_prefix
            else:
                continue  # 跳过非用户和AI的消息

            # 处理消息内容，支持文本和图片类型
            if isinstance(m.content, list):
                inner_msg = ""
                for content in m.content:
                    if isinstance(content, TextPromptMessageContent):
                        inner_msg += f"{content.data}\n"
                    elif isinstance(content, ImagePromptMessageContent):
                        inner_msg += "[image]\n"

                string_messages.append(f"{role}: {inner_msg.strip()}")
            else:
                message = f"{role}: {m.content}"
                string_messages.append(message)

        return "\n".join(string_messages)