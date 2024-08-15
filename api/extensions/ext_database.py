from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData

POSTGRES_INDEXES_NAMING_CONVENTION = {
    "ix": "%(column_0_label)s_idx",
    "uq": "%(table_name)s_%(column_0_name)s_key",
    "ck": "%(table_name)s_%(constraint_name)s_check",
    "fk": "%(table_name)s_%(column_0_name)s_fkey",
    "pk": "%(table_name)s_pkey",
}

metadata = MetaData(naming_convention=POSTGRES_INDEXES_NAMING_CONVENTION)
db = SQLAlchemy(metadata=metadata)


def init_app(app):
    """
    初始化数据库与Flask应用的连接。
    
    参数:
    - app: Flask应用实例，用于配置和使用数据库。
    
    返回值:
    - 无
    """
    db.init_app(app)  # 将Flask应用与数据库初始化连接
