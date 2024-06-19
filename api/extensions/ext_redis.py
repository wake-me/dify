import redis
from redis.connection import Connection, SSLConnection

redis_client = redis.Redis()


def init_app(app):
    """
    初始化Redis客户端连接。
    
    参数:
    - app: 应用实例，用于获取配置信息。
    
    该函数根据应用的配置信息，初始化一个Redis连接池，并将该连接池绑定到应用的扩展中。
    """
    
    # 根据是否使用SSL选择连接类
    connection_class = Connection
    if app.config.get('REDIS_USE_SSL'):
        connection_class = SSLConnection

    # 配置并创建Redis连接池
    redis_client.connection_pool = redis.ConnectionPool(**{
        'host': app.config.get('REDIS_HOST'),
        'port': app.config.get('REDIS_PORT'),
        'username': app.config.get('REDIS_USERNAME'),
        'password': app.config.get('REDIS_PASSWORD'),
        'db': app.config.get('REDIS_DB'),
        'encoding': 'utf-8',
        'encoding_errors': 'strict',
        'decode_responses': False
    }, connection_class=connection_class)

    # 将Redis客户端绑定到应用扩展
    app.extensions['redis'] = redis_client
