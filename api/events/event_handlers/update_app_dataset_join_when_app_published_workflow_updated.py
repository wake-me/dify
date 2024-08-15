from typing import cast

from core.workflow.entities.node_entities import NodeType
from core.workflow.nodes.knowledge_retrieval.entities import KnowledgeRetrievalNodeData
from events.app_event import app_published_workflow_was_updated
from extensions.ext_database import db
from models.dataset import AppDatasetJoin
from models.workflow import Workflow


@app_published_workflow_was_updated.connect
def handle(sender, **kwargs):
    """
    处理应用程序与工作流之间的数据集关联更新。

    参数:
    - sender: 触发事件的应用程序实例。
    - **kwargs: 关键字参数，包括发布的工作流信息。

    返回值:
    - 无。
    """
    app = sender
    published_workflow = kwargs.get("published_workflow")
    published_workflow = cast(Workflow, published_workflow)

    # 从发布的工作流中获取数据集ID集合
    dataset_ids = get_dataset_ids_from_workflow(published_workflow)
    app_dataset_joins = db.session.query(AppDatasetJoin).filter(AppDatasetJoin.app_id == app.id).all()

    removed_dataset_ids = []
    if not app_dataset_joins:
        # 如果当前没有应用与数据集的关联，则直接将所有数据集ID视为新增
        added_dataset_ids = dataset_ids
    else:
        # 计算新增和移除的数据集ID
        old_dataset_ids = set()
        for app_dataset_join in app_dataset_joins:
            old_dataset_ids.add(app_dataset_join.dataset_id)

        added_dataset_ids = dataset_ids - old_dataset_ids
        removed_dataset_ids = old_dataset_ids - dataset_ids

    # 处理移除的数据集ID，断开其与应用的关联
    if removed_dataset_ids:
        for dataset_id in removed_dataset_ids:
            db.session.query(AppDatasetJoin).filter(
                AppDatasetJoin.app_id == app.id, AppDatasetJoin.dataset_id == dataset_id
            ).delete()

    # 处理新增的数据集ID，建立其与应用的关联
    if added_dataset_ids:
        for dataset_id in added_dataset_ids:
            app_dataset_join = AppDatasetJoin(app_id=app.id, dataset_id=dataset_id)
            db.session.add(app_dataset_join)

    # 提交数据库会话，保存所有更改
    db.session.commit()


def get_dataset_ids_from_workflow(published_workflow: Workflow) -> set:
    """
    从发布的流程中获取数据集ID集合。
    
    参数:
    - published_workflow: Workflow类型，表示已发布的流程对象。
    
    返回值:
    - set: 包含所有数据集ID的集合。
    """
    dataset_ids = set()
    graph = published_workflow.graph_dict
    if not graph:
        return dataset_ids

    nodes = graph.get("nodes", [])

    # fetch all knowledge retrieval nodes
    knowledge_retrieval_nodes = [
        node for node in nodes if node.get("data", {}).get("type") == NodeType.KNOWLEDGE_RETRIEVAL.value
    ]

    if not knowledge_retrieval_nodes:
        return dataset_ids

    for node in knowledge_retrieval_nodes:
        try:
            node_data = KnowledgeRetrievalNodeData(**node.get("data", {}))
            dataset_ids.update(node_data.dataset_ids)
        except Exception as e:
            # 如果解析失败，则跳过该节点
            continue

    return dataset_ids
