from typing import Optional

from core.agent.entities import AgentEntity, AgentPromptEntity, AgentToolEntity
from core.agent.prompt.template import REACT_PROMPT_TEMPLATES


class AgentConfigManager:
    @classmethod
    def convert(cls, config: dict) -> Optional[AgentEntity]:
        """
        将模型配置转换为代理实体配置。

        :param config: 模型配置参数，一个字典。
        :return: 根据配置生成的AgentEntity实例或None。
        """
        # 检查配置中是否定义了代理模式并启用
        if 'agent_mode' in config and config['agent_mode'] \
                and 'enabled' in config['agent_mode']:

            # 获取代理模式字典
            agent_dict = config.get('agent_mode', {})
            # 默认策略为cot（chain of thought）
            agent_strategy = agent_dict.get('strategy', 'cot')

            # 根据策略名称设置策略枚举
            if agent_strategy == 'function_call':
                strategy = AgentEntity.Strategy.FUNCTION_CALLING
            elif agent_strategy == 'cot' or agent_strategy == 'react':
                strategy = AgentEntity.Strategy.CHAIN_OF_THOUGHT
            else:
                # 旧配置尝试检测默认策略
                if config['model']['provider'] == 'openai':
                    strategy = AgentEntity.Strategy.FUNCTION_CALLING
                else:
                    strategy = AgentEntity.Strategy.CHAIN_OF_THOUGHT

            # 初始化代理工具列表
            agent_tools = []
            for tool in agent_dict.get('tools', []):
                keys = tool.keys()
                # 忽略未启用的工具
                if len(keys) >= 4:
                    if "enabled" not in tool or not tool["enabled"]:
                        continue

                    # 构建代理工具实体属性
                    agent_tool_properties = {
                        'provider_type': tool['provider_type'],
                        'provider_id': tool['provider_id'],
                        'tool_name': tool['tool_name'],
                        'tool_parameters': tool.get('tool_parameters', {})
                    }

                    # 添加代理工具实体到列表
                    agent_tools.append(AgentToolEntity(**agent_tool_properties))

            # 配置了特定策略时，处理代理提示信息
            if 'strategy' in config['agent_mode'] and \
                    config['agent_mode']['strategy'] not in ['react_router', 'router']:
                agent_prompt = agent_dict.get('prompt', None) or {}
                # 根据模型模式设置代理提示实体
                model_mode = config.get('model', {}).get('mode', 'completion')
                if model_mode == 'completion':
                    agent_prompt_entity = AgentPromptEntity(
                        first_prompt=agent_prompt.get('first_prompt',
                                                      REACT_PROMPT_TEMPLATES['english']['completion']['prompt']),
                        next_iteration=agent_prompt.get('next_iteration',
                                                        REACT_PROMPT_TEMPLATES['english']['completion'][
                                                            'agent_scratchpad']),
                    )
                else:
                    agent_prompt_entity = AgentPromptEntity(
                        first_prompt=agent_prompt.get('first_prompt',
                                                      REACT_PROMPT_TEMPLATES['english']['chat']['prompt']),
                        next_iteration=agent_prompt.get('next_iteration',
                                                        REACT_PROMPT_TEMPLATES['english']['chat']['agent_scratchpad']),
                    )

                # 返回代理实体
                return AgentEntity(
                    provider=config['model']['provider'],
                    model=config['model']['name'],
                    strategy=strategy,
                    prompt=agent_prompt_entity,
                    tools=agent_tools,
                    max_iteration=agent_dict.get('max_iteration', 5)
                )

        # 如果没有符合条件的配置，返回None
        return None
