from enum import Enum
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel


class AgentToolEntity(BaseModel):
    """
    Agent Tool Entity 类。
    代表一个代理工具实体，包含工具的基本信息和参数。
    """
    provider_type: Literal["builtin", "api", "workflow"]
    provider_id: str
    # 提供者的唯一标识符。
    tool_name: str
    # 工具的名称。
    tool_parameters: dict[str, Any] = {}
    # 工具的参数，以键值对形式存储。

class AgentPromptEntity(BaseModel):
    """
    Agent Prompt Entity 类。
    代表一个代理提示实体，包含首次提示和下一次迭代的提示信息。
    """

    first_prompt: str
    # 首次提示的信息。
    next_iteration: str
    # 下一次迭代的提示信息。

class AgentScratchpadUnit(BaseModel):
    """
    Agent Scratchpad Unit 类。
    代表代理的草稿垫单元，用于存储代理的动作、思考过程等信息。
    """

    class Action(BaseModel):
        """
        Action Entity 类。
        代表一个动作实体，包含动作名称和输入。
        """

        action_name: str
        # 动作的名称。
        action_input: Union[dict, str]
        # 动作的输入，可以是字典或字符串格式。

        def to_dict(self) -> dict:
            """
            将动作实体转换为字典格式。
            
            返回值:
            dict: 包含动作名称和输入的字典。
            """

            return {
                'action': self.action_name,
                'action_input': self.action_input,
            }

    agent_response: Optional[str] = None
    # 代理的响应信息。
    thought: Optional[str] = None
    # 代理的思考过程。
    action_str: Optional[str] = None
    # 动作的字符串表示。
    observation: Optional[str] = None
    # 观察结果。
    action: Optional[Action] = None
    # 动作实体。

    def is_final(self) -> bool:
        """
        判断草稿垫单元是否为最终单元。
        
        返回值:
        bool: 如果单元为最终单元，则返回True，否则返回False。
        """
        return self.action is None or (
            'final' in self.action.action_name.lower() and 
            'answer' in self.action.action_name.lower()
        )

class AgentEntity(BaseModel):
    """
    Agent Entity 类。
    代表一个代理实体，包含代理的基本信息、策略、提示信息和工具等。
    """

    class Strategy(Enum):
        """
        Agent Strategy 枚举类。
        定义了代理的策略类型，包括链式思考和函数调用。
        """

        CHAIN_OF_THOUGHT = 'chain-of-thought'
        # 链式思考策略。
        FUNCTION_CALLING = 'function-calling'
        # 函数调用策略。

    provider: str
    # 代理提供者。
    model: str
    # 代理模型。
    strategy: Strategy
    # 代理的策略类型。
    prompt: Optional[AgentPromptEntity] = None
    # 代理的提示信息实体。
    tools: list[AgentToolEntity] = None
    # 代理使用的工具实体列表。
    max_iteration: int = 5
    # 代理的最大迭代次数。