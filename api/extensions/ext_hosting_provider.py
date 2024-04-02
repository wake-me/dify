from flask import Flask

from core.hosting_configuration import HostingConfiguration

hosting_configuration = HostingConfiguration()


def init_app(app: Flask):
    """
    初始化应用程序的配置。

    参数:
    app: Flask - 需要进行配置初始化的Flask应用实例。
    
    返回值:
    无
    """
    hosting_configuration.init_app(app)  # 将当前应用实例与配置管理器进行绑定
