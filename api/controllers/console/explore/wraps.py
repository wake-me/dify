from functools import wraps

from flask_login import current_user
from flask_restful import Resource
from werkzeug.exceptions import NotFound

from controllers.console.wraps import account_initialization_required
from extensions.ext_database import db
from libs.login import login_required
from models.model import InstalledApp


def installed_app_required(view=None):
    """
    装饰器，确保视图函数有有效的已安装应用ID作为参数，并验证该应用是否存在。

    :param view: 需要被装饰的视图函数，该参数为可选，默认为None。
    :return: 包装后的视图函数，如果提供了view参数，则直接返回装饰后的视图函数；否则返回装饰器函数。
    """

    def decorator(view):
        @wraps(view)
        def decorated(*args, **kwargs):
            if not kwargs.get("installed_app_id"):
                raise ValueError("missing installed_app_id in path parameters")

            installed_app_id = kwargs.get("installed_app_id")
            installed_app_id = str(installed_app_id)

            del kwargs["installed_app_id"]

            installed_app = (
                db.session.query(InstalledApp)
                .filter(
                    InstalledApp.id == str(installed_app_id), InstalledApp.tenant_id == current_user.current_tenant_id
                )
                .first()
            )

            # 如果查询不到已安装的应用，则抛出未找到的异常
            if installed_app is None:
                raise NotFound("Installed app not found")

            # 如果已安装的应用没有关联的应用信息，则删除该安装记录，并抛出未找到的异常
            if not installed_app.app:
                db.session.delete(installed_app)
                db.session.commit()

                raise NotFound("Installed app not found")

            # 执行原视图函数，并传入验证过的已安装应用实例及其他参数
            return view(installed_app, *args, **kwargs)

        return decorated

    # 如果提供了view参数，则直接返回装饰后的视图函数；否则返回装饰器函数
    if view:
        return decorator(view)
    return decorator


class InstalledAppResource(Resource):
    """
    已安装应用资源类，继承自Resource类。这个类用于表示一个需要多个条件装饰器修饰的资源，
    例如需要验证应用是否已安装、账户是否完成初始化以及用户是否登录。

    属性:
    - method_decorators (list): 一个包含多个装饰器函数的列表，这些装饰器将按逆序应用于类的方法。
      如果存在多个装饰器，需要注意它们的顺序需要反转。
    """
    # 必须逆序排列，如果存在多个装饰器
    method_decorators = [installed_app_required, account_initialization_required, login_required]