from datetime import datetime

from celery import states

from extensions.ext_database import db


class CeleryTask(db.Model):
    """
    Celery任务的结果/状态模型类。
    
    用于存储Celery任务的状态、结果等信息。
    """

    __tablename__ = 'celery_taskmeta'  # 数据库表名

    # 表字段定义
    id = db.Column(db.Integer, db.Sequence('task_id_sequence'),
                   primary_key=True, autoincrement=True)  # 任务ID，主键，自增长
    task_id = db.Column(db.String(155), unique=True)  # 任务唯一标识符
    status = db.Column(db.String(50), default=states.PENDING)  # 任务状态，默认为PENDING
    result = db.Column(db.PickleType, nullable=True)  # 任务执行结果，可为空
    date_done = db.Column(db.DateTime, default=datetime.utcnow,
                          onupdate=datetime.utcnow, nullable=True)  # 任务完成时间，默认为当前时间，更新时也更新此字段
    traceback = db.Column(db.Text, nullable=True)  # 任务异常堆栈信息，可为空
    name = db.Column(db.String(155), nullable=True)  # 任务名称，可为空
    args = db.Column(db.LargeBinary, nullable=True)  # 任务参数，序列化后存储，可为空
    kwargs = db.Column(db.LargeBinary, nullable=True)  # 任务关键字参数，序列化后存储，可为空
    worker = db.Column(db.String(155), nullable=True)  # 执行任务的工作器标识，可为空
    retries = db.Column(db.Integer, nullable=True)  # 任务重试次数，可为空
    queue = db.Column(db.String(155), nullable=True)  # 任务队列名，可为空


class CeleryTaskSet(db.Model):
    """
    Celery任务集结果模型类。
    
    用于存储Celery任务集的结果信息。
    """

    __tablename__ = 'celery_tasksetmeta'  # 数据库表名

    # 表字段定义
    id = db.Column(db.Integer, db.Sequence('taskset_id_sequence'),
                   autoincrement=True, primary_key=True)  # 任务集ID，主键，自增长
    taskset_id = db.Column(db.String(155), unique=True)  # 任务集唯一标识符
    result = db.Column(db.PickleType, nullable=True)  # 任务集执行结果，可为空
    date_done = db.Column(db.DateTime, default=datetime.utcnow,
                          nullable=True)  # 任务集完成时间，默认为当前时间