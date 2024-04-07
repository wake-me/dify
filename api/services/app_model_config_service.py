import re
import uuid

from core.entities.agent_entities import PlanningStrategy
from core.external_data_tool.factory import ExternalDataToolFactory
from core.model_runtime.entities.model_entities import ModelPropertyKey, ModelType
from core.model_runtime.model_providers import model_provider_factory
from core.moderation.factory import ModerationFactory
from core.prompt.prompt_transform import AppMode
from core.provider_manager import ProviderManager
from models.account import Account
from services.dataset_service import DatasetService

SUPPORT_TOOLS = ["dataset", "google_search", "web_reader", "wikipedia", "current_datetime"]


class AppModelConfigService:
    @classmethod
    def is_dataset_exists(cls, account: Account, dataset_id: str) -> bool:
        """
        检查给定的数据库集是否存在于指定账户下。
        
        参数:
        - cls: 类的引用，用于可能的类方法调用，但在此上下文中未使用。
        - account: Account类型，表示当前的用户账户。
        - dataset_id: 字符串，指定要查询的数据库集的ID。
        
        返回值:
        - bool: 如果数据库集存在且属于指定账户的当前租户，则返回True；否则返回False。
        """
        # 根据dataset_id获取数据库集信息
        dataset = DatasetService.get_dataset(dataset_id)

        if not dataset:
            return False  # 数据库集不存在

        if dataset.tenant_id != account.current_tenant_id:
            return False  # 数据库集不属于当前租户

        return True  # 数据库集存在且属于当前租户

    @classmethod
    def validate_model_completion_params(cls, cp: dict, model_name: str) -> dict:
        """
        验证模型完成参数的合法性。

        参数:
        - cls: 类的引用，用于可能的类方法调用，但在此函数中未使用。
        - cp: 一个字典，包含模型的完成参数。
        - model_name: 模型的名称，用于可能的错误消息，但在此函数中未使用。

        返回值:
        - 通过验证的参数字典。

        抛出:
        - ValueError: 如果参数不符合要求，则抛出此异常。
        """
        # 验证cp是否为字典类型
        if not isinstance(cp, dict):
            raise ValueError("model.completion_params must be of object type")

        # 验证并设置stop参数
        if 'stop' not in cp:
            cp["stop"] = []
        elif not isinstance(cp["stop"], list):
            raise ValueError("stop in model.completion_params must be of list type")

        # 确保stop列表长度小于等于4
        if len(cp["stop"]) > 4:
            raise ValueError("stop sequences must be less than 4")

        return cp

    @classmethod
    def validate_configuration(cls, tenant_id: str, account: Account, config: dict, app_mode: str) -> dict:
        """
        验证并配置应用模式的参数。

        参数:
        - cls: 类名，用于调用类方法进行进一步的验证。
        - tenant_id: 租户ID，用于标识应用的租户。
        - account: 账户对象，包含与账户相关的信息，用于验证数据权限等。
        - config: 字典，包含应用模式的配置信息。
        - app_mode: 字符串，表示应用的模式。

        返回值:
        - 配置信息的字典，经过验证和必要的填充后。

        验证config字典中的各项配置，确保其完整性和正确性，并根据需要填充默认值。
        """

        # 验证并设置'opening_statement'配置
        if 'opening_statement' not in config or not config["opening_statement"]:
            config["opening_statement"] = ""

        if not isinstance(config["opening_statement"], str):
            raise ValueError("opening_statement must be of string type")

        # 验证并设置'suggested_questions'配置
        if 'suggested_questions' not in config or not config["suggested_questions"]:
            config["suggested_questions"] = []

        if not isinstance(config["suggested_questions"], list):
            raise ValueError("suggested_questions must be of list type")

        for question in config["suggested_questions"]:
            if not isinstance(question, str):
                raise ValueError("Elements in suggested_questions list must be of string type")

        # 验证并设置'suggested_questions_after_answer'配置
        if 'suggested_questions_after_answer' not in config or not config["suggested_questions_after_answer"]:
            config["suggested_questions_after_answer"] = {
                "enabled": False
            }

        if not isinstance(config["suggested_questions_after_answer"], dict):
            raise ValueError("suggested_questions_after_answer must be of dict type")

        # 确保'enabled'字段存在且为布尔类型
        if "enabled" not in config["suggested_questions_after_answer"] or not config["suggested_questions_after_answer"]["enabled"]:
            config["suggested_questions_after_answer"]["enabled"] = False

        if not isinstance(config["suggested_questions_after_answer"]["enabled"], bool):
            raise ValueError("enabled in suggested_questions_after_answer must be of boolean type")

        # 以下部分对'speech_to_text', 'text_to_speech', 'retriever_resource', 'more_like_this'的配置进行类似的验证和设置

        # 验证并设置'speech_to_text'配置
        if 'speech_to_text' not in config or not config["speech_to_text"]:
            config["speech_to_text"] = {
                "enabled": False
            }

        if not isinstance(config["speech_to_text"], dict):
            raise ValueError("speech_to_text must be of dict type")

        # 确保'enabled'字段存在且为布尔类型
        if "enabled" not in config["speech_to_text"] or not config["speech_to_text"]["enabled"]:
            config["speech_to_text"]["enabled"] = False

        if not isinstance(config["speech_to_text"]["enabled"], bool):
            raise ValueError("enabled in speech_to_text must be of boolean type")

        # 验证并设置'text_to_speech'配置
        if 'text_to_speech' not in config or not config["text_to_speech"]:
            config["text_to_speech"] = {
                "enabled": False,
                "voice": "",
                "language": ""
            }

        if not isinstance(config["text_to_speech"], dict):
            raise ValueError("text_to_speech must be of dict type")

        # 确保'enabled', 'voice', 'language'字段存在且正确
        if "enabled" not in config["text_to_speech"] or not config["text_to_speech"]["enabled"]:
            config["text_to_speech"]["enabled"] = False
            config["text_to_speech"]["voice"] = ""
            config["text_to_speech"]["language"] = ""

        if not isinstance(config["text_to_speech"]["enabled"], bool):
            raise ValueError("enabled in text_to_speech must be of boolean type")

        # 验证并设置'retriever_resource'配置
        if 'retriever_resource' not in config or not config["retriever_resource"]:
            config["retriever_resource"] = {
                "enabled": False
            }

        if not isinstance(config["retriever_resource"], dict):
            raise ValueError("retriever_resource must be of dict type")

        # 确保'enabled'字段存在且为布尔类型
        if "enabled" not in config["retriever_resource"] or not config["retriever_resource"]["enabled"]:
            config["retriever_resource"]["enabled"] = False

        if not isinstance(config["retriever_resource"]["enabled"], bool):
            raise ValueError("enabled in retriever_resource must be of boolean type")

        # 验证并设置'more_like_this'配置
        if 'more_like_this' not in config or not config["more_like_this"]:
            config["more_like_this"] = {
                "enabled": False
            }

        if not isinstance(config["more_like_this"], dict):
            raise ValueError("more_like_this must be of dict type")

        # 确保'enabled'字段存在且为布尔类型
        if "enabled" not in config["more_like_this"] or not config["more_like_this"]["enabled"]:
            config["more_like_this"]["enabled"] = False

        if not isinstance(config["more_like_this"]["enabled"], bool):
            raise ValueError("enabled in more_like_this must be of boolean type")

        # 验证并设置'model'配置
        if 'model' not in config:
            raise ValueError("model is required")

        if not isinstance(config["model"], dict):
            raise ValueError("model must be of object type")

        # 对'model'的'provider'和'name'字段进行详细验证
        provider_entities = model_provider_factory.get_providers()
        model_provider_names = [provider.provider for provider in provider_entities]
        if 'provider' not in config["model"] or config["model"]["provider"] not in model_provider_names:
            raise ValueError(f"model.provider is required and must be in {str(model_provider_names)}")

        if 'name' not in config["model"]:
            raise ValueError("model.name is required")

        # 验证模型是否可用
        provider_manager = ProviderManager()
        models = provider_manager.get_configurations(tenant_id).get_models(
            provider=config["model"]["provider"],
            model_type=ModelType.LLM
        )
        if not models:
            raise ValueError("model.name must be in the specified model list")

        model_ids = [m.model for m in models]
        if config["model"]["name"] not in model_ids:
            raise ValueError("model.name must be in the specified model list")

        # 设置'model'的'mode'字段
        model_mode = None
        for model in models:
            if model.model == config["model"]["name"]:
                model_mode = model.model_properties.get(ModelPropertyKey.MODE)
                break

        if model_mode:
            config['model']["mode"] = model_mode
        else:
            config['model']["mode"] = "completion"

        # 验证并设置'model.completion_params'
        if 'completion_params' not in config["model"]:
            raise ValueError("model.completion_params is required")

        config["model"]["completion_params"] = cls.validate_model_completion_params(
            config["model"]["completion_params"],
            config["model"]["name"]
        )

        # 验证并设置'user_input_form'配置
        if "user_input_form" not in config or not config["user_input_form"]:
            config["user_input_form"] = []

        if not isinstance(config["user_input_form"], list):
            raise ValueError("user_input_form must be a list of objects")

        # 对'user_input_form'中的每一项进行详细验证
        variables = []
        for item in config["user_input_form"]:
            key = list(item.keys())[0]
            if key not in ["text-input", "select", "paragraph", "external_data_tool"]:
                raise ValueError("Keys in user_input_form list can only be 'text-input', 'paragraph'  or 'select'")

            form_item = item[key]
            if 'label' not in form_item:
                raise ValueError("label is required in user_input_form")

            if not isinstance(form_item["label"], str):
                raise ValueError("label in user_input_form must be of string type")

            if 'variable' not in form_item:
                raise ValueError("variable is required in user_input_form")

            if not isinstance(form_item["variable"], str):
                raise ValueError("variable in user_input_form must be of string type")

            # 验证'variable'的格式
            pattern = re.compile(r"^(?!\d)[\u4e00-\u9fa5A-Za-z0-9_\U0001F300-\U0001F64F\U0001F680-\U0001F6FF]{1,100}$")
            if pattern.match(form_item["variable"]) is None:
                raise ValueError("variable in user_input_form must be a string, "
                                "and cannot start with a number")

             # 处理用户输入表单中的变量
            variables.append(form_item["variable"])
            
            # 设置表单项是否必需，默认为非必需
            if 'required' not in form_item or not form_item["required"]:
                form_item["required"] = False
                
            # 检查required字段是否为布尔值
            if not isinstance(form_item["required"], bool):
                raise ValueError("required in user_input_form must be of boolean type")

            # 处理选择类型字段的选项
            if key == "select":
                # 设置默认选项列表，若未提供则为空列表
                if 'options' not in form_item or not form_item["options"]:
                    form_item["options"] = []
                    
                # 检查options字段是否为字符串列表
                if not isinstance(form_item["options"], list):
                    raise ValueError("options in user_input_form must be a list of strings")

                # 检查默认值是否在选项列表中
                if "default" in form_item and form_item['default'] \
                        and form_item["default"] not in form_item["options"]:
                    raise ValueError("default value in user_input_form must be in the options list")

        # 处理预提示信息
        if "pre_prompt" not in config or not config["pre_prompt"]:
            config["pre_prompt"] = ""

        # 检查pre_prompt字段是否为字符串
        if not isinstance(config["pre_prompt"], str):
            raise ValueError("pre_prompt must be of string type")

        # 设置代理模式的默认配置
        if "agent_mode" not in config or not config["agent_mode"]:
            config["agent_mode"] = {
                "enabled": False,
                "tools": []
            }

        # 检查agent_mode字段是否为字典
        if not isinstance(config["agent_mode"], dict):
            raise ValueError("agent_mode must be of object type")

        # 设置代理模式是否启用，默认不启用
        if "enabled" not in config["agent_mode"] or not config["agent_mode"]["enabled"]:
            config["agent_mode"]["enabled"] = False

        # 检查enabled字段是否为布尔值
        if not isinstance(config["agent_mode"]["enabled"], bool):
            raise ValueError("enabled in agent_mode must be of boolean type")

        # 设置代理模式策略，默认为ROUTER
        if "strategy" not in config["agent_mode"] or not config["agent_mode"]["strategy"]:
            config["agent_mode"]["strategy"] = PlanningStrategy.ROUTER.value

        # 检查策略是否在指定策略列表中
        if config["agent_mode"]["strategy"] not in [member.value for member in list(PlanningStrategy.__members__.values())]:
            raise ValueError("strategy in agent_mode must be in the specified strategy list")

        # 设置代理模式工具列表，默认为空列表
        if "tools" not in config["agent_mode"] or not config["agent_mode"]["tools"]:
            config["agent_mode"]["tools"] = []

        # 检查tools字段是否为对象列表
        if not isinstance(config["agent_mode"]["tools"], list):
            raise ValueError("tools in agent_mode must be a list of objects")

        # 验证代理模式工具的配置
        for tool in config["agent_mode"]["tools"]:
            key = list(tool.keys())[0]
            if key in SUPPORT_TOOLS:
                # 处理旧样式工具配置
                tool_item = tool[key]

                # 设置工具是否启用，默认不启用
                if "enabled" not in tool_item or not tool_item["enabled"]:
                    tool_item["enabled"] = False
                # 检查enabled字段是否为布尔值
                if not isinstance(tool_item["enabled"], bool):
                    raise ValueError("enabled in agent_mode.tools must be of boolean type")

                # 验证数据集配置
                if key == "dataset":
                    if 'id' not in tool_item:
                        raise ValueError("id is required in dataset")

                    # 检查数据集ID是否为UUID类型
                    try:
                        uuid.UUID(tool_item["id"])
                    except ValueError:
                        raise ValueError("id in dataset must be of UUID type")

                    # 验证数据集ID是否存在
                    if not cls.is_dataset_exists(account, tool_item["id"]):
                        raise ValueError("Dataset ID does not exist, please check your permission.")
            else:
                 # 处理新样式工具配置
                if "enabled" not in tool or not tool["enabled"]:
                    tool["enabled"] = False
                if "provider_type" not in tool:
                    raise ValueError("provider_type is required in agent_mode.tools")
                if "provider_id" not in tool:
                    raise ValueError("provider_id is required in agent_mode.tools")
                if "tool_name" not in tool:
                    raise ValueError("tool_name is required in agent_mode.tools")
                if "tool_parameters" not in tool:
                    raise ValueError("tool_parameters is required in agent_mode.tools")

        # 验证数据集查询变量的合法性
        cls.is_dataset_query_variable_valid(config, app_mode)

        # 高级提示验证
        cls.is_advanced_prompt_valid(config, app_mode)

        # 外部数据工具验证
        cls.is_external_data_tools_valid(tenant_id, config)

        # 审核验证
        cls.is_moderation_valid(tenant_id, config)

        # 文件上传验证
        cls.is_file_upload_valid(config)

        # 过滤掉额外的参数，只保留必要的配置项
        filtered_config = {
            "opening_statement": config["opening_statement"],
            "suggested_questions": config["suggested_questions"],
            "suggested_questions_after_answer": config["suggested_questions_after_answer"],
            "speech_to_text": config["speech_to_text"],
            "text_to_speech": config["text_to_speech"],
            "retriever_resource": config["retriever_resource"],
            "more_like_this": config["more_like_this"],
            "sensitive_word_avoidance": config["sensitive_word_avoidance"],
            "external_data_tools": config["external_data_tools"],
            "model": {
                "provider": config["model"]["provider"],
                "name": config["model"]["name"],
                "mode": config['model']["mode"],
                "completion_params": config["model"]["completion_params"]
            },
            "user_input_form": config["user_input_form"],
            "dataset_query_variable": config.get('dataset_query_variable'),
            "pre_prompt": config["pre_prompt"],
            "agent_mode": config["agent_mode"],
            "prompt_type": config["prompt_type"],
            "chat_prompt_config": config["chat_prompt_config"],
            "completion_prompt_config": config["completion_prompt_config"],
            "dataset_configs": config["dataset_configs"],
            "file_upload": config["file_upload"]
        }

        return filtered_config

    @classmethod
    def is_moderation_valid(cls, tenant_id: str, config: dict):
        """
        校验审核配置是否有效。

        参数:
        - cls: 类的引用，用于可能的类方法调用。
        - tenant_id: 字符串，表示租户ID。
        - config: 字典，包含敏感词规避的配置信息。

        返回值:
        - 无返回值，但会在配置无效时抛出异常或直接返回。
        """

        # 如果配置中没有敏感词规避部分，初始化为禁用状态
        if 'sensitive_word_avoidance' not in config or not config["sensitive_word_avoidance"]:
            config["sensitive_word_avoidance"] = {
                "enabled": False
            }

        # 确保敏感词规避的配置是字典类型
        if not isinstance(config["sensitive_word_avoidance"], dict):
            raise ValueError("sensitive_word_avoidance must be of dict type")

        # 如果未明确启用敏感词规避，视为禁用
        if "enabled" not in config["sensitive_word_avoidance"] or not config["sensitive_word_avoidance"]["enabled"]:
            config["sensitive_word_avoidance"]["enabled"] = False

        # 如果敏感词规避未启用，则直接返回
        if not config["sensitive_word_avoidance"]["enabled"]:
            return

        # 如果未提供类型或类型未明确启用，抛出异常
        if "type" not in config["sensitive_word_avoidance"] or not config["sensitive_word_avoidance"]["type"]:
            raise ValueError("sensitive_word_avoidance.type is required")

        # 准备类型和配置，以供进一步验证
        type = config["sensitive_word_avoidance"]["type"]
        config = config["sensitive_word_avoidance"]["config"]

        # 调用工厂方法验证配置的有效性
        ModerationFactory.validate_config(
            name=type,
            tenant_id=tenant_id,
            config=config
        )

    @classmethod
    def is_file_upload_valid(cls, config: dict):
        """
        检查文件上传配置是否有效。
        
        参数:
        - cls: 类的引用，用于可能的类方法调用，但在此函数中未使用。
        - config: 一个字典，包含关于文件上传的配置信息。
        
        返回值:
        - 无返回值，但会抛出 ValueError 如果配置不满足要求。
        """
        # 检查 file_upload 配置是否存在，若不存在则初始化为空字典
        if 'file_upload' not in config or not config["file_upload"]:
            config["file_upload"] = {}

        # 确保 file_upload 配置是字典类型
        if not isinstance(config["file_upload"], dict):
            raise ValueError("file_upload must be of dict type")

        # 检查图片上传配置
        if 'image' not in config["file_upload"] or not config["file_upload"]["image"]:
            config["file_upload"]["image"] = {"enabled": False}

        # 如果启用了图片上传，检查配置的合法性
        if config['file_upload']['image']['enabled']:
            # 检查图片数量限制是否在 [1, 6] 的范围内
            number_limits = config['file_upload']['image']['number_limits']
            if number_limits < 1 or number_limits > 6:
                raise ValueError("number_limits must be in [1, 6]")
            
            # 检查图片详情设置是否为 'high' 或 'low'
            detail = config['file_upload']['image']['detail']
            if detail not in ['high', 'low']:
                raise ValueError("detail must be in ['high', 'low']")

            # 检查图片传输方法是否为列表，并且列表中的每个项是否是 'remote_url' 或 'local_file'
            transfer_methods = config['file_upload']['image']['transfer_methods']
            if not isinstance(transfer_methods, list):
                raise ValueError("transfer_methods must be of list type")
            for method in transfer_methods:
                if method not in ['remote_url', 'local_file']:
                    raise ValueError("transfer_methods must be in ['remote_url', 'local_file']")

    @classmethod
    def is_external_data_tools_valid(cls, tenant_id: str, config: dict):
        """
        验证外部数据工具的配置是否有效。

        参数:
        - cls: 类的引用，用于可能的类方法调用。
        - tenant_id: 字符串，表示租户ID。
        - config: 字典，包含外部数据工具的配置信息。

        返回值:
        - 无返回值，但会抛出异常来指示配置验证失败。
        """
        # 检查config中是否定义了external_data_tools，如果没有则初始化为空列表
        if 'external_data_tools' not in config or not config["external_data_tools"]:
            config["external_data_tools"] = []

        # 确保external_data_tools是一个列表类型
        if not isinstance(config["external_data_tools"], list):
            raise ValueError("external_data_tools must be of list type")

        # 遍历external_data_tools列表，验证每个工具的配置
        for tool in config["external_data_tools"]:
            # 如果工具未明确启用，则默认为禁用
            if "enabled" not in tool or not tool["enabled"]:
                tool["enabled"] = False

            # 跳过禁用的工具
            if not tool["enabled"]:
                continue

            # 验证工具必须提供类型信息
            if "type" not in tool or not tool["type"]:
                raise ValueError("external_data_tools[].type is required")

            # 获取工具类型和配置，并进行进一步的配置验证
            type = tool["type"]
            config = tool["config"]

            ExternalDataToolFactory.validate_config(
                name=type,
                tenant_id=tenant_id,
                config=config
            )

    @classmethod
    def is_dataset_query_variable_valid(cls, config: dict, mode: str) -> None:
        """
        检查数据集查询变量的有效性。
        
        参数:
        - cls: 类的引用，此处未使用。
        - config: 包含代理模式和数据集配置的字典。
        - mode: 操作模式，如"completion"表示完成模式。
        
        返回值:
        - None: 该函数不返回任何值，但可能会抛出 ValueError。

        当模式为"completion"时，检查配置中是否指定了数据集以及数据集查询变量。
        如果数据集存在但未指定数据集查询变量，则抛出 ValueError。
        """

        # 仅当模式为"completion"时进行检查
        if mode != 'completion':
            return

        agent_mode = config.get("agent_mode", {})
        tools = agent_mode.get("tools", [])
        dataset_exists = "dataset" in str(tools)  # 检查数据集是否存在

        dataset_query_variable = config.get("dataset_query_variable")  # 获取数据集查询变量配置

        # 如果数据集存在但未设置数据集查询变量，则抛出异常
        if dataset_exists and not dataset_query_variable:
            raise ValueError("Dataset query variable is required when dataset is exist")

    @classmethod
    def is_advanced_prompt_valid(cls, config: dict, app_mode: str) -> None:
        """
        校验高级提示配置的有效性。

        参数:
        - cls: 类的引用，用于可能的类方法调用，但在此函数中未使用。
        - config: 一个字典，包含提示配置、聊天提示配置、完成提示配置和数据集配置等。
        - app_mode: 应用模式字符串，用于根据应用的当前模式调整配置要求。

        返回值:
        - 无。此函数通过抛出异常来报告无效配置。
        """

        # 校验提示类型配置
        if 'prompt_type' not in config or not config["prompt_type"]:
            config["prompt_type"] = "simple"

        if config['prompt_type'] not in ['simple', 'advanced']:
            raise ValueError("prompt_type must be in ['simple', 'advanced']")

        # 校验聊天提示配置
        if 'chat_prompt_config' not in config or not config["chat_prompt_config"]:
            config["chat_prompt_config"] = {}

        if not isinstance(config["chat_prompt_config"], dict):
            raise ValueError("chat_prompt_config must be of object type")

        # 校验完成提示配置
        if 'completion_prompt_config' not in config or not config["completion_prompt_config"]:
            config["completion_prompt_config"] = {}

        if not isinstance(config["completion_prompt_config"], dict):
            raise ValueError("completion_prompt_config must be of object type")

        # 校验数据集配置
        if 'dataset_configs' not in config or not config["dataset_configs"]:
            config["dataset_configs"] = {'retrieval_model': 'single'}

        if 'datasets' not in config["dataset_configs"] or not config["dataset_configs"]["datasets"]:
            config["dataset_configs"]["datasets"] = {
                "strategy": "router",
                "datasets": []
            }

        if not isinstance(config["dataset_configs"], dict):
            raise ValueError("dataset_configs must be of object type")

        # 多重检索模型配置检查
        if config["dataset_configs"]['retrieval_model'] == 'multiple':
            if not config["dataset_configs"]['reranking_model']:
                raise ValueError("reranking_model has not been set")
            if not isinstance(config["dataset_configs"]['reranking_model'], dict):
                raise ValueError("reranking_model must be of object type")

        if not isinstance(config["dataset_configs"], dict):
            raise ValueError("dataset_configs must be of object type")

        # 高级提示类型下的额外校验
        if config['prompt_type'] == 'advanced':
            if not config['chat_prompt_config'] and not config['completion_prompt_config']:
                raise ValueError("chat_prompt_config or completion_prompt_config is required when prompt_type is advanced")

            if config['model']["mode"] not in ['chat', 'completion']:
                raise ValueError("model.mode must be in ['chat', 'completion'] when prompt_type is advanced")

            # 在聊天模式下，检查完成提示配置中的用户和助手前缀
            if app_mode == AppMode.CHAT.value and config['model']["mode"] == "completion":
                user_prefix = config['completion_prompt_config']['conversation_histories_role']['user_prefix']
                assistant_prefix = config['completion_prompt_config']['conversation_histories_role']['assistant_prefix']

                if not user_prefix:
                    config['completion_prompt_config']['conversation_histories_role']['user_prefix'] = 'Human'

                if not assistant_prefix:
                    config['completion_prompt_config']['conversation_histories_role']['assistant_prefix'] = 'Assistant'

            # 聊天模式下，提示消息数量限制检查
            if config['model']["mode"] == "chat":
                prompt_list = config['chat_prompt_config']['prompt']

                if len(prompt_list) > 10:
                    raise ValueError("prompt messages must be less than 10")
