import json

from flask import current_app
from flask_restful import fields, marshal_with, Resource

from controllers.service_api import api
from controllers.service_api.wraps import validate_app_token
from extensions.ext_database import db
from models.model import App, AppModelConfig
from models.tools import ApiToolProvider


class AppParameterApi(Resource):
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

    @validate_app_token  # 验证应用令牌
    @marshal_with(parameters_fields)  # 用预定义的字段列表对返回结果进行格式化
    def get(self, app_model: App):
        """
        获取应用参数。
        
        参数:
        - app_model: App 类型，代表一个具体的应用模型实例。
        
        返回值:
        - 一个字典，包含应用的各种配置参数。
        """
        app_model_config = app_model.app_model_config  # 获取应用模型的配置

        return {
            'opening_statement': app_model_config.opening_statement,  # 开场白
            'suggested_questions': app_model_config.suggested_questions_list,  # 建议的问题列表
            'suggested_questions_after_answer': app_model_config.suggested_questions_after_answer_dict,  # 回答后的建议问题字典
            'speech_to_text': app_model_config.speech_to_text_dict,  # 语音转文本配置
            'text_to_speech': app_model_config.text_to_speech_dict,  # 文本转语音配置
            'retriever_resource': app_model_config.retriever_resource_dict,  # 数据检索资源配置
            'annotation_reply': app_model_config.annotation_reply_dict,  # 注解回复配置
            'more_like_this': app_model_config.more_like_this_dict,  # 类似的选项配置
            'user_input_form': app_model_config.user_input_form_list,  # 用户输入表单列表
            'sensitive_word_avoidance': app_model_config.sensitive_word_avoidance_dict,  # 敏感词规避配置
            'file_upload': app_model_config.file_upload_dict,  # 文件上传配置
            'system_parameters': {  # 系统参数
                'image_file_size_limit': current_app.config.get('UPLOAD_IMAGE_FILE_SIZE_LIMIT')  # 图片文件大小限制
            }
        }

class AppMetaApi(Resource):
    @validate_app_token
    def get(self, app_model: App):
        """
        获取应用元数据
        参数:
        - app_model: App 类型，代表一个具体的应用模型实例
        
        返回值:
        - 一个包含应用工具图标的字典
        """
        # 获取应用模型配置
        app_model_config: AppModelConfig = app_model.app_model_config

        # 获取代理模式配置，如果不存在则默认为空字典
        agent_config = app_model_config.agent_mode_dict or {}
        # 初始化元数据，其中 tool_icons 用于存放工具图标信息
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
                # 处理当前格式的工具标准信息
                provider_type = tool.get('provider_type')
                provider_id = tool.get('provider_id')
                tool_name = tool.get('tool_name')
                if provider_type == 'builtin':
                    # 对于内建工具，拼接图标URL
                    meta['tool_icons'][tool_name] = url_prefix + provider_id + '/icon'
                elif provider_type == 'api':
                    try:
                        # 尝试从数据库中查询 API 工具提供者，并获取图标地址
                        provider: ApiToolProvider = db.session.query(ApiToolProvider).filter(
                            ApiToolProvider.id == provider_id
                        )
                        meta['tool_icons'][tool_name] = json.loads(provider.icon)
                    except:
                        # 如果查询失败，设置默认图标
                        meta['tool_icons'][tool_name] =  {
                            "background": "#252525",
                            "content": "\ud83d\ude01"
                        }

        return meta

api.add_resource(AppParameterApi, '/parameters')
api.add_resource(AppMetaApi, '/meta')
