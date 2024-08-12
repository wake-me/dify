
from flask_restful import fields, marshal_with

from configs import dify_config
from controllers.console import api
from controllers.console.app.error import AppUnavailableError
from controllers.console.explore.wraps import InstalledAppResource
from models.model import AppMode, InstalledApp
from services.app_service import AppService


class AppParameterApi(InstalledAppResource):
    """Resource for app variables."""
    # 定义变量字段类型
    variable_fields = {
        'key': fields.String,  # 键名
        'name': fields.String,  # 变量名
        'description': fields.String,  # 描述
        'type': fields.String,  # 类型
        'default': fields.String,  # 默认值
        'max_length': fields.Integer,  # 最大长度
        'options': fields.List(fields.String)  # 可选值列表
    }

    # 定义系统参数字段类型
    system_parameters_fields = {
        'image_file_size_limit': fields.String  # 图片文件大小限制
    }

    # 定义参数字段类型
    parameters_fields = {
        'opening_statement': fields.String,  # 开场白
        'suggested_questions': fields.Raw,  # 建议问题
        'suggested_questions_after_answer': fields.Raw,  # 回答后的建议问题
        'speech_to_text': fields.Raw,  # 语音转文本
        'text_to_speech': fields.Raw,  # 文本转语音
        'retriever_resource': fields.Raw,  # 数据检索资源
        'annotation_reply': fields.Raw,  # 注解回复
        'more_like_this': fields.Raw,  # 类似的回复
        'user_input_form': fields.Raw,  # 用户输入表单
        'sensitive_word_avoidance': fields.Raw,  # 敏感词规避
        'file_upload': fields.Raw,  # 文件上传
        'system_parameters': fields.Nested(system_parameters_fields)  # 系统参数
    }
    
    @marshal_with(parameters_fields)
    def get(self, installed_app: InstalledApp):
        """
        获取应用参数。
        
        :param installed_app: 已安装的应用对象，用于获取应用的详细配置参数。
        :return: 包含应用各种配置参数的字典，如开场白、建议问题等。
        """
        app_model = installed_app.app

        if app_model.mode in [AppMode.ADVANCED_CHAT.value, AppMode.WORKFLOW.value]:
            workflow = app_model.workflow
            if workflow is None:
                raise AppUnavailableError()

            features_dict = workflow.features_dict
            user_input_form = workflow.user_input_form(to_old_structure=True)
        else:
            app_model_config = app_model.app_model_config
            features_dict = app_model_config.to_dict()

            user_input_form = features_dict.get('user_input_form', [])

        # 组装并返回包含各种配置参数的字典
        return {
            'opening_statement': features_dict.get('opening_statement'),
            'suggested_questions': features_dict.get('suggested_questions', []),
            'suggested_questions_after_answer': features_dict.get('suggested_questions_after_answer',
                                                                  {"enabled": False}),
            'speech_to_text': features_dict.get('speech_to_text', {"enabled": False}),
            'text_to_speech': features_dict.get('text_to_speech', {"enabled": False}),
            'retriever_resource': features_dict.get('retriever_resource', {"enabled": False}),
            'annotation_reply': features_dict.get('annotation_reply', {"enabled": False}),
            'more_like_this': features_dict.get('more_like_this', {"enabled": False}),
            'user_input_form': user_input_form,
            'sensitive_word_avoidance': features_dict.get('sensitive_word_avoidance',
                                                          {"enabled": False, "type": "", "configs": []}),
            'file_upload': features_dict.get('file_upload', {"image": {
                                                     "enabled": False,
                                                     "number_limits": 3,
                                                     "detail": "high",
                                                     "transfer_methods": ["remote_url", "local_file"]
                                                 }}),
            'system_parameters': {
                'image_file_size_limit': dify_config.UPLOAD_IMAGE_FILE_SIZE_LIMIT
            }
        }


class ExploreAppMetaApi(InstalledAppResource):
    def get(self, installed_app: InstalledApp):
        """Get app meta"""
        app_model = installed_app.app
        return AppService().get_app_meta(app_model)


api.add_resource(AppParameterApi, '/installed-apps/<uuid:installed_app_id>/parameters',
                 endpoint='installed_app_parameters')
api.add_resource(ExploreAppMetaApi, '/installed-apps/<uuid:installed_app_id>/meta', endpoint='installed_app_meta')
