from events.dataset_event import dataset_was_deleted
from tasks.clean_dataset_task import clean_dataset_task


@dataset_was_deleted.connect
def handle(sender, **kwargs):
    """
    当数据集被删除时触发的处理函数。
    
    参数:
    - sender: 发送信号的对象，即被删除的数据集。
    - **kwargs: 关键字参数，包含额外的信息（本例中未使用）。
    
    无返回值。
    """
    dataset = sender  # 获取被删除的数据集对象
    
    # 异步调用清理数据集任务，传入数据集的相关信息
    clean_dataset_task.delay(dataset.id, dataset.tenant_id, dataset.indexing_technique,
                             dataset.index_struct, dataset.collection_binding_id, dataset.doc_form)