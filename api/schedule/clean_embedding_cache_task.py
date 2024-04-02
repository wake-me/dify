import datetime
import time

import click
from flask import current_app
from werkzeug.exceptions import NotFound

import app
from extensions.ext_database import db
from models.dataset import Embedding


@app.celery.task(queue='dataset')
def clean_embedding_cache_task():
    """
    清理嵌入缓存任务。
    该函数无参数，也不返回任何值。
    它从数据库中删除超过指定天数（CLEAN_DAY_SETTING配置项指定）的嵌入记录，以清理缓存。
    """
    click.echo(click.style('Start clean embedding cache.', fg='green'))  # 开始清理嵌入缓存的提示信息
    clean_days = int(current_app.config.get('CLEAN_DAY_SETTING'))  # 从应用配置中获取清理天数
    start_at = time.perf_counter()  # 记录开始时间
    thirty_days_ago = datetime.datetime.now() - datetime.timedelta(days=clean_days)  # 计算清理时间点
    page = 1  # 初始化分页查询的页码
    while True:
        try:
            # 查询创建时间早于指定清理时间点的嵌入记录，分页获取
            embeddings = db.session.query(Embedding).filter(Embedding.created_at < thirty_days_ago) \
                .order_by(Embedding.created_at.desc()).paginate(page=page, per_page=100)
        except NotFound:
            break  # 如果没有找到记录，结束循环
        for embedding in embeddings:
            db.session.delete(embedding)  # 删除查询到的每条嵌入记录
        db.session.commit()  # 提交数据库操作
        page += 1  # 分页查询下一页
    end_at = time.perf_counter()  # 记录结束时间
    # 输出清理成功的提示信息，包括操作耗时
    click.echo(click.style('Cleaned embedding cache from db success latency: {}'.format(end_at - start_at), fg='green'))
