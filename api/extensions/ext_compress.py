from flask import Flask


def init_app(app: Flask):
    """
    初始化Flask应用，如果启用了API压缩，则配置并启用Flask_Compress扩展。

    参数:
    app: Flask - 需要初始化的Flask应用实例。
    
    返回值:
    无
    """
    # 检查是否启用了API压缩
    if app.config.get('API_COMPRESSION_ENABLED', False):
        from flask_compress import Compress

        # 配置压缩的MIME类型
        app.config['COMPRESS_MIMETYPES'] = [
            'application/json',
            'image/svg+xml',
            'text/html',
        ]

        # 初始化并注册Flask_Compress扩展
        compress = Compress()
        compress.init_app(app)

