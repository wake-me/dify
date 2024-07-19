from events.app_event import app_was_deleted
from extensions.ext_database import db
from models.model import InstalledApp


# 当检测到app被删除的信号时，触发此函数进行相应处理
@app_was_deleted.connect
def handle(sender, **kwargs):
    """
    处理应用被删除的信号。
    
    参数:
    - sender: 发送信号的对象，此处为被删除的应用。
    - **kwargs: 关键字参数，包含额外的信号信息。
    
    返回值:
    无
    """
    app = sender  # 获取发送信号的应用对象
    # 查询数据库中与该应用相关联的所有已安装应用
    installed_apps = db.session.query(InstalledApp).filter(InstalledApp.app_id == app.id).all()
    for installed_app in installed_apps:
        # 对于每个相关联的已安装应用，将其从数据库中删除
        db.session.delete(installed_app)
    # 提交数据库事务，确认删除操作
    db.session.commit()
