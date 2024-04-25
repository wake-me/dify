from typing import Union

from core.app.entities.app_invoke_entities import ModelConfigWithCredentialsEntity
from core.model_manager import ModelInstance
from core.model_runtime.entities.message_entities import PromptMessageTool, SystemPromptMessage, UserPromptMessage


class FunctionCallMultiDatasetRouter:
    """
    多数据集调用函数路由器类。
    
    用于根据输入查询和可用的数据集工具列表，决定使用哪个数据集工具，并调用相应的模型。
    """

    def invoke(
            self,
            query: str,
            dataset_tools: list[PromptMessageTool],
            model_config: ModelConfigWithCredentialsEntity,
            model_instance: ModelInstance,

    ) -> Union[str, None]:
        """
        根据输入决定使用哪个数据集工具，并调用模型。
        
        参数:
            query: 用户的查询字符串。
            dataset_tools: 数据集工具列表，用于处理数据集。
            model_config: 包含模型认证信息的模型配置实体。
            model_instance: 模型实例，用于执行模型推理。
        
        返回:
            如果决定使用某个工具，则返回该工具的名称；如果没有适合的工具或发生异常，则返回None。
        """
        # 如果没有提供任何数据集工具，直接返回None
        if len(dataset_tools) == 0:
            return None
        # 如果只有一个数据集工具，直接返回该工具的名称
        elif len(dataset_tools) == 1:
            return dataset_tools[0].name

        try:
            # 准备提示消息，包括系统提示和用户查询
            prompt_messages = [
                SystemPromptMessage(content='You are a helpful AI assistant.'),
                UserPromptMessage(content=query)
            ]
            # 调用模型进行处理
            result = model_instance.invoke_llm(
                prompt_messages=prompt_messages,
                tools=dataset_tools,
                stream=False,
                model_parameters={
                    'temperature': 0.2,
                    'top_p': 0.3,
                    'max_tokens': 1500
                }
            )
            # 如果模型返回了工具调用信息，返回第一个工具的函数名称
            if result.message.tool_calls:
                return result.message.tool_calls[0].function.name
            # 如果没有返回工具调用信息，返回None
            return None
        except Exception as e:
            # 发生异常时返回None
            return None