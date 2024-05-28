from typing import cast

from core.model_runtime.entities.message_entities import (
    AssistantPromptMessage,
    ImagePromptMessageContent,
    PromptMessage,
    PromptMessageContentType,
    PromptMessageRole,
    TextPromptMessageContent,
)
from core.prompt.simple_prompt_transform import ModelMode


class PromptMessageUtil:
    @staticmethod
    def prompt_messages_to_prompt_for_saving(model_mode: str, prompt_messages: list[PromptMessage]) -> list[dict]:
        """
        将提示消息转换为保存所需的格式。
        :param model_mode: 模型模式
        :param prompt_messages: 提示消息列表
        :return: 转换后的提示信息列表，每个提示信息包括角色、文本和文件列表（如果存在）
        """
        prompts = []
        # 当模型模式为聊天模式时，处理每个提示消息
        if model_mode == ModelMode.CHAT.value:
            tool_calls = []
            for prompt_message in prompt_messages:
                # 根据消息角色，转换为对应的字符串表示
                if prompt_message.role == PromptMessageRole.USER:
                    role = 'user'
                elif prompt_message.role == PromptMessageRole.ASSISTANT:
                    role = 'assistant'
                    if isinstance(prompt_message, AssistantPromptMessage):
                        tool_calls = [{
                            'id': tool_call.id,
                            'type': 'function',
                            'function': {
                                'name': tool_call.function.name,
                                'arguments': tool_call.function.arguments,
                            }
                        } for tool_call in prompt_message.tool_calls]
                elif prompt_message.role == PromptMessageRole.SYSTEM:
                    role = 'system'
                elif prompt_message.role == PromptMessageRole.TOOL:
                    role = 'tool'
                else:
                    continue  # 跳过角色不识别的消息

                # 初始化文本和文件列表
                text = ''
                files = []
                # 处理消息内容，支持文本和图片类型
                if isinstance(prompt_message.content, list):
                    for content in prompt_message.content:
                        if content.type == PromptMessageContentType.TEXT:
                            content = cast(TextPromptMessageContent, content)
                            text += content.data
                        else:
                            content = cast(ImagePromptMessageContent, content)
                            files.append({
                                "type": 'image',
                                "data": content.data[:10] + '...[TRUNCATED]...' + content.data[-10:],
                                "detail": content.detail.value
                            })
                else:
                    text = prompt_message.content

                prompt = {
                    "role": role,
                    "text": text,
                    "files": files
                }
                
                if tool_calls:
                    prompt['tool_calls'] = tool_calls

                prompts.append(prompt)
        else:
            # 对于非聊天模式，只处理第一个提示消息
            prompt_message = prompt_messages[0]
            text = ''
            files = []
            # 同样，处理消息内容，支持文本和图片类型
            if isinstance(prompt_message.content, list):
                for content in prompt_message.content:
                    if content.type == PromptMessageContentType.TEXT:
                        content = cast(TextPromptMessageContent, content)
                        text += content.data
                    else:
                        content = cast(ImagePromptMessageContent, content)
                        files.append({
                            "type": 'image',
                            "data": content.data[:10] + '...[TRUNCATED]...' + content.data[-10:],
                            "detail": content.detail.value
                        })
            else:
                text = prompt_message.content

            # 构建包含角色、文本和文件的信息字典
            params = {
                "role": 'user',
                "text": text,
            }

            if files:
                params['files'] = files

            prompts.append(params)

        return prompts