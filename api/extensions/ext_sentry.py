import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.flask import FlaskIntegration
from werkzeug.exceptions import HTTPException


def init_app(app):
    """
    初始化Sentry错误监控。

    参数:
    - app: Flask应用实例，用于获取配置信息。

    返回值:
    - 无
    """
    # 检查是否配置了Sentry的DSN
    if app.config.get('SENTRY_DSN'):
        # 初始化Sentry SDK
        sentry_sdk.init(
            dsn=app.config.get('SENTRY_DSN'),  # Sentry服务的DSN
            integrations=[
                FlaskIntegration(),  # 集成Flask框架
                CeleryIntegration()  # 集成Celery异步任务
            ],
            ignore_errors=[HTTPException, ValueError],  # 忽略特定的错误类型
            traces_sample_rate=app.config.get('SENTRY_TRACES_SAMPLE_RATE', 1.0),  # 采样率配置
            profiles_sample_rate=app.config.get('SENTRY_PROFILES_SAMPLE_RATE', 1.0),
            environment=app.config.get('DEPLOY_ENV'),  # 设置环境变量
            release=f"dify-{app.config.get('CURRENT_VERSION')}-{app.config.get('COMMIT_SHA')}"  # 设置发布版本信息
        )
