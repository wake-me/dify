from typing import Any, Literal

from pydantic import BaseModel
from pydantic.version import VERSION as PYDANTIC_VERSION

# 判断 pydantic 版本，以确定使用哪个版本的模型序列化方法
PYDANTIC_V2 = PYDANTIC_VERSION.startswith("2.")

# 根据 pydantic 版本导入不同的 Url 类
if PYDANTIC_V2:
    from pydantic_core import Url as Url  # pydantic 2.x 版本的 Url 类

    def _model_dump(
        model: BaseModel, mode: Literal["json", "python"] = "json", **kwargs: Any
    ) -> Any:
        """
        序列化 pydantic 模型为 json 或 python 字典格式。
        
        :param model: 要序列化的 pydantic 模型实例。
        :param mode: 序列化的格式，可以是 "json" 或 "python"，默认为 "json"。
        :param kwargs: 传递给序列化方法的额外关键字参数。
        :return: 返回序列化后的数据，格式取决于 mode 参数。
        """
        return model.model_dump(mode=mode, **kwargs)
else:
    from pydantic import AnyUrl as Url  # pydantic 1.x 版本的 Url 类，此处导入但未使用

    def _model_dump(
        model: BaseModel, mode: Literal["json", "python"] = "json", **kwargs: Any
    ) -> Any:
        """
        序列化 pydantic 模型为 json 或 python 字典格式。
        
        :param model: 要序列化的 pydantic 模型实例。
        :param mode: 序列化的格式，可以是 "json" 或 "python"，在 pydantic 1.x 中无效。
        :param kwargs: 传递给 dict 方法的额外关键字参数。
        :return: 返回序列化后的数据，总是以 python 字典格式。
        """
        return model.dict(**kwargs)