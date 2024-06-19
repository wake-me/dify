import dataclasses
import datetime
from collections import defaultdict, deque
from collections.abc import Callable
from decimal import Decimal
from enum import Enum
from ipaddress import IPv4Address, IPv4Interface, IPv4Network, IPv6Address, IPv6Interface, IPv6Network
from pathlib import Path, PurePath
from re import Pattern
from types import GeneratorType
from typing import Any, Optional, Union
from uuid import UUID

from pydantic import BaseModel
from pydantic.networks import AnyUrl, NameEmail
from pydantic.types import SecretBytes, SecretStr
from pydantic_extra_types.color import Color

from ._compat import PYDANTIC_V2, Url, _model_dump


# 从Pydantic v1直接获取，未做修改
def isoformat(o: Union[datetime.date, datetime.time]) -> str:
    """
    将日期或时间对象格式化为ISO格式的字符串。

    参数:
        o (Union[datetime.date, datetime.time]): 需要格式化的日期或时间对象。

    返回:
        str: 格式化后的ISO格式字符串。
    """
    return o.isoformat()


# 从Pydantic v1直接获取，未做修改
# TODO: pv2 是否应该返回字符串而不是数值？
def decimal_encoder(dec_value: Decimal) -> Union[int, float]:
    """
    将Decimal类型编码为整型或浮点型。
    
    如果Decimal没有指数部分，则编码为整型；否则编码为浮点型。
    这在使用ConstrainedDecimal来表示Numeric(x,0)时非常有用，
    在这种情况下，使用整型（但不是int类型）是常见的。如果将此编码为浮点型，
    将导致在encode和parse之间无法完成循环。我们的Id类型就是这种情况的一个典型例子。

    参数:
        dec_value (Decimal): 需要编码的Decimal值。

    返回:
        Union[int, float]: 编码后的整型或浮点型值。
    """
    if dec_value.as_tuple().exponent >= 0:  # 检查指数是否大于等于0
        return int(dec_value)
    else:
        return float(dec_value)


# 定义了一个基于类型的编码器字典，用于将不同类型的对象转换为可序列化的形式
ENCODERS_BY_TYPE: dict[type[Any], Callable[[Any], Any]] = {
    bytes: lambda o: o.decode(),  # 将bytes类型转换为字符串
    Color: str,  # 直接使用str函数对Color类型进行转换
    datetime.date: isoformat,  # 使用isoformat将日期转换为字符串
    datetime.datetime: isoformat,  # 使用isoformat将日期时间转换为字符串
    datetime.time: isoformat,  # 使用isoformat将时间转换为字符串
    datetime.timedelta: lambda td: td.total_seconds(),  # 将时间差转换为秒数
    Decimal: decimal_encoder,  # 使用decimal_encoder函数将Decimal类型转换为字符串
    Enum: lambda o: o.value,  # 获取枚举类型的值
    frozenset: list,  # 将不可变集合转换为列表
    deque: list,  # 将双端队列转换为列表
    GeneratorType: list,  # 将生成器转换为列表
    IPv4Address: str,  # 直接将IPv4地址转换为字符串
    IPv4Interface: str,  # 直接将IPv4接口转换为字符串
    IPv4Network: str,  # 直接将IPv4网络转换为字符串
    IPv6Address: str,  # 直接将IPv6地址转换为字符串
    IPv6Interface: str,  # 直接将IPv6接口转换为字符串
    IPv6Network: str,  # 直接将IPv6网络转换为字符串
    NameEmail: str,  # 直接将名称和电子邮件地址转换为字符串
    Path: str,  # 将路径对象转换为字符串
    Pattern: lambda o: o.pattern,  # 获取正则表达式的模式字符串
    SecretBytes: str,  # 将秘密字节转换为字符串
    SecretStr: str,  # 将秘密字符串转换为字符串
    set: list,  # 将集合转换为列表
    UUID: str,  # 将UUID对象转换为字符串
    Url: str,  # 直接将URL转换为字符串
    AnyUrl: str,  # 直接将任何URL转换为字符串
}

def generate_encoders_by_class_tuples(
    type_encoder_map: dict[Any, Callable[[Any], Any]]
) -> dict[Callable[[Any], Any], tuple[Any, ...]]:
    """
    根据类型到编码器的映射，生成编码器到类型元组的映射。
    
    参数:
    type_encoder_map: dict[Any, Callable[[Any], Any]] - 一个映射，其键为任意类型，值为对该类型数据进行编码的可调用对象。
    
    返回值:
    dict[Callable[[Any], Any], tuple[Any, ...]] - 一个映射，其键为编码器（可调用对象），值为一个类型元组，表示该编码器所对应的类型。
    """
    # 使用defaultdict以空元组初始化编码器到类型元组的映射
    encoders_by_class_tuples: dict[Callable[[Any], Any], tuple[Any, ...]] = defaultdict(
        tuple
    )
    # 遍历类型到编码器的映射，为每个编码器增加对应的类型到编码器到类型元组的映射中
    for type_, encoder in type_encoder_map.items():
        encoders_by_class_tuples[encoder] += (type_,)
    return encoders_by_class_tuples


# 通过ENCODERS_BY_TYPE生成encoders_by_class_tuples
encoders_by_class_tuples = generate_encoders_by_class_tuples(ENCODERS_BY_TYPE)

