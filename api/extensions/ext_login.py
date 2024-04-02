import flask_login

login_manager = flask_login.LoginManager()


def init_app(app):
    """
    初始化Flask应用的登录管理器。

    参数:
    - app: Flask应用实例，即将被登录管理器初始化的Flask应用。

    返回值:
    - 无
    """
    login_manager.init_app(app)
