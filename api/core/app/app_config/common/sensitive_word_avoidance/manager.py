from typing import Optional

from core.app.app_config.entities import SensitiveWordAvoidanceEntity
from core.moderation.factory import ModerationFactory


class SensitiveWordAvoidanceConfigManager:
    """
    敏感词规避配置管理器类，用于处理敏感词规避相关的配置管理任务。
    """

    @classmethod
    def convert(cls, config: dict) -> Optional[SensitiveWordAvoidanceEntity]:
        """
        将配置字典转换为敏感词规避实体对象。

        :param config: 包含敏感词规避配置的字典。
        :return: 如果配置启用且有效，则返回敏感词规避实体对象；否则返回None。
        """
        # 尝试获取敏感词规避配置
        sensitive_word_avoidance_dict = config.get('sensitive_word_avoidance')
        if not sensitive_word_avoidance_dict:
            return None

        # 检查是否启用了敏感词规避，并构造相应实体对象
        if 'enabled' in sensitive_word_avoidance_dict and sensitive_word_avoidance_dict['enabled']:
            return SensitiveWordAvoidanceEntity(
                type=sensitive_word_avoidance_dict.get('type'),
                config=sensitive_word_avoidance_dict.get('config'),
            )
        else:
            return None

    @classmethod
    def validate_and_set_defaults(cls, tenant_id, config: dict, only_structure_validate: bool = False) \
            -> tuple[dict, list[str]]:
        """
        验证并设置敏感词规避配置的默认值。

        :param tenant_id: 租户ID，用于验证配置时的上下文标识。
        :param config: 待验证和设置默认值的配置字典。
        :param only_structure_validate: 是否仅进行结构验证，不校验具体配置内容。
        :return: 一个元组，包含校验并更新后的配置字典和一个影响范围列表。
        """
        # 如果配置中没有敏感词规避部分，则初始化为禁用状态
        if not config.get("sensitive_word_avoidance"):
            config["sensitive_word_avoidance"] = {
                "enabled": False
            }

        # 确保敏感词规避配置是字典类型
        if not isinstance(config["sensitive_word_avoidance"], dict):
            raise ValueError("sensitive_word_avoidance must be of dict type")

        # 如果未明确启用敏感词规避，则设置为禁用
        if "enabled" not in config["sensitive_word_avoidance"] or not config["sensitive_word_avoidance"]["enabled"]:
            config["sensitive_word_avoidance"]["enabled"] = False

        # 如果启用了敏感词规避，则进行进一步的验证和设置
        if config["sensitive_word_avoidance"]["enabled"]:
            # 必须指定规避类型
            if not config["sensitive_word_avoidance"].get("type"):
                raise ValueError("sensitive_word_avoidance.type is required")

            # 如果不仅进行结构验证，则对配置内容进行校验
            if not only_structure_validate:
                typ = config["sensitive_word_avoidance"]["type"]
                sensitive_word_avoidance_config = config["sensitive_word_avoidance"]["config"]

                ModerationFactory.validate_config(
                    name=typ,
                    tenant_id=tenant_id,
                    config=sensitive_word_avoidance_config
                )

        return config, ["sensitive_word_avoidance"]
