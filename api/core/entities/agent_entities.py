from enum import Enum


class PlanningStrategy(Enum):
    """
    规划策略枚举类，定义了不同的规划策略。

    参数:
    无

    返回值:
    无
    """

    ROUTER = 'router'  # 使用路由器规划
    REACT_ROUTER = 'react_router'  # 使用React路由器规划
    REACT = 'react'  # 使用React框架规划
    FUNCTION_CALL = 'function_call'  # 使用函数调用方式进行规划
