import os

# 导入dotenv模块，用于加载环境变量
import dotenv

# 加载.env文件中的环境变量
dotenv.load_dotenv()

# 默认配置字典，包含数据库、Redis、OAuth、Console和文件存储等服务的配置项
DEFAULTS = {
    'DB_USERNAME': 'postgres',  # 数据库用户名，默认为postgres
    'DB_PASSWORD': '',  # 数据库密码，默认为空
    'DB_HOST': 'localhost',  # 数据库主机，默认为localhost
    'DB_PORT': '5432',  # 数据库端口，默认为5432
    'DB_DATABASE': 'dify',  # 数据库名，默认为dify
    'DB_CHARSET': '',  # 数据库字符集，默认为空
    'REDIS_HOST': 'localhost',  # Redis主机，默认为localhost
    'REDIS_PORT': '6379',  # Redis端口，默认为6379
    'REDIS_DB': '0',  # Redis数据库编号，默认为0
    'REDIS_USE_SSL': 'False',  # 是否使用SSL连接Redis，默认为False
    'OAUTH_REDIRECT_PATH': '/console/api/oauth/authorize',  # OAuth授权回调路径
    'OAUTH_REDIRECT_INDEX_PATH': '/',  # OAuth授权成功后的跳转首页路径
    'CONSOLE_WEB_URL': 'https://cloud.dify.ai',  # Console Web服务URL
    'CONSOLE_API_URL': 'https://cloud.dify.ai',  # Console API服务URL
    'SERVICE_API_URL': 'https://api.dify.ai',  # 服务API URL
    'APP_WEB_URL': 'https://udify.app',  # 应用Web URL
    'FILES_URL': '',  # 文件访问基础URL，默认为空
    'S3_ADDRESS_STYLE': 'auto',  # S3地址风格，默认为自动
    'STORAGE_TYPE': 'local',  # 存储类型，默认为本地存储
    'STORAGE_LOCAL_PATH': 'storage',  # 本地存储路径，默认为storage
    'CHECK_UPDATE_URL': 'https://updates.dify.ai',  # 检查更新的URL
    'DEPLOY_ENV': 'PRODUCTION',  # 部署环境，默认为生产环境
    'SQLALCHEMY_POOL_SIZE': 30,  # SQLAlchemy连接池大小
    'SQLALCHEMY_POOL_RECYCLE': 3600,  # SQLAlchemy连接池回收时间
    'SQLALCHEMY_ECHO': 'False',  # SQLAlchemy日志输出开关，默认关闭
    'SENTRY_TRACES_SAMPLE_RATE': 1.0,  # Sentry跟踪采样率
    'SENTRY_PROFILES_SAMPLE_RATE': 1.0,  # Sentry性能分析采样率
    'WEAVIATE_GRPC_ENABLED': 'True',  # 是否启用WEAVIATE的gRPC服务
    'WEAVIATE_BATCH_SIZE': 100,  # WEAVIATE批处理大小
    'QDRANT_CLIENT_TIMEOUT': 20,  # Qdrant客户端超时时间
    'CELERY_BACKEND': 'database',  # Celery任务后端
    'LOG_LEVEL': 'INFO',  # 日志级别，默认为INFO
    'HOSTED_OPENAI_QUOTA_LIMIT': 200,  # 托管的OpenAI配额限制
    'HOSTED_OPENAI_TRIAL_ENABLED': 'False',  # 是否启用OpenAI试用
    'HOSTED_OPENAI_TRIAL_MODELS': 'gpt-3.5-turbo,gpt-3.5-turbo-1106,gpt-3.5-turbo-instruct,gpt-3.5-turbo-16k,gpt-3.5-turbo-16k-0613,gpt-3.5-turbo-0613,gpt-3.5-turbo-0125,text-davinci-003', 
    'HOSTED_OPENAI_PAID_ENABLED': 'False',  # 是否启用OpenAI付费模型
    'HOSTED_OPENAI_PAID_MODELS': 'gpt-4,gpt-4-turbo-preview,gpt-4-1106-preview,gpt-4-0125-preview,gpt-3.5-turbo,gpt-3.5-turbo-16k,gpt-3.5-turbo-16k-0613,gpt-3.5-turbo-1106,gpt-3.5-turbo-0613,gpt-3.5-turbo-0125,gpt-3.5-turbo-instruct,text-davinci-003',    
    'HOSTED_AZURE_OPENAI_ENABLED': 'False',  # 是否启用Azure OpenAI服务
    'HOSTED_AZURE_OPENAI_QUOTA_LIMIT': 200,  # Azure OpenAI配额限制
    'HOSTED_ANTHROPIC_QUOTA_LIMIT': 600000,  # Hosted Anthropic配额限制
    'HOSTED_ANTHROPIC_TRIAL_ENABLED': 'False',  # 是否启用Anthropic试用
    'HOSTED_ANTHROPIC_PAID_ENABLED': 'False',  # 是否启用Anthropic付费
    'HOSTED_MODERATION_ENABLED': 'False',  # 是否启用托管的内容审核
    'HOSTED_MODERATION_PROVIDERS': '',  # 内容审核服务提供商列表
    'CLEAN_DAY_SETTING': 30,  # 数据清理周期（天）
    'UPLOAD_FILE_SIZE_LIMIT': 15,  # 文件上传大小限制（MB）
    'UPLOAD_FILE_BATCH_LIMIT': 5,  # 批量上传文件限制
    'UPLOAD_IMAGE_FILE_SIZE_LIMIT': 10,  # 图片文件上传大小限制（MB）
    'OUTPUT_MODERATION_BUFFER_SIZE': 300,  # 输出审核缓冲区大小
    'MULTIMODAL_SEND_IMAGE_FORMAT': 'base64',  # 多模态发送图片的格式
    'INVITE_EXPIRY_HOURS': 72,  # 邀请链接有效期（小时）
    'BILLING_ENABLED': 'False',  # 是否启用计费功能
    'CAN_REPLACE_LOGO': 'False',  # 是否允许替换Logo
    'ETL_TYPE': 'dify',  # ETL类型
    'KEYWORD_STORE': 'jieba',  # 关键词存储方式
    'BATCH_UPLOAD_LIMIT': 20,  # 批量上传限制
    'TOOL_ICON_CACHE_MAX_AGE': 3600,  # 工具图标缓存最大年龄（秒）
    'KEYWORD_DATA_SOURCE_TYPE': 'database',
}


