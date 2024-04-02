from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def init_app(app):
    """
    初始化数据库与Flask应用的连接。
    
    参数:
    - app: Flask应用实例，用于配置和使用数据库。
    
    返回值:
    - 无
    """
    db.init_app(app)  # 将Flask应用与数据库初始化连接
