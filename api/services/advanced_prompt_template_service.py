
import copy

from core.prompt.prompt_templates.advanced_prompt_templates import (
    BAICHUAN_CHAT_APP_CHAT_PROMPT_CONFIG,
    BAICHUAN_CHAT_APP_COMPLETION_PROMPT_CONFIG,
    BAICHUAN_COMPLETION_APP_CHAT_PROMPT_CONFIG,
    BAICHUAN_COMPLETION_APP_COMPLETION_PROMPT_CONFIG,
    BAICHUAN_CONTEXT,
    CHAT_APP_CHAT_PROMPT_CONFIG,
    CHAT_APP_COMPLETION_PROMPT_CONFIG,
    COMPLETION_APP_CHAT_PROMPT_CONFIG,
    COMPLETION_APP_COMPLETION_PROMPT_CONFIG,
    CONTEXT,
)
from models.model import AppMode


class AdvancedPromptTemplateService:
    """
    高级提示模板服务类，提供根据不同的应用模式、模型模式以及是否存在上下文信息，
    来动态获取并组装相应提示模板的方法。

    方法：
    - get_prompt：根据输入参数获取对应的提示信息
    - get_common_prompt：根据通用应用模式与模型模式获取提示信息
    - get_completion_prompt：针对 completion 模式获取提示信息，并可选择性添加上下文
    - get_chat_prompt：针对 chat 模式获取提示信息，并可选择性添加上下文
    - get_baichuan_prompt：针对“百川”模型获取特定的提示信息，处理逻辑同上但使用特定配置

    """
    
    @classmethod
    def get_prompt(cls, args: dict) -> dict:
        """
        根据提供的参数获取相应的提示信息。

        参数:
        - cls: 类的引用，用于调用类方法。
        - args: 字典类型，包含以下键:
        - app_mode: 应用模式。
        - model_mode: 模型模式。
        - model_name: 模型名称。
        - has_context: 是否有上下文。

        返回值:
        - 返回一个字典，包含特定于应用和模型的提示信息。
        """
        # 提取参数
        app_mode = args['app_mode']
        model_mode = args['model_mode']
        model_name = args['model_name']
        has_context = args['has_context']

        # 判断模型名称中是否包含"baichuan"，以决定使用哪种提示信息
        if 'baichuan' in model_name.lower():
            return cls.get_baichuan_prompt(app_mode, model_mode, has_context)  # 获取白川模型的特定提示
        else:
            return cls.get_common_prompt(app_mode, model_mode, has_context)  # 获取通用模型的提示

    @classmethod
    def get_common_prompt(cls, app_mode: str, model_mode:str, has_context: str) -> dict:
        """
        根据应用模式和模型模式获取通用的提示信息配置。

        参数:
        cls - 类的引用，用于调用类方法。
        app_mode - 字符串，表示应用的模式，例如聊天模式或完成模式。
        model_mode - 字符串，表示模型的模式，可以是完成模式或聊天模式。
        has_context - 字符串，表示是否有上下文。

        返回值:
        一个字典，包含所请求的提示信息配置。
        """
        context_prompt = copy.deepcopy(CONTEXT)  # 深拷贝全局上下文配置

        # 根据应用模式和模型模式选择相应的提示配置
        if app_mode == AppMode.CHAT.value:
            if model_mode == "completion":
                return cls.get_completion_prompt(copy.deepcopy(CHAT_APP_COMPLETION_PROMPT_CONFIG), has_context, context_prompt)
            elif model_mode == "chat":
                return cls.get_chat_prompt(copy.deepcopy(CHAT_APP_CHAT_PROMPT_CONFIG), has_context, context_prompt)
        elif app_mode == AppMode.COMPLETION.value:
            if model_mode == "completion":
                return cls.get_completion_prompt(copy.deepcopy(COMPLETION_APP_COMPLETION_PROMPT_CONFIG), has_context, context_prompt)
            elif model_mode == "chat":
                return cls.get_chat_prompt(copy.deepcopy(COMPLETION_APP_CHAT_PROMPT_CONFIG), has_context, context_prompt)
                
    @classmethod
    def get_completion_prompt(cls, prompt_template: dict, has_context: str, context: str) -> dict:
        """
        根据给定的上下文信息，更新完成提示模板。

        参数:
        cls - 类的引用，用于可能的类方法调用，但在此函数中未使用。
        prompt_template - 一个字典，包含了完成提示的模板配置。
        has_context - 一个字符串，表示是否有上下文信息。'true' 表示有上下文信息，'false' 表示没有。
        context - 一个字符串，包含了上下文信息。

        返回值:
        一个更新后的完成提示模板字典。
        """
        if has_context == 'true':
            # 如果存在上下文信息，则将上下文信息添加到完成提示的文本中
            prompt_template['completion_prompt_config']['prompt']['text'] = context + prompt_template['completion_prompt_config']['prompt']['text']
        
        return prompt_template

    @classmethod
    def get_chat_prompt(cls, prompt_template: dict, has_context: str, context: str) -> dict:
        """
        根据给定的提示模板和上下文信息，获取聊天提示的配置。

        参数:
        cls - 类的引用，用于可能的类方法调用，此处未使用。
        prompt_template - 包含聊天提示配置的字典。
        has_context - 字符串，表示是否有上下文信息。'true' 表示有上下文信息，'false' 表示没有。
        context - 上下文信息的字符串。

        返回值:
        包含更新后聊天提示配置的字典。
        """
        if has_context == 'true':
            # 如果有上下文信息，则将上下文信息添加到提示文本的开头
            prompt_template['chat_prompt_config']['prompt'][0]['text'] = context + prompt_template['chat_prompt_config']['prompt'][0]['text']
        
        return prompt_template

    @classmethod
    def get_baichuan_prompt(cls, app_mode: str, model_mode:str, has_context: str) -> dict:
        """
        获取白川模型的提示信息配置。

        参数:
        - cls: 类名，用于调用类方法。
        - app_mode: 应用模式，决定了是使用聊天应用还是完成应用的配置。
        - model_mode: 模型模式，指明了是完成模式还是聊天模式。
        - has_context: 是否有上下文，用于决定提示信息的具体内容。

        返回值:
        - dict: 包含特定模式下白川模型的提示信息配置的字典。
        """
        # 深拷贝白川通用上下文提示配置
        baichuan_context_prompt = copy.deepcopy(BAICHUAN_CONTEXT)

        # 根据应用模式和模型模式选择相应的提示配置并返回
        if app_mode == AppMode.CHAT.value:
            if model_mode == "completion":
                # 聊天应用下的完成模式提示配置
                return cls.get_completion_prompt(copy.deepcopy(BAICHUAN_CHAT_APP_COMPLETION_PROMPT_CONFIG), has_context, baichuan_context_prompt)
            elif model_mode == "chat":
                # 聊天应用下的聊天模式提示配置
                return cls.get_chat_prompt(copy.deepcopy(BAICHUAN_CHAT_APP_CHAT_PROMPT_CONFIG), has_context, baichuan_context_prompt)
        elif app_mode == AppMode.COMPLETION.value:
            if model_mode == "completion":
                # 完成应用下的完成模式提示配置
                return cls.get_completion_prompt(copy.deepcopy(BAICHUAN_COMPLETION_APP_COMPLETION_PROMPT_CONFIG), has_context, baichuan_context_prompt)
            elif model_mode == "chat":
                # 完成应用下的聊天模式提示配置
                return cls.get_chat_prompt(copy.deepcopy(BAICHUAN_COMPLETION_APP_CHAT_PROMPT_CONFIG), has_context, baichuan_context_prompt)