def get_env(key):
    """
    获取环境变量的值。
    
    参数:
    key: 环境变量的键名。
    
    返回值:
    如果环境变量存在，则返回其值；如果不存在，并且在DEFAULTS中定义了该键，则返回DEFAULTS中对应的值；如果都不存在，返回None。
    """
    return os.environ.get(key, DEFAULTS.get(key))


def get_bool_env(key):
    """
    获取环境变量的布尔值表示。
    
    参数:
    key: 环境变量的键名。
    
    返回值:
    如果环境变量存在且值为"true"（不区分大小写），则返回True；如果不存在或值不为"true"，则返回False。
    """
    value = get_env(key)
    # 将环境变量的值转换为小写，并在值为"true"时返回True，否则返回False
    return value.lower() == 'true' if value is not None else False


def get_cors_allow_origins(env, default):
    """
    获取跨域资源共享(CORS)允许的来源列表。
    
    参数:
    env: 环境变量的键名，预期存储一个以逗号分隔的来源列表。
    default: 如果环境变量未设置，默认返回的来源列表。
    
    返回值:
    根据环境变量设置的来源列表，如果环境变量未设置，则返回default参数指定的来源列表。
    """
    cors_allow_origins = []
    # 如果环境变量设置，则解析其值为来源列表，否则使用默认来源列表
    if get_env(env):
        for origin in get_env(env).split(','):
            cors_allow_origins.append(origin)
    else:
        cors_allow_origins = [default]

    return cors_allow_origins


