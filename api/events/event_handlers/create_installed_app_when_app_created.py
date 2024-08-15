from events.app_event import app_was_created
from extensions.ext_database import db
from models.model import InstalledApp


# 当创建应用时触发的信号处理器
@app_was_created.connect
def handle(sender, **kwargs):
    """
    当一个应用被创建时，自动创建一个安装应用的记录。

    参数:
    - sender: 发送信号的源头，即被创建的应用对象。
    - **kwargs: 关键字参数，包含任何额外的信息。

    返回值:
    - 无
    """
    # 获取发送信号的应用对象
    app = sender
    # 创建一个安装应用的记录
    installed_app = InstalledApp(
        tenant_id=app.tenant_id,
        app_id=app.id,
        app_owner_tenant_id=app.tenant_id,
    )
    # 将新创建的安装应用记录添加到数据库会话中
    db.session.add(installed_app)
    # 提交数据库会话，使更改持久化
    db.session.commit()