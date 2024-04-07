# 导入必要的模块和库
import os
from werkzeug.exceptions import Unauthorized

# 如果不是在调试模式下，对一些库进行特殊配置，以提高性能
if not os.environ.get("DEBUG") or os.environ.get("DEBUG").lower() != 'true':
    from gevent import monkey
    monkey.patch_all()
    # 如果使用Milvus作为向量存储，进行额外的grpc配置
    import grpc.experimental.gevent
    grpc.experimental.gevent.init_gevent()

    # 配置langchain库，用于语言处理
    import langchain
    langchain.verbose = True

# 导入广泛使用的模块
import json
import logging
import threading
import time
import warnings

# 导入Flask及其相关扩展
from flask import Flask, Response, request
from flask_cors import CORS

# 导入自定义的模块和类
from commands import register_commands
from config import CloudEditionConfig, Config
from extensions import (
    ext_celery,
    ext_code_based_extension,
    ext_compress,
    ext_database,
    ext_hosting_provider,
    ext_login,
    ext_mail,
    ext_migrate,
    ext_redis,
    ext_sentry,
    ext_storage,
)
from extensions.ext_database import db
from extensions.ext_login import login_manager
from libs.passport import PassportService
from services.account_service import AccountService

# 注册事件处理器和模型
from events import event_handlers
from models import account, dataset, model, source, task, tool, tools, web

# 忽略特定的资源警告
warnings.simplefilter("ignore", ResourceWarning)

# 根据操作系统设置时区
if os.name == "nt":
    os.system('tzutil /s "UTC"')    
else:
    os.environ['TZ'] = 'UTC'
    time.tzset()


# 定义继承自Flask的自定义应用类
class DifyApp(Flask):
    pass

# 配置部分
config_type = os.getenv('EDITION', default='SELF_HOSTED')  # 通过环境变量读取应用版本类型

# 应用工厂函数，用于创建和配置Flask应用实例
def create_app(test_config=None) -> Flask:
    app = DifyApp(__name__)

    # 加载测试配置或环境配置
    if test_config:
        app.config.from_object(test_config)
    else:
        if config_type == "CLOUD":
            app.config.from_object(CloudEditionConfig())
        else:
            app.config.from_object(Config())

    # 初始化Flask扩展
    initialize_extensions(app)
    register_blueprints(app)
    register_commands(app)

    return app


# 初始化Flask扩展
def initialize_extensions(app):
    # 将Flask应用实例绑定到各个扩展实例上
    ext_compress.init_app(app)
    ext_code_based_extension.init()
    ext_database.init_app(app)
    ext_migrate.init(app, db)
    ext_redis.init_app(app)
    ext_storage.init_app(app)
    ext_celery.init_app(app)
    ext_login.init_app(app)
    ext_mail.init_app(app)
    ext_hosting_provider.init_app(app)
    ext_sentry.init_app(app)


# Flask-Login的请求加载器配置，用于从请求中加载用户
@login_manager.request_loader
def load_user_from_request(request_from_flask_login):
    """从请求中加载用户。如果请求来自控制台，使用不同的认证方式。"""
    if request.blueprint == 'console':
        # 处理基于token的认证
        auth_header = request.headers.get('Authorization', '')
        if not auth_header:
            auth_token = request.args.get('_token')
            if not auth_token:
                raise Unauthorized('Invalid Authorization token.')
        else:
            if ' ' not in auth_header:
                raise Unauthorized('Invalid Authorization header format. Expected \'Bearer <api-key>\' format.')
            auth_scheme, auth_token = auth_header.split(None, 1)
            auth_scheme = auth_scheme.lower()
            if auth_scheme != 'bearer':
                raise Unauthorized('Invalid Authorization header format. Expected \'Bearer <api-key>\' format.')

        decoded = PassportService().verify(auth_token)
        user_id = decoded.get('user_id')

        return AccountService.load_user(user_id)
    else:
        return None


