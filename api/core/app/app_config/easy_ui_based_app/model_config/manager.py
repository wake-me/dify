from core.app.app_config.entities import ModelConfigEntity
from core.model_runtime.entities.model_entities import ModelPropertyKey, ModelType
from core.model_runtime.model_providers import model_provider_factory
from core.provider_manager import ProviderManager


class ModelConfigManager:
    @classmethod
    def convert(cls, config: dict) -> ModelConfigEntity:
        """
        将模型配置转换为模型配置实体。

        :param config: 模型配置参数
        :return: 模型配置实体
        """
        # 获取模型配置
        model_config = config.get('model')

        if not model_config:
            raise ValueError("model is required")

        # 处理完成参数中的'stop'字段
        completion_params = model_config.get('completion_params')
        stop = []
        if 'stop' in completion_params:
            stop = completion_params['stop']
            del completion_params['stop']

        # 获取模型模式
        model_mode = model_config.get('mode')

        # 返回模型配置实体
        return ModelConfigEntity(
            provider=config['model']['provider'],
            model=config['model']['name'],
            mode=model_mode,
            parameters=completion_params,
            stop=stop,
        )

    @classmethod
    def validate_and_set_defaults(cls, tenant_id: str, config: dict) -> tuple[dict, list[str]]:
        """
        验证并设置模型配置的默认值。

        :param tenant_id: 租户ID
        :param config: 应用模型配置参数
        :return: 配置参数和更新的字段列表
        """
        # 检查模型配置是否存在
        if 'model' not in config:
            raise ValueError("model is required")

        # 检查模型配置是否为字典类型
        if not isinstance(config["model"], dict):
            raise ValueError("model must be of object type")

        # 验证模型提供者配置
        provider_entities = model_provider_factory.get_providers()
        model_provider_names = [provider.provider for provider in provider_entities]
        if 'provider' not in config["model"] or config["model"]["provider"] not in model_provider_names:
            raise ValueError(f"model.provider is required and must be in {str(model_provider_names)}")

        # 验证模型名称配置
        if 'name' not in config["model"]:
            raise ValueError("model.name is required")

        # 获取符合条件的模型列表
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

        # 获取模型模式
        model_mode = None
        for model in models:
            if model.model == config["model"]["name"]:
                model_mode = model.model_properties.get(ModelPropertyKey.MODE)
                break

        # 设置模型模式，默认为"completion"
        if model_mode:
            config['model']["mode"] = model_mode
        else:
            config['model']["mode"] = "completion"

        # 验证并设置完成参数
        if 'completion_params' not in config["model"]:
            raise ValueError("model.completion_params is required")

        config["model"]["completion_params"] = cls.validate_model_completion_params(
            config["model"]["completion_params"]
        )

        return config, ["model"]

    @classmethod
    def validate_model_completion_params(cls, cp: dict) -> dict:
        """
        验证并设置模型完成参数的默认值。

        :param cp: 完成参数配置
        :return: 验证后的完成参数配置
        """
        # 检查完成参数是否为字典类型
        if not isinstance(cp, dict):
            raise ValueError("model.completion_params must be of object type")

        # 处理'stop'字段，默认为空列表
        if 'stop' not in cp:
            cp["stop"] = []
        elif not isinstance(cp["stop"], list):
            raise ValueError("stop in model.completion_params must be of list type")

        # 检查'stop'字段长度是否超过限制
        if len(cp["stop"]) > 4:
            raise ValueError("stop sequences must be less than 4")

        return cp
