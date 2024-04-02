from events.document_event import document_was_deleted
from tasks.clean_document_task import clean_document_task


# 此函数用于处理文档被删除的事件
@document_was_deleted.connect
def handle(sender, **kwargs):
    """
    当文档被删除时触发的处理函数。
    
    参数:
    - sender: 触发事件的对象，此处为被删除文档的ID。
    - **kwargs: 关键字参数，包含额外的信息，比如：
                - dataset_id: 数据集的ID，文档所属的数据集。
                - doc_form: 文档表单，包含文档的详细信息。
                
    返回值: 无
    """
    document_id = sender  # 被删除文档的ID
    dataset_id = kwargs.get('dataset_id')  # 文档所属数据集的ID
    doc_form = kwargs.get('doc_form')  # 文档表单
    
    # 异步调用清理文档的任务
    clean_document_task.delay(document_id, dataset_id, doc_form)