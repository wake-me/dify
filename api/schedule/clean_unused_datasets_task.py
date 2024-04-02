import datetime
import time

import click
from flask import current_app
from werkzeug.exceptions import NotFound

import app
from core.rag.index_processor.index_processor_factory import IndexProcessorFactory
from extensions.ext_database import db
from models.dataset import Dataset, DatasetQuery, Document


@app.celery.task(queue='dataset')
def clean_unused_datasets_task():
    """
    执行清理未使用的数据集任务。
    此任务会查找创建时间超过指定天数（由CLEAN_DAY_SETTING配置项定义）且没有被查询记录的数据集，
    并清理这些数据集对应的索引，同时将数据集在数据库中的状态设为不可用。
    """
    # 输出任务开始信息
    click.echo(click.style('Start clean unused datasets indexes.', fg='green'))
    # 读取清理天数设置
    clean_days = int(current_app.config.get('CLEAN_DAY_SETTING'))
    # 记录任务开始时间
    start_at = time.perf_counter()
    # 计算清理阈值时间
    thirty_days_ago = datetime.datetime.now() - datetime.timedelta(days=clean_days)
    # 初始化分页查询
    page = 1
    while True:
        try:
            # 查询创建时间超过阈值的数据集
            datasets = db.session.query(Dataset).filter(Dataset.created_at < thirty_days_ago) \
                .order_by(Dataset.created_at.desc()).paginate(page=page, per_page=50)
        except NotFound:
            # 查询不到数据时退出循环
            break
        page += 1
        for dataset in datasets:
            # 查询数据集的查询记录
            dataset_query = db.session.query(DatasetQuery).filter(
                DatasetQuery.created_at > thirty_days_ago,
                DatasetQuery.dataset_id == dataset.id
            ).all()
            # 如果数据集没有查询记录且没有文档，则进行清理
            if not dataset_query or len(dataset_query) == 0:
                documents = db.session.query(Document).filter(
                    Document.dataset_id == dataset.id,
                    Document.indexing_status == 'completed',
                    Document.enabled == True,
                    Document.archived == False,
                    Document.updated_at > thirty_days_ago
                ).all()
                # 如果数据集没有关联的文档，则进行索引清理和状态更新
                if not documents or len(documents) == 0:
                    try:
                        # 清理索引
                        index_processor = IndexProcessorFactory(dataset.doc_form).init_index_processor()
                        index_processor.clean(dataset, None)

                        # 更新文档状态为不可用
                        update_params = {
                            Document.enabled: False
                        }

                        Document.query.filter_by(dataset_id=dataset.id).update(update_params)
                        db.session.commit()
                        # 输出清理成功信息
                        click.echo(click.style('Cleaned unused dataset {} from db success!'.format(dataset.id),
                                               fg='green'))
                    except Exception as e:
                        # 输出清理失败信息
                        click.echo(
                            click.style('clean dataset index error: {} {}'.format(e.__class__.__name__, str(e)),
                                        fg='red'))
    # 输出任务完成信息
    end_at = time.perf_counter()
    click.echo(click.style('Cleaned unused dataset from db success latency: {}'.format(end_at - start_at), fg='green'))
