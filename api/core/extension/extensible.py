import enum
import importlib
import json
import logging
import os
from typing import Any, Optional

from pydantic import BaseModel

from core.helper.position_helper import sort_to_dict_by_position_map


class ExtensionModule(enum.Enum):
    """
    扩展模块枚举类，定义了系统中可识别的扩展模块类型。

    MODERATION: 用于审核功能的模块。
    EXTERNAL_DATA_TOOL: 用于外部数据工具的模块。
    """
    MODERATION = 'moderation'
    EXTERNAL_DATA_TOOL = 'external_data_tool'


class ModuleExtension(BaseModel):
    """
    模块扩展类，定义了一个模块扩展的基本结构。

    extension_class: 扩展类的引用，可以是任何类型。
    name: 扩展的名称，字符串类型。
    label: 扩展的标签，是一个字典，可以是可选的。
    form_schema: 表单结构定义，以列表形式表示，是可选的。
    builtin: 标记是否为内置扩展，布尔类型，默认为True。
    position: 扩展的位置，整数类型，是可选的。
    """
    extension_class: Any
    name: str
    label: Optional[dict] = None
    form_schema: Optional[list] = None
    builtin: bool = True
    position: Optional[int] = None


class Extensible:
    """
    可扩展类，定义了基本的可扩展性结构。

    module: 一个ExtensionModule枚举实例，指定了该类实例所属的扩展模块类型。
    name: 实例的名称，字符串类型。
    tenant_id: 实例所属的租户ID，字符串类型。
    config: 配置信息，一个字典，是可选的。
    """
    # 类的属性定义
    module: ExtensionModule  # 扩展模块类型

    name: str  # 实例名称
    tenant_id: str  # 租户ID
    config: Optional[dict] = None  # 配置信息，字典类型，可选

    def __init__(self, tenant_id: str, config: Optional[dict] = None) -> None:
        """
        初始化可扩展类实例。

        :param tenant_id: 实例所属的租户ID，字符串类型。
        :param config: 实例的配置信息，字典类型，可选。
        """
        self.tenant_id = tenant_id  # 设置租户ID
        self.config = config  # 设置配置信息

    @classmethod
    def scan_extensions(cls):
        """
        扫描并加载扩展模块。
        
        该方法会从当前类所在的目录开始扫描，查找所有符合条件的扩展模块。每个扩展模块需要满足以下条件：
        - 必须是一个子目录。
        - 子目录中必须包含一个同名的`.py`文件和一个`schema.json`文件（非内置扩展必须）。
        - `.py`文件中必须定义一个继承自`cls`的类。
        
        扫描结果会根据扩展的类型和位置进行排序，并返回一个列表。
        
        参数:
        - cls: 扩展类的基类，用于判断扫描到的类是否为符合条件的扩展类。
        
        返回值:
        - 返回一个包含所有加载的扩展模块信息的列表，列表中的每个元素都是`ModuleExtension`的一个实例。
        """
        extensions: list[ModuleExtension] = []
        position_map = {}

        # 获取当前类的路径
        current_path = os.path.abspath(cls.__module__.replace(".", os.path.sep) + '.py')
        current_dir_path = os.path.dirname(current_path)

        # 遍历当前目录下的所有子目录
        for subdir_name in os.listdir(current_dir_path):
            if subdir_name.startswith('__'):
                continue

            subdir_path = os.path.join(current_dir_path, subdir_name)
            extension_name = subdir_name
            if os.path.isdir(subdir_path):
                file_names = os.listdir(subdir_path)

                # 判断是否为内置扩展，并读取其位置信息
                builtin = False
                position = None
                if '__builtin__' in file_names:
                    builtin = True

                    builtin_file_path = os.path.join(subdir_path, '__builtin__')
                    if os.path.exists(builtin_file_path):
                        with open(builtin_file_path, encoding='utf-8') as f:
                            position = int(f.read().strip())
                position_map[extension_name] = position

                # 检查是否缺少`.py`文件
                if (extension_name + '.py') not in file_names:
                    logging.warning(f"Missing {extension_name}.py file in {subdir_path}, Skip.")
                    continue

                # 动态加载`.py`文件，并寻找继承自cls的类
                py_path = os.path.join(subdir_path, extension_name + '.py')
                spec = importlib.util.spec_from_file_location(extension_name, py_path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)

                extension_class = None
                for name, obj in vars(mod).items():
                    if isinstance(obj, type) and issubclass(obj, cls) and obj != cls:
                        extension_class = obj
                        break

                # 如果没有找到符合条件的类，则跳过该扩展
                if not extension_class:
                    logging.warning(f"Missing subclass of {cls.__name__} in {py_path}, Skip.")
                    continue

                json_data = {}
                # 非内置扩展必须有一个`schema.json`文件
                if not builtin:
                    if 'schema.json' not in file_names:
                        logging.warning(f"Missing schema.json file in {subdir_path}, Skip.")
                        continue

                    json_path = os.path.join(subdir_path, 'schema.json')
                    json_data = {}
                    if os.path.exists(json_path):
                        with open(json_path, encoding='utf-8') as f:
                            json_data = json.load(f)

                # 将扩展信息添加到列表中
                extensions.append(ModuleExtension(
                    extension_class=extension_class,
                    name=extension_name,
                    label=json_data.get('label'),
                    form_schema=json_data.get('form_schema'),
                    builtin=builtin,
                    position=position
                ))

        # 根据位置信息对扩展进行排序
        sorted_extensions = sort_to_dict_by_position_map(position_map, extensions, lambda x: x.name)

        return sorted_extensions
