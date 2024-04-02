import flask_migrate


def init(app, db):
    """
    初始化Flask迁移模块

    参数:
    app - Flask应用实例，用于配置和使用Flask的各种功能。
    db - 数据库实例，通常是Flask-SQLAlchemy扩展提供的，用于数据库操作。

    返回值:
    无
    """
    flask_migrate.Migrate(app, db)  # 初始化Flask迁移模块，将应用和数据库实例关联起来
