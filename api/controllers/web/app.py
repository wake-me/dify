import json

from flask import current_app
from flask_restful import fields, marshal_with

from controllers.web import api
from controllers.web.wraps import WebApiResource
from extensions.ext_database import db
from models.model import App, AppModelConfig
from models.tools import ApiToolProvider


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
        """
        获取应用参数。

        :param app_model: 应用模型，用于获取应用配置信息。
        :param end_user: 终端用户，此处未使用，但保留以便于扩展。
        :return: 包含应用所有配置参数的字典。
        """
        # 从应用模型中获取应用配置信息
        app_model_config = app_model.app_model_config

        # 构建并返回包含应用所有配置参数的字典
        return {
            'opening_statement': app_model_config.opening_statement,  # 开场白配置
            'suggested_questions': app_model_config.suggested_questions_list,  # 建议问题列表
            'suggested_questions_after_answer': app_model_config.suggested_questions_after_answer_dict,  # 回答后的建议问题字典
            'speech_to_text': app_model_config.speech_to_text_dict,  # 语音转文本配置
            'text_to_speech': app_model_config.text_to_speech_dict,  # 文本转语音配置
            'retriever_resource': app_model_config.retriever_resource_dict,  # 数据检索资源配置
            'annotation_reply': app_model_config.annotation_reply_dict,  # 注解回复配置
            'more_like_this': app_model_config.more_like_this_dict,  # 类似内容推荐配置
            'user_input_form': app_model_config.user_input_form_list,  # 用户输入表单配置
            'sensitive_word_avoidance': app_model_config.sensitive_word_avoidance_dict,  # 敏感词规避配置
            'file_upload': app_model_config.file_upload_dict,  # 文件上传配置
            'system_parameters': {  # 系统参数
                'image_file_size_limit': current_app.config.get('UPLOAD_IMAGE_FILE_SIZE_LIMIT')
                # 获取上传图片文件大小限制的系统参数
            }
        }

class AppMeta(WebApiResource):
    def get(self, app_model: App, end_user):
        """
        获取应用元数据
        :param app_model: App模型实例，用于获取应用的配置信息
        :param end_user: 终端用户，此处未使用，但可能用于未来扩展以提供用户定制的元数据
        :return: 包含工具图标信息的字典
        """
        # 获取应用的模型配置
        app_model_config: AppModelConfig = app_model.app_model_config

        # 获取代理模式的配置，如果不存在则默认为空字典
        agent_config = app_model_config.agent_mode_dict or {}
        meta = {
            'tool_icons': {}
        }

        # 获取所有工具配置
        tools = agent_config.get('tools', [])
        # 构造工具图标URL的前缀
        url_prefix = (current_app.config.get("CONSOLE_API_URL")
                      + "/console/api/workspaces/current/tool-provider/builtin/")
        for tool in tools:
            keys = list(tool.keys())
            if len(keys) >= 4:
                # 处理当前格式的工具配置
                provider_type = tool.get('provider_type')
                provider_id = tool.get('provider_id')
                tool_name = tool.get('tool_name')
                if provider_type == 'builtin':
                    # 为内置工具构建图标URL
                    meta['tool_icons'][tool_name] = url_prefix + provider_id + '/icon'
                elif provider_type == 'api':
                    try:
                        # 从数据库查询API工具提供者，并尝试获取图标URL
                        provider: ApiToolProvider = db.session.query(ApiToolProvider).filter(
                            ApiToolProvider.id == provider_id
                        )
                        meta['tool_icons'][tool_name] = json.loads(provider.icon)
                    except:
                        # 如果查询失败，则为工具设置默认图标
                        meta['tool_icons'][tool_name] =  {
                            "background": "#252525",
                            "content": "\ud83d\ude01"
                        }

        return meta

api.add_resource(AppParameterApi, '/parameters')
api.add_resource(AppMeta, '/meta')