# 自定义未授权请求处理器
@login_manager.unauthorized_handler
def unauthorized_handler():
    """处理未授权的请求，返回JSON格式的错误信息。"""
    return Response(json.dumps({
        'code': 'unauthorized',
        'message': "Unauthorized."
    }), status=401, content_type="application/json")


# 注册蓝图
def register_blueprints(app):
    # 导入并注册各个路由蓝图
    from controllers.console import bp as console_app_bp
    from controllers.files import bp as files_bp
    from controllers.service_api import bp as service_api_bp
    from controllers.web import bp as web_bp

    # 对service_api_bp配置CORS，允许特定的请求头和方法
    CORS(service_api_bp,
         allow_headers=['Content-Type', 'Authorization', 'X-App-Code'],
         methods=['GET', 'PUT', 'POST', 'DELETE', 'OPTIONS', 'PATCH']
         )
    app.register_blueprint(service_api_bp)

    # 对web_bp配置CORS，允许特定的请求源、请求头和方法
    CORS(web_bp,
         resources={
             r"/*": {"origins": app.config['WEB_API_CORS_ALLOW_ORIGINS']}},
         supports_credentials=True,
         allow_headers=['Content-Type', 'Authorization', 'X-App-Code'],
         methods=['GET', 'PUT', 'POST', 'DELETE', 'OPTIONS', 'PATCH'],
         expose_headers=['X-Version', 'X-Env']
         )

    app.register_blueprint(web_bp)

    # 对console_app_bp配置CORS，允许特定的请求源、请求头和方法
    CORS(console_app_bp,
         resources={
             r"/*": {"origins": app.config['CONSOLE_CORS_ALLOW_ORIGINS']}},
         supports_credentials=True,
         allow_headers=['Content-Type', 'Authorization'],
         methods=['GET', 'PUT', 'POST', 'DELETE', 'OPTIONS', 'PATCH'],
         expose_headers=['X-Version', 'X-Env']
         )

    app.register_blueprint(console_app_bp)

    # 对files_bp配置CORS，允许特定的请求头和方法
    CORS(files_bp,
         allow_headers=['Content-Type'],
         methods=['GET', 'PUT', 'POST', 'DELETE', 'OPTIONS', 'PATCH']
         )
    app.register_blueprint(files_bp)


# 创建应用实例
app = create_app()
celery = app.extensions["celery"]

# 如果处于测试模式，输出提示信息
if app.config['TESTING']:
    print("App is running in TESTING mode")

# 请求后处理器，用于添加版本和环境信息到响应头
@app.after_request
def after_request(response):
    """在响应发送前添加版本和环境信息到响应头。"""
    response.set_cookie('remember_token', '', expires=0)
    response.headers.add('X-Version', app.config['CURRENT_VERSION'])
    response.headers.add('X-Env', app.config['DEPLOY_ENV'])
    return response


# 健康检查接口
@app.route('/health')
def health():
    return Response(json.dumps({
        'status': 'ok',
        'version': app.config['CURRENT_VERSION']
    }), status=200, content_type="application/json")


# 线程信息接口
@app.route('/threads')
def threads():
    num_threads = threading.active_count()
    threads = threading.enumerate()

    thread_list = []
    for thread in threads:
        thread_name = thread.name
        thread_id = thread.ident
        is_alive = thread.is_alive()

        thread_list.append({
            'name': thread_name,
            'id': thread_id,
            'is_alive': is_alive
        })

    return {
        'thread_num': num_threads,
        'threads': thread_list
    }


# 数据库连接池状态接口
@app.route('/db-pool-stat')
def pool_stat():
    engine = db.engine
    return {
        'pool_size': engine.pool.size(),
        'checked_in_connections': engine.pool.checkedin(),
        'checked_out_connections': engine.pool.checkedout(),
        'overflow_connections': engine.pool.overflow(),
        'connection_timeout': engine.pool.timeout(),
        'recycle_time': db.engine.pool._recycle
    }


# 如果直接运行此文件，则启动Flask应用
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)