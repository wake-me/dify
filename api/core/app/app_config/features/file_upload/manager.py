from typing import Optional

from core.app.app_config.entities import FileExtraConfig


class FileUploadConfigManager:
    @classmethod
    def convert(cls, config: dict, is_vision: bool = True) -> Optional[FileExtraConfig]:
        """
        将模型配置转换为特定于文件上传的额外配置。

        :param config: 模型配置参数
        :param is_vision: 如果为True，则表示特性是视觉特性
        :return: 根据配置生成的FileExtraConfig对象，如果没有相应的配置，则返回None
        """
        # 尝试从配置中获取文件上传字典
        file_upload_dict = config.get('file_upload')
        if file_upload_dict:
            # 检查并处理图像配置
            if 'image' in file_upload_dict and file_upload_dict['image']:
                if 'enabled' in file_upload_dict['image'] and file_upload_dict['image']['enabled']:
                    # 构建图像配置字典
                    image_config = {
                        'number_limits': file_upload_dict['image']['number_limits'],
                        'transfer_methods': file_upload_dict['image']['transfer_methods']
                    }

                    # 如果是视觉特性，添加详细配置
                    if is_vision:
                        image_config['detail'] = file_upload_dict['image']['detail']

                    # 返回包含图像配置的FileExtraConfig对象
                    return FileExtraConfig(
                        image_config=image_config
                    )

        # 如果没有符合的配置，返回None
        return None

    @classmethod
    def validate_and_set_defaults(cls, config: dict, is_vision: bool = True) -> tuple[dict, list[str]]:
        """
        验证文件上传配置并设置默认值。

        :param config: 应用模型配置参数
        :param is_vision: 如果为True，则表示特性是视觉特性
        :return: 经过验证和设置默认值后的配置字典，以及一个包含已处理配置项名称的列表
        """
        # 检查并确保file_upload配置存在
        if not config.get("file_upload"):
            config["file_upload"] = {}

        # 确保file_upload配置为字典类型
        if not isinstance(config["file_upload"], dict):
            raise ValueError("file_upload must be of dict type")

        # 初始化或校验image配置
        if not config["file_upload"].get("image"):
            config["file_upload"]["image"] = {"enabled": False}

        # 验证并设置图像配置的启用状态、数量限制、详细程度和传输方法
        if config['file_upload']['image']['enabled']:
            number_limits = config['file_upload']['image']['number_limits']
            # 验证数量限制的范围
            if number_limits < 1 or number_limits > 6:
                raise ValueError("number_limits must be in [1, 6]")
            
            # 如果是视觉特性，验证详细程度配置
            if is_vision:
                detail = config['file_upload']['image']['detail']
                if detail not in ['high', 'low']:
                    raise ValueError("detail must be in ['high', 'low']")

            # 验证传输方法配置
            transfer_methods = config['file_upload']['image']['transfer_methods']
            if not isinstance(transfer_methods, list):
                raise ValueError("transfer_methods must be of list type")
            for method in transfer_methods:
                if method not in ['remote_url', 'local_file']:
                    raise ValueError("transfer_methods must be in ['remote_url', 'local_file']")

        # 返回更新后的配置和处理的配置项列表
        return config, ["file_upload"]