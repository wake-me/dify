from typing import Optional

from core.app.app_config.entities import DatasetEntity, DatasetRetrieveConfigEntity
from core.entities.agent_entities import PlanningStrategy
from models.model import AppMode
from services.dataset_service import DatasetService


class DatasetConfigManager:
    @classmethod
    def convert(cls, config: dict) -> Optional[DatasetEntity]:
        """
        将模型配置转换为模型配置。

        :param config: 模型配置参数，为字典类型。
        :return: 返回 DatasetEntity 实例或者 None。若没有有效的数据集ID，则返回 None。

        主要步骤包括：
        1. 从配置中提取数据集ID列表。
        2. 根据配置的不同类型（单模型检索或复合模型检索），创建并返回不同的 DatasetEntity 实例。
        """

        # 初始化数据集ID列表
        dataset_ids = []
        
        # 从配置中提取第一阶段数据集ID
        if 'datasets' in config.get('dataset_configs', {}):
            datasets = config.get('dataset_configs', {}).get('datasets', {
                'strategy': 'router',
                'datasets': []
            })

            for dataset in datasets.get('datasets', []):
                keys = list(dataset.keys())
                if len(keys) == 0 or keys[0] != 'dataset':
                    continue

                dataset = dataset['dataset']

                if 'enabled' not in dataset or not dataset['enabled']:
                    continue

                dataset_id = dataset.get('id', None)
                if dataset_id:
                    dataset_ids.append(dataset_id)

        # 从配置中提取第二阶段（代理模式）数据集ID
        if 'agent_mode' in config and config['agent_mode'] \
                and 'enabled' in config['agent_mode'] \
                and config['agent_mode']['enabled']:
            
            agent_dict = config.get('agent_mode', {})

            for tool in agent_dict.get('tools', []):
                keys = tool.keys()
                if len(keys) == 1:
                    # 旧标准处理
                    key = list(tool.keys())[0]

                    if key != 'dataset':
                        continue

                    tool_item = tool[key]

                    if "enabled" not in tool_item or not tool_item["enabled"]:
                        continue

                    dataset_id = tool_item['id']
                    dataset_ids.append(dataset_id)

        # 若没有有效的数据集ID，则返回 None
        if len(dataset_ids) == 0:
            return None

        # 提取并处理数据集配置
        dataset_configs = config.get('dataset_configs', {'retrieval_model': 'single'})
        query_variable = config.get('dataset_query_variable')

        # 根据检索模型类型构造并返回 DatasetEntity 实例
        if dataset_configs['retrieval_model'] == 'single':
            # 单模型检索配置
            return DatasetEntity(
                dataset_ids=dataset_ids,
                retrieve_config=DatasetRetrieveConfigEntity(
                    query_variable=query_variable,
                    retrieve_strategy=DatasetRetrieveConfigEntity.RetrieveStrategy.value_of(
                        dataset_configs['retrieval_model']
                    )
                )
            )
        else:
            # 复合模型检索配置
            return DatasetEntity(
                dataset_ids=dataset_ids,
                retrieve_config=DatasetRetrieveConfigEntity(
                    query_variable=query_variable,
                    retrieve_strategy=DatasetRetrieveConfigEntity.RetrieveStrategy.value_of(
                        dataset_configs['retrieval_model']
                    ),
                    top_k=dataset_configs.get('top_k'),
                    score_threshold=dataset_configs.get('score_threshold'),
                    reranking_model=dataset_configs.get('reranking_model')
                )
            )

    @classmethod
    def validate_and_set_defaults(cls, tenant_id: str, app_mode: AppMode, config: dict) -> tuple[dict, list[str]]:
        """
        验证并设置数据集功能的默认值

        :param tenant_id: 租户ID
        :param app_mode: 应用模式
        :param config: 应用模型配置参数
        :return: 一个元组，包含经过验证和设置默认值的配置字典，以及一个字符串列表，提示哪些配置项是必需的或被修改了

        此函数主要用于对数据集配置进行验证，并在缺少必要配置时设置默认值。它确保了配置的完整性和正确性，为后续操作提供保障。
        """

        # 从旧版兼容性中提取数据集配置
        config = cls.extract_dataset_config_for_legacy_compatibility(tenant_id, app_mode, config)

        # 确保"dataset_configs"存在，并设置默认的检索模型为'single'
        if not config.get("dataset_configs"):
            config["dataset_configs"] = {'retrieval_model': 'single'}

        # 确保"datasets"配置存在，并设置默认策略为'router'，数据集列表为空
        if not config["dataset_configs"].get("datasets"):
            config["dataset_configs"]["datasets"] = {
                "strategy": "router",
                "datasets": []
            }

        # 验证"dataset_configs"必须为字典类型
        if not isinstance(config["dataset_configs"], dict):
            raise ValueError("dataset_configs must be of object type")

        # 如果设置了多种检索模型，确保重排模型也被设置，并且为字典类型
        if config["dataset_configs"]['retrieval_model'] == 'multiple':
            if not config["dataset_configs"]['reranking_model']:
                raise ValueError("reranking_model has not been set")
            if not isinstance(config["dataset_configs"]['reranking_model'], dict):
                raise ValueError("reranking_model must be of object type")

        # 再次验证"dataset_configs"必须为字典类型，确保配置的正确性
        if not isinstance(config["dataset_configs"], dict):
            raise ValueError("dataset_configs must be of object type")

        # 检查是否需要手动查询数据集，并且应用模式为补全模式
        need_manual_query_datasets = (config.get("dataset_configs")
                                    and config["dataset_configs"].get("datasets", {}).get("datasets"))

        if need_manual_query_datasets and app_mode == AppMode.COMPLETION:
            # 当模式为补全时，仅检查数据集查询变量是否存在
            dataset_query_variable = config.get("dataset_query_variable")

            if not dataset_query_variable:
                raise ValueError("Dataset query variable is required when dataset is exist")

        # 返回经过验证和设置默认值的配置，以及受影响的配置项列表
        return config, ["agent_mode", "dataset_configs", "dataset_query_variable"]

    @classmethod
    def extract_dataset_config_for_legacy_compatibility(cls, tenant_id: str, app_mode: AppMode, config: dict) -> dict:
        """
        为与旧版兼容而提取数据集配置

        :param tenant_id: 租户ID
        :param app_mode: 应用模式
        :param config: 应用模型配置参数
        :return: 更新后的配置字典
        """
        # 为兼容旧版提取数据集配置
        if not config.get("agent_mode"):
            config["agent_mode"] = {
                "enabled": False,
                "tools": []
            }

        if not isinstance(config["agent_mode"], dict):
            raise ValueError("agent_mode must be of object type")

        # 启用状态设置
        if "enabled" not in config["agent_mode"] or not config["agent_mode"]["enabled"]:
            config["agent_mode"]["enabled"] = False

        if not isinstance(config["agent_mode"]["enabled"], bool):
            raise ValueError("enabled in agent_mode must be of boolean type")

        # 工具设置
        if not config["agent_mode"].get("tools"):
            config["agent_mode"]["tools"] = []

        if not isinstance(config["agent_mode"]["tools"], list):
            raise ValueError("tools in agent_mode must be a list of objects")

        # 策略设置
        if not config["agent_mode"].get("strategy"):
            config["agent_mode"]["strategy"] = PlanningStrategy.ROUTER.value

        has_datasets = False
        if config["agent_mode"]["strategy"] in [PlanningStrategy.ROUTER.value, PlanningStrategy.REACT_ROUTER.value]:
            for tool in config["agent_mode"]["tools"]:
                key = list(tool.keys())[0]
                if key == "dataset":
                    # 旧样式，使用工具名称作为键
                    tool_item = tool[key]

                    if "enabled" not in tool_item or not tool_item["enabled"]:
                        tool_item["enabled"] = False

                    if not isinstance(tool_item["enabled"], bool):
                        raise ValueError("enabled in agent_mode.tools must be of boolean type")

                    if 'id' not in tool_item:
                        raise ValueError("id is required in dataset")

                    try:
                        uuid.UUID(tool_item["id"])
                    except ValueError:
                        raise ValueError("id in dataset must be of UUID type")

                    if not cls.is_dataset_exists(tenant_id, tool_item["id"]):
                        raise ValueError("Dataset ID does not exist, please check your permission.")

                    has_datasets = True

        need_manual_query_datasets = has_datasets and config["agent_mode"]["enabled"]

        if need_manual_query_datasets and app_mode == AppMode.COMPLETION:
            # 仅在模式为完成时检查
            dataset_query_variable = config.get("dataset_query_variable")

            if not dataset_query_variable:
                raise ValueError("Dataset query variable is required when dataset is exist")

        return config

    @classmethod
    def is_dataset_exists(cls, tenant_id: str, dataset_id: str) -> bool:
        """
        检查给定的租户ID和数据集ID是否对应的数据集存在。
        
        参数:
        - cls: 类的引用，用于调用类方法。
        - tenant_id: 字符串，指定的租户ID。
        - dataset_id: 字符串，指定的数据集ID。
        
        返回值:
        - 布尔值，如果数据集存在且属于指定的租户ID，则返回True；否则返回False。
        """
        # 尝试根据数据集ID获取数据集信息
        dataset = DatasetService.get_dataset(dataset_id)

        if not dataset:
            return False  # 数据集不存在

        if dataset.tenant_id != tenant_id:
            return False  # 数据集存在，但不属于指定的租户ID

        return True  # 数据集存在且属于指定租户ID
