from collections.abc import Callable
from functools import wraps
from typing import Optional, Union

from controllers.console.app.error import AppNotFoundError
from extensions.ext_database import db
from libs.login import current_user
from models.model import App, AppMode


def get_app_model(view: Optional[Callable] = None, *,
                  mode: Union[AppMode, list[AppMode]] = None):
    """
    装饰器函数，用于在视图函数执行前验证和获取应用模型（App Model）。
    
    参数:
    - view: 可选，视图函数。如果传递，则直接装饰该视图函数，否则返回一个装饰器。
    - mode: 可选，应用模式或应用模式列表。用于限制只有特定模式的应用才能访问。
    
    返回:
    - 如果view参数未提供，则返回一个装饰器函数。
    - 如果view参数提供，则返回装饰后的视图函数。
    """

    def decorator(view_func):
        @wraps(view_func)
        def decorated_view(*args, **kwargs):
            # 验证app_id是否在路径参数中
            if not kwargs.get('app_id'):
                raise ValueError('missing app_id in path parameters')

            app_id = kwargs.get('app_id')
            app_id = str(app_id)  # 确保app_id为字符串类型

            del kwargs['app_id']  # 从关键字参数中移除app_id，避免干扰后续逻辑

            # 从数据库查询应用模型，并进行权限验证
            app_model = db.session.query(App).filter(
                App.id == app_id,
                App.tenant_id == current_user.current_tenant_id,
                App.status == 'normal'
            ).first()

            if not app_model:
                raise AppNotFoundError()  # 应用模型未找到，抛出异常

            app_mode = AppMode.value_of(app_model.mode)
            if app_mode == AppMode.CHANNEL:
                raise AppNotFoundError()  # 预设的不可用应用模式，抛出异常

            # 检查应用模式是否符合要求
            if mode is not None:
                if isinstance(mode, list):
                    modes = mode
                else:
                    modes = [mode]  # 将单个模式转换为列表，统一处理逻辑

                if app_mode not in modes:
                    mode_values = {m.value for m in modes}
                    raise AppNotFoundError(f"App mode is not in the supported list: {mode_values}")

            # 将应用模型添加到关键字参数中，供视图函数使用
            kwargs['app_model'] = app_model

            return view_func(*args, **kwargs)
        return decorated_view

    if view is None:
        return decorator  # 如果未提供视图函数，返回装饰器
    else:
        return decorator(view)  # 如果提供了视图函数，直接装饰并返回