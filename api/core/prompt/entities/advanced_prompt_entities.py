from typing import Literal, Optional

from pydantic import BaseModel

from core.model_runtime.entities.message_entities import PromptMessageRole


class ChatModelMessage(BaseModel):
    """
    聊天模型消息类。
    用于定义聊天消息的结构，包含消息文本和消息角色。

    属性:
    - text: str - 消息文本。
    - role: PromptMessageRole - 消息角色。
    """
    text: str
    role: PromptMessageRole
    edition_type: Optional[Literal['basic', 'jinja2']]

class CompletionModelPromptTemplate(BaseModel):
    """
    完成模型提示模板类。
    用于定义完成模型的提示模板，包含提示文本。

    属性:
    - text: str - 提示文本。
    """
    text: str
    edition_type: Optional[Literal['basic', 'jinja2']]

class MemoryConfig(BaseModel):
    """
    内存配置类。
    用于定义内存配置的结构，包括角色前缀和窗口配置。

    属性:
    - role_prefix: Optional[RolePrefix] - 角色前缀配置，可选。
    - window: WindowConfig - 窗口配置。
    """
    class RolePrefix(BaseModel):
        """
        角色前缀子类。
        用于定义用户和助手的角色前缀。

        属性:
        - user: str - 用户角色前缀。
        - assistant: str - 助手角色前缀。
        """
        user: str
        assistant: str

    class WindowConfig(BaseModel):
        """
        窗口配置子类。
        用于定义窗口是否启用以及窗口大小。

        属性:
        - enabled: bool - 窗口是否启用。
        - size: Optional[int] - 窗口大小，可选。
        """
        enabled: bool
        size: Optional[int] = None

    role_prefix: Optional[RolePrefix] = None
    window: WindowConfig
    query_prompt_template: Optional[str] = None
