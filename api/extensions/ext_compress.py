from flask import Flask


def init_app(app: Flask):
    if app.config.get('API_COMPRESSION_ENABLED'):
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