class Config:
    """应用配置类，用于初始化应用程序的各种配置项。"""

    def __init__(self):
        # 初始化通用配置
        self.CURRENT_VERSION = "0.5.11"  # 应用当前版本
        self.COMMIT_SHA = get_env('COMMIT_SHA')  # 版本控制的提交哈希值
        self.EDITION = "SELF_HOSTED"  # 应用版本，此处为自托管版
        self.DEPLOY_ENV = get_env('DEPLOY_ENV')  # 部署环境
        self.TESTING = False  # 是否为测试模式
        self.LOG_LEVEL = get_env('LOG_LEVEL')  # 日志级别

        # 初始化_console_api的URL前缀
        self.CONSOLE_API_URL = get_env('CONSOLE_API_URL')

        # 初始化_console_web的URL前缀
        self.CONSOLE_WEB_URL = get_env('CONSOLE_WEB_URL')

        # 初始化WebApp的URL前缀
        self.APP_WEB_URL = get_env('APP_WEB_URL')

        # 初始化服务API的URL前缀
        self.SERVICE_API_URL = get_env('SERVICE_API_URL')

        # 初始化文件预览或下载的URL前缀
        self.FILES_URL = get_env('FILES_URL') if get_env('FILES_URL') else self.CONSOLE_API_URL

        # 初始化应用的密钥，用于会话cookie的安全签名
        self.SECRET_KEY = get_env('SECRET_KEY')

        # 初始化CORS允许的来源
        self.CONSOLE_CORS_ALLOW_ORIGINS = get_cors_allow_origins(
            'CONSOLE_CORS_ALLOW_ORIGINS', self.CONSOLE_WEB_URL)
        self.WEB_API_CORS_ALLOW_ORIGINS = get_cors_allow_origins(
            'WEB_API_CORS_ALLOW_ORIGINS', '*')

        # 检查更新的URL
        self.CHECK_UPDATE_URL = get_env('CHECK_UPDATE_URL')

        # 初始化数据库配置
        db_credentials = {
            key: get_env(key) for key in
            ['DB_USERNAME', 'DB_PASSWORD', 'DB_HOST', 'DB_PORT', 'DB_DATABASE', 'DB_CHARSET']
        }
        db_extras = f"?client_encoding={db_credentials['DB_CHARSET']}" if db_credentials['DB_CHARSET'] else ""
        self.SQLALCHEMY_DATABASE_URI = f"postgresql://{db_credentials['DB_USERNAME']}:{db_credentials['DB_PASSWORD']}@{db_credentials['DB_HOST']}:{db_credentials['DB_PORT']}/{db_credentials['DB_DATABASE']}{db_extras}"
        self.SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_size': int(get_env('SQLALCHEMY_POOL_SIZE')),
            'pool_recycle': int(get_env('SQLALCHEMY_POOL_RECYCLE'))
        }
        self.SQLALCHEMY_ECHO = get_bool_env('SQLALCHEMY_ECHO')

        # 初始化Redis配置
        self.REDIS_HOST = get_env('REDIS_HOST')
        self.REDIS_PORT = get_env('REDIS_PORT')
        self.REDIS_USERNAME = get_env('REDIS_USERNAME')
        self.REDIS_PASSWORD = get_env('REDIS_PASSWORD')
        self.REDIS_DB = get_env('REDIS_DB')
        self.REDIS_USE_SSL = get_bool_env('REDIS_USE_SSL')

        # 初始化Celery worker配置
        self.CELERY_BROKER_URL = get_env('CELERY_BROKER_URL')
        self.CELERY_BACKEND = get_env('CELERY_BACKEND')
        self.CELERY_RESULT_BACKEND = 'db+{}'.format(self.SQLALCHEMY_DATABASE_URI) \
            if self.CELERY_BACKEND == 'database' else self.CELERY_BROKER_URL
        self.BROKER_USE_SSL = self.CELERY_BROKER_URL.startswith('rediss://')

        # 初始化文件存储配置
        self.STORAGE_TYPE = get_env('STORAGE_TYPE')
        self.STORAGE_LOCAL_PATH = get_env('STORAGE_LOCAL_PATH')
        self.S3_ENDPOINT = get_env('S3_ENDPOINT')
        self.S3_BUCKET_NAME = get_env('S3_BUCKET_NAME')
        self.S3_ACCESS_KEY = get_env('S3_ACCESS_KEY')
        self.S3_SECRET_KEY = get_env('S3_SECRET_KEY')
        self.S3_REGION = get_env('S3_REGION')
        self.S3_ADDRESS_STYLE = get_env('S3_ADDRESS_STYLE')
        self.AZURE_BLOB_ACCOUNT_NAME = get_env('AZURE_BLOB_ACCOUNT_NAME')
        self.AZURE_BLOB_ACCOUNT_KEY = get_env('AZURE_BLOB_ACCOUNT_KEY')
        self.AZURE_BLOB_CONTAINER_NAME = get_env('AZURE_BLOB_CONTAINER_NAME')
        self.AZURE_BLOB_ACCOUNT_URL = get_env('AZURE_BLOB_ACCOUNT_URL')

        # 初始化向量存储配置
        self.VECTOR_STORE = get_env('VECTOR_STORE')
        self.KEYWORD_STORE = get_env('KEYWORD_STORE')
        self.QDRANT_URL = get_env('QDRANT_URL')
        self.QDRANT_API_KEY = get_env('QDRANT_API_KEY')
        self.QDRANT_CLIENT_TIMEOUT = get_env('QDRANT_CLIENT_TIMEOUT')
        self.MILVUS_HOST = get_env('MILVUS_HOST')
        self.MILVUS_PORT = get_env('MILVUS_PORT')
        self.MILVUS_USER = get_env('MILVUS_USER')
        self.MILVUS_PASSWORD = get_env('MILVUS_PASSWORD')
        self.MILVUS_SECURE = get_env('MILVUS_SECURE')
        self.WEAVIATE_ENDPOINT = get_env('WEAVIATE_ENDPOINT')
        self.WEAVIATE_API_KEY = get_env('WEAVIATE_API_KEY')
        self.WEAVIATE_GRPC_ENABLED = get_bool_env('WEAVIATE_GRPC_ENABLED')
        self.WEAVIATE_BATCH_SIZE = int(get_env('WEAVIATE_BATCH_SIZE'))

        # 初始化邮件配置
        self.MAIL_TYPE = get_env('MAIL_TYPE')
        self.MAIL_DEFAULT_SEND_FROM = get_env('MAIL_DEFAULT_SEND_FROM')
        self.RESEND_API_KEY = get_env('RESEND_API_KEY')
        self.RESEND_API_URL = get_env('RESEND_API_URL')
        self.SMTP_SERVER = get_env('SMTP_SERVER')
        self.SMTP_PORT = get_env('SMTP_PORT')
        self.SMTP_USERNAME = get_env('SMTP_USERNAME')
        self.SMTP_PASSWORD = get_env('SMTP_PASSWORD')
        self.SMTP_USE_TLS = get_bool_env('SMTP_USE_TLS')

        # 初始化工作区配置
        self.INVITE_EXPIRY_HOURS = int(get_env('INVITE_EXPIRY_HOURS'))

        # 初始化Sentry配置
        self.SENTRY_DSN = get_env('SENTRY_DSN')
        self.SENTRY_TRACES_SAMPLE_RATE = float(get_env('SENTRY_TRACES_SAMPLE_RATE'))
        self.SENTRY_PROFILES_SAMPLE_RATE = float(get_env('SENTRY_PROFILES_SAMPLE_RATE'))

        # 初始化业务配置
        self.MULTIMODAL_SEND_IMAGE_FORMAT = get_env('MULTIMODAL_SEND_IMAGE_FORMAT')
        self.CLEAN_DAY_SETTING = get_env('CLEAN_DAY_SETTING')
        self.UPLOAD_FILE_SIZE_LIMIT = int(get_env('UPLOAD_FILE_SIZE_LIMIT'))
        self.UPLOAD_FILE_BATCH_LIMIT = int(get_env('UPLOAD_FILE_BATCH_LIMIT'))
        self.UPLOAD_IMAGE_FILE_SIZE_LIMIT = int(get_env('UPLOAD_IMAGE_FILE_SIZE_LIMIT'))
        self.OUTPUT_MODERATION_BUFFER_SIZE = int(get_env('OUTPUT_MODERATION_BUFFER_SIZE'))

        # 初始化Notion集成设置
        self.NOTION_CLIENT_ID = get_env('NOTION_CLIENT_ID')
        self.NOTION_CLIENT_SECRET = get_env('NOTION_CLIENT_SECRET')
        self.NOTION_INTEGRATION_TYPE = get_env('NOTION_INTEGRATION_TYPE')
        self.NOTION_INTERNAL_SECRET = get_env('NOTION_INTERNAL_SECRET')
        self.NOTION_INTEGRATION_TOKEN = get_env('NOTION_INTEGRATION_TOKEN')

        # 初始化平台配置
        self.HOSTED_OPENAI_API_KEY = get_env('HOSTED_OPENAI_API_KEY')
        self.HOSTED_OPENAI_API_BASE = get_env('HOSTED_OPENAI_API_BASE')
        self.HOSTED_OPENAI_API_ORGANIZATION = get_env('HOSTED_OPENAI_API_ORGANIZATION')
        self.HOSTED_OPENAI_TRIAL_ENABLED = get_bool_env('HOSTED_OPENAI_TRIAL_ENABLED')
        self.HOSTED_OPENAI_TRIAL_MODELS = get_env('HOSTED_OPENAI_TRIAL_MODELS')
        self.HOSTED_OPENAI_QUOTA_LIMIT = int(get_env('HOSTED_OPENAI_QUOTA_LIMIT'))
        self.HOSTED_OPENAI_PAID_ENABLED = get_bool_env('HOSTED_OPENAI_PAID_ENABLED')
        self.HOSTED_OPENAI_PAID_MODELS = get_env('HOSTED_OPENAI_PAID_MODELS')
        self.HOSTED_AZURE_OPENAI_ENABLED = get_bool_env('HOSTED_AZURE_OPENAI_ENABLED')
        self.HOSTED_AZURE_OPENAI_API_KEY = get_env('HOSTED_AZURE_OPENAI_API_KEY')
        self.HOSTED_AZURE_OPENAI_API_BASE = get_env('HOSTED_AZURE_OPENAI_API_BASE')
        self.HOSTED_AZURE_OPENAI_QUOTA_LIMIT = int(get_env('HOSTED_AZURE_OPENAI_QUOTA_LIMIT'))
        self.HOSTED_ANTHROPIC_API_BASE = get_env('HOSTED_ANTHROPIC_API_BASE')
        self.HOSTED_ANTHROPIC_API_KEY = get_env('HOSTED_ANTHROPIC_API_KEY')
        self.HOSTED_ANTHROPIC_TRIAL_ENABLED = get_bool_env('HOSTED_ANTHROPIC_TRIAL_ENABLED')
        self.HOSTED_ANTHROPIC_QUOTA_LIMIT = int(get_env('HOSTED_ANTHROPIC_QUOTA_LIMIT'))
        self.HOSTED_ANTHROPIC_PAID_ENABLED = get_bool_env('HOSTED_ANTHROPIC_PAID_ENABLED')
        self.HOSTED_MINIMAX_ENABLED = get_bool_env('HOSTED_MINIMAX_ENABLED')
        self.HOSTED_SPARK_ENABLED = get_bool_env('HOSTED_SPARK_ENABLED')
        self.HOSTED_ZHIPUAI_ENABLED = get_bool_env('HOSTED_ZHIPUAI_ENABLED')
        self.HOSTED_MODERATION_ENABLED = get_bool_env('HOSTED_MODERATION_ENABLED')
        self.HOSTED_MODERATION_PROVIDERS = get_env('HOSTED_MODERATION_PROVIDERS')
        self.ETL_TYPE = get_env('ETL_TYPE')
        self.UNSTRUCTURED_API_URL = get_env('UNSTRUCTURED_API_URL')
        self.BILLING_ENABLED = get_bool_env('BILLING_ENABLED')
        self.CAN_REPLACE_LOGO = get_bool_env('CAN_REPLACE_LOGO')
        self.BATCH_UPLOAD_LIMIT = get_env('BATCH_UPLOAD_LIMIT')
        self.API_COMPRESSION_ENABLED = get_bool_env('API_COMPRESSION_ENABLED')
        self.TOOL_ICON_CACHE_MAX_AGE = get_env('TOOL_ICON_CACHE_MAX_AGE')
        self.KEYWORD_DATA_SOURCE_TYPE = get_env('KEYWORD_DATA_SOURCE_TYPE')

class CloudEditionConfig(Config):
    """
    云版本配置类，继承自Config类。用于设置和管理云版本相关的配置信息。
    """
    def __init__(self):
        """
        初始化CloudEditionConfig类的实例。
        """
        super().__init__()  # 调用父类的构造函数进行初始化

        self.EDITION = "CLOUD"  # 设置版本类型为“云”

        # 从环境变量中获取OAuth相关配置
        self.GITHUB_CLIENT_ID = get_env('GITHUB_CLIENT_ID')
        self.GITHUB_CLIENT_SECRET = get_env('GITHUB_CLIENT_SECRET')
        self.GOOGLE_CLIENT_ID = get_env('GOOGLE_CLIENT_ID')
        self.GOOGLE_CLIENT_SECRET = get_env('GOOGLE_CLIENT_SECRET')
        self.OAUTH_REDIRECT_PATH = get_env('OAUTH_REDIRECT_PATH')  # OAuth重定向路径