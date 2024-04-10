from datetime import timedelta

from celery import Celery, Task
from flask import Flask


def init_app(app: Flask) -> Celery:
    """
    初始化并配置Celery任务队列。
    
    参数:
    - app: Flask应用实例，用于配置Celery。
    
    返回值:
    - 配置好的Celery实例。
    """
    class FlaskTask(Task):
        """
        自定义的Celery任务类，用于在Flask应用上下文中执行任务。
        """
        def __call__(self, *args: object, **kwargs: object) -> object:
            """
            重写__call__方法，确保任务在Flask应用上下文中执行。
            """
            with app.app_context():
                return self.run(*args, **kwargs)

    # 初始化Celery实例，并配置任务类、消息代理和结果后端
    celery_app = Celery(
        app.name,
        task_cls=FlaskTask,
        broker=app.config["CELERY_BROKER_URL"],
        backend=app.config["CELERY_BACKEND"],
        task_ignore_result=True,
    )
    
    # 配置Celery的SSL选项
    ssl_options = {
        "ssl_cert_reqs": None,
        "ssl_ca_certs": None,
        "ssl_certfile": None,
        "ssl_keyfile": None,
    }

    # 更新Celery配置结果后端
    celery_app.conf.update(
        result_backend=app.config["CELERY_RESULT_BACKEND"],
        broker_connection_retry_on_startup=True,
    )

    # 如果配置了使用SSL，则更新Broker配置以包含SSL选项
    if app.config["BROKER_USE_SSL"]:
        celery_app.conf.update(
            broker_use_ssl=ssl_options,  # 将SSL选项添加到Broker配置中
        )
        
    # 设置Celery为默认实例，并在Flask应用中注册
    celery_app.set_default()
    app.extensions["celery"] = celery_app

    # 配置Celery定时任务
    imports = [
        "schedule.clean_embedding_cache_task",
        "schedule.clean_unused_datasets_task",
    ]

    beat_schedule = {
        'clean_embedding_cache_task': {
            'task': 'schedule.clean_embedding_cache_task.clean_embedding_cache_task',
            'schedule': timedelta(days=1),
        },
        'clean_unused_datasets_task': {
            'task': 'schedule.clean_unused_datasets_task.clean_unused_datasets_task',
            'schedule': timedelta(days=1),
        }
    }
    celery_app.conf.update(
        beat_schedule=beat_schedule,
        imports=imports
    )

    return celery_app
