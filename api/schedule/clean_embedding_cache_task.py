import datetime
import time

import click
from werkzeug.exceptions import NotFound

import app
from configs import dify_config
from extensions.ext_database import db
from models.dataset import Embedding


@app.celery.task(queue='dataset')
def clean_embedding_cache_task():
    click.echo(click.style('Start clean embedding cache.', fg='green'))
    clean_days = int(dify_config.CLEAN_DAY_SETTING)
    start_at = time.perf_counter()
    thirty_days_ago = datetime.datetime.now() - datetime.timedelta(days=clean_days)
    while True:
        try:
            # 查询创建时间早于指定清理时间点的嵌入记录，分页获取
            embeddings = db.session.query(Embedding).filter(Embedding.created_at < thirty_days_ago) \
                .order_by(Embedding.created_at.desc()).limit(100).all()
        except NotFound:
            break  # 如果没有找到记录，结束循环
        for embedding in embeddings:
            db.session.delete(embedding)
        db.session.commit()
    end_at = time.perf_counter()
    click.echo(click.style('Cleaned embedding cache from db success latency: {}'.format(end_at - start_at), fg='green'))
