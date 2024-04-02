from events.app_event import app_model_config_was_updated
from extensions.ext_database import db
from models.dataset import AppDatasetJoin
from models.model import AppModelConfig


# 当 app 的模型配置更新时触发的处理函数
@app_model_config_was_updated.connect
def handle(sender, **kwargs):
    app = sender
    app_model_config = kwargs.get('app_model_config')

    # 从新的模型配置中获取数据集 ID 列表
    dataset_ids = get_dataset_ids_from_model_config(app_model_config)

    # 查询当前 app 已经关联的数据集 ID
    app_dataset_joins = db.session.query(AppDatasetJoin).filter(
        AppDatasetJoin.app_id == app.id
    ).all()

    removed_dataset_ids = []
    if not app_dataset_joins:
        added_dataset_ids = dataset_ids  # 如果之前没有关联数据集，那么新增的数据集即为当前所有数据集
    else:
        old_dataset_ids = set()
        for app_dataset_join in app_dataset_joins:
            old_dataset_ids.add(app_dataset_join.dataset_id)

        # 新增的数据集 ID 和移除的数据集 ID
        added_dataset_ids = dataset_ids - old_dataset_ids
        removed_dataset_ids = old_dataset_ids - dataset_ids

    # 处理移除的数据集
    if removed_dataset_ids:
        for dataset_id in removed_dataset_ids:
            db.session.query(AppDatasetJoin).filter(
                AppDatasetJoin.app_id == app.id,
                AppDatasetJoin.dataset_id == dataset_id
            ).delete()

    # 处理新增的数据集
    if added_dataset_ids:
        for dataset_id in added_dataset_ids:
            app_dataset_join = AppDatasetJoin(
                app_id=app.id,
                dataset_id=dataset_id
            )
            db.session.add(app_dataset_join)

    # 提交数据库会话更改
    db.session.commit()


# 从 app 模型配置中提取数据集 ID 的集合
def get_dataset_ids_from_model_config(app_model_config: AppModelConfig) -> set:
    dataset_ids = set()
    if not app_model_config:
        return dataset_ids

    agent_mode = app_model_config.agent_mode_dict

    # 从工具配置中获取数据集 ID
    tools = agent_mode.get('tools', []) or []
    for tool in tools:
        if len(list(tool.keys())) != 1:
            continue

        tool_type = list(tool.keys())[0]
        tool_config = list(tool.values())[0]
        if tool_type == "dataset":
            dataset_ids.add(tool_config.get("id"))

    # 从数据集配置中获取数据集 ID
    dataset_configs = app_model_config.dataset_configs_dict
    datasets = dataset_configs.get('datasets', {}) or {}
    for dataset in datasets.get('datasets', []) or []:
        keys = list(dataset.keys())
        if len(keys) == 1 and keys[0] == 'dataset':
            if dataset['dataset'].get('id'):
                dataset_ids.add(dataset['dataset'].get('id'))

    return dataset_ids