def jsonable_encoder(
    obj: Any,
    by_alias: bool = True,
    exclude_unset: bool = False,
    exclude_defaults: bool = False,
    exclude_none: bool = False,
    custom_encoder: Optional[dict[Any, Callable[[Any], Any]]] = None,
    sqlalchemy_safe: bool = True,
) -> Any:
    """
    将各种类型的对象编码为JSON序列化友好的格式。
    
    参数:
    - obj: 要编码的对象。
    - by_alias: 是否按照Pydantic模型的别名进行编码，默认为True。
    - exclude_unset: 是否排除未设置的字段，默认为False。
    - exclude_defaults: 是否排除默认值的字段，默认为False。
    - exclude_none: 是否排除值为None的字段，默认为False。
    - custom_encoder: 自定义对象编码器字典，键为类型，值为编码函数。
    - sqlalchemy_safe: 是否在编码时安全处理SQLAlchemy相关对象，默认为True。
    
    返回值:
    - 编码后的对象，通常是字典或列表，可直接进行JSON序列化。
    """
    custom_encoder = custom_encoder or {}
    # 使用自定义编码器进行编码
    if custom_encoder:
        if type(obj) in custom_encoder:
            return custom_encoder[type(obj)](obj)
        else:
            for encoder_type, encoder_instance in custom_encoder.items():
                if isinstance(obj, encoder_type):
                    return encoder_instance(obj)
    # 处理Pydantic模型
    if isinstance(obj, BaseModel):
        # 序列化Pydantic模型为字典，并递归处理其中的字段
        encoders: dict[Any, Any] = {}
        if not PYDANTIC_V2:
            encoders = getattr(obj.__config__, "json_encoders", {})  # type: ignore[attr-defined]
            if custom_encoder:
                encoders.update(custom_encoder)
        obj_dict = _model_dump(
            obj,
            mode="json",
            include=None,
            exclude=None,
            by_alias=by_alias,
            exclude_unset=exclude_unset,
            exclude_none=exclude_none,
            exclude_defaults=exclude_defaults,
        )
        if "__root__" in obj_dict:
            obj_dict = obj_dict["__root__"]
        return jsonable_encoder(
            obj_dict,
            exclude_none=exclude_none,
            exclude_defaults=exclude_defaults,
            # 逐步移除对Pydantic v1的支持
            custom_encoder=encoders,
            sqlalchemy_safe=sqlalchemy_safe,
        )
    # 处理数据类
    if dataclasses.is_dataclass(obj):
        obj_dict = dataclasses.asdict(obj)
        return jsonable_encoder(
            obj_dict,
            by_alias=by_alias,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
            custom_encoder=custom_encoder,
            sqlalchemy_safe=sqlalchemy_safe,
        )
    # 处理枚举类型
    if isinstance(obj, Enum):
        return obj.value
    # 处理路径对象
    if isinstance(obj, PurePath):
        return str(obj)
    # 处理基本数据类型
    if isinstance(obj, str | int | float | type(None)):
        return obj
    # 处理Decimal类型，转为字符串
    if isinstance(obj, Decimal):
        return format(obj, 'f')
    # 处理字典类型
    if isinstance(obj, dict):
        encoded_dict = {}
        allowed_keys = set(obj.keys())
        for key, value in obj.items():
            # 安全地处理字典的键和值，并递归编码
            encoded_key = jsonable_encoder(
                key,
                by_alias=by_alias,
                exclude_unset=exclude_unset,
                exclude_none=exclude_none,
                custom_encoder=custom_encoder,
                sqlalchemy_safe=sqlalchemy_safe,
            )
            encoded_value = jsonable_encoder(
                value,
                by_alias=by_alias,
                exclude_unset=exclude_unset,
                exclude_none=exclude_none,
                custom_encoder=custom_encoder,
                sqlalchemy_safe=sqlalchemy_safe,
            )
            encoded_dict[encoded_key] = encoded_value
        return encoded_dict
    # 处理序列类型（列表、集合、元组等）
    if isinstance(obj, list | set | frozenset | GeneratorType | tuple | deque):
        encoded_list = []
        for item in obj:
            encoded_list.append(
                jsonable_encoder(
                    item,
                    by_alias=by_alias,
                    exclude_unset=exclude_unset,
                    exclude_defaults=exclude_defaults,
                    exclude_none=exclude_none,
                    custom_encoder=custom_encoder,
                    sqlalchemy_safe=sqlalchemy_safe,
                )
            )
        return encoded_list

    # 使用注册的类型特定编码器
    if type(obj) in ENCODERS_BY_TYPE:
        return ENCODERS_BY_TYPE[type(obj)](obj)
    for encoder, classes_tuple in encoders_by_class_tuples.items():
        if isinstance(obj, classes_tuple):
            return encoder(obj)

    # 尝试将对象转换为字典，如果失败则尝试使用vars()，最后抛出异常
    try:
        data = dict(obj)
    except Exception as e:
        errors: list[Exception] = []
        errors.append(e)
        try:
            data = vars(obj)
        except Exception as e:
            errors.append(e)
            raise ValueError(errors) from e
    return jsonable_encoder(
        data,
        by_alias=by_alias,
        exclude_unset=exclude_unset,
        exclude_defaults=exclude_defaults,
        exclude_none=exclude_none,
        custom_encoder=custom_encoder,
        sqlalchemy_safe=sqlalchemy_safe,
    )