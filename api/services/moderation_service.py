from core.moderation.factory import ModerationFactory, ModerationOutputsResult
from extensions.ext_database import db
from models.model import App, AppModelConfig


class ModerationService:
    def moderation_for_outputs(self, app_id: str, app_model: App, text: str) -> ModerationOutputsResult:
        """
        对给定文本进行审核，根据应用模型的配置来执行敏感词过滤或其他审核逻辑。
        
        参数:
        app_id (str): 应用的ID。
        app_model (App): 应用模型实例，包含应用的配置信息。
        text (str): 需要进行审核的文本。
        
        返回:
        ModerationOutputsResult: 审核结果的实例，包含审核过程中产生的所有输出。
        """
        app_model_config: AppModelConfig = None

        app_model_config = (
            db.session.query(AppModelConfig).filter(AppModelConfig.id == app_model.app_model_config_id).first()
        )

        if not app_model_config:
            # 如果找不到应用模型配置，抛出异常
            raise ValueError("app model config not found")

        name = app_model_config.sensitive_word_avoidance_dict["type"]
        config = app_model_config.sensitive_word_avoidance_dict["config"]

        # 根据审核类型和配置创建审核器实例
        moderation = ModerationFactory(name, app_id, app_model.tenant_id, config)
        # 执行审核，并返回审核结果
        return moderation.moderation_for_outputs(text)
