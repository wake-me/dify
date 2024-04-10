import json

from flask import current_app
from flask_restful import fields, marshal_with

from controllers.web import api
from controllers.web.error import AppUnavailableError
from controllers.web.wraps import WebApiResource
from extensions.ext_database import db
from models.model import App, AppModelConfig, AppMode
from models.tools import ApiToolProvider
from services.app_service import AppService


class AppParameterApi(WebApiResource):
    """应用变量资源类。"""

    # 定义应用变量的字段及其类型
    variable_fields = {
        'key': fields.String,
        'name': fields.String,
        'description': fields.String,
        'type': fields.String,
        'default': fields.String,
        'max_length': fields.Integer,
        'options': fields.List(fields.String)
    }

    # 定义系统参数的字段及其类型
    system_parameters_fields = {
        'image_file_size_limit': fields.String
    }

    # 定义全部参数的字段及其类型
    parameters_fields = {
        'opening_statement': fields.String,  # 开场白
        'suggested_questions': fields.Raw,  # 建议问题
        'suggested_questions_after_answer': fields.Raw,  # 答后建议问题
        'speech_to_text': fields.Raw,  # 语音转文本
        'text_to_speech': fields.Raw,  # 文本转语音
        'retriever_resource': fields.Raw,  # 数据检索资源
        'annotation_reply': fields.Raw,  # 注解回复
        'more_like_this': fields.Raw,  # 类似的回答
        'user_input_form': fields.Raw,  # 用户输入表单
        'sensitive_word_avoidance': fields.Raw,  # 敏感词规避
        'file_upload': fields.Raw,  # 文件上传
        'system_parameters': fields.Nested(system_parameters_fields)  # 系统参数
    }

    @marshal_with(parameters_fields)
    def get(self, app_model: App, end_user):
        """Retrieve app parameters."""
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

        # 构建并返回包含应用所有配置参数的字典
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
                'image_file_size_limit': current_app.config.get('UPLOAD_IMAGE_FILE_SIZE_LIMIT')
                # 获取上传图片文件大小限制的系统参数
            }
        }


class AppMeta(WebApiResource):
    def get(self, app_model: App, end_user):
        """Get app meta"""
        return AppService().get_app_meta(app_model)


api.add_resource(AppParameterApi, '/parameters')
api.add_resource(AppMeta, '/meta')