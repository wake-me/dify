import json

from flask import current_app
from flask_restful import fields, marshal_with

from controllers.console import api
from controllers.console.explore.wraps import InstalledAppResource
from extensions.ext_database import db
from models.model import AppModelConfig, InstalledApp
from models.tools import ApiToolProvider


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
        app_model_config = app_model.app_model_config

        # 组装并返回包含各种配置参数的字典
        return {
            'opening_statement': app_model_config.opening_statement,  # 开场白
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
                'image_file_size_limit': current_app.config.get('UPLOAD_IMAGE_FILE_SIZE_LIMIT')  # 图片文件大小限制
            }
        }

class ExploreAppMetaApi(InstalledAppResource):
    def get(self, installed_app: InstalledApp):
        """
        获取应用元数据
        参数:
        - installed_app: InstalledApp 类型，表示已安装的应用对象。
        
        返回值:
        - meta: 字典类型，包含应用的工具图标信息。
        """
        # 获取应用的模型配置
        app_model_config: AppModelConfig = installed_app.app.app_model_config

        # 获取代理配置，如果不存在则默认为空字典
        agent_config = app_model_config.agent_mode_dict or {}
        meta = {
            'tool_icons': {}
        }

        # 获取所有工具信息
        tools = agent_config.get('tools', [])
        # 构造工具图标URL的前缀
        url_prefix = (current_app.config.get("CONSOLE_API_URL")
                  + "/console/api/workspaces/current/tool-provider/builtin/")
        for tool in tools:
            keys = list(tool.keys())
            if len(keys) >= 4:
                # 处理当前工具标准
                provider_type = tool.get('provider_type')
                provider_id = tool.get('provider_id')
                tool_name = tool.get('tool_name')
                if provider_type == 'builtin':
                    # 为内建工具添加图标URL
                    meta['tool_icons'][tool_name] = url_prefix + provider_id + '/icon'
                elif provider_type == 'api':
                    try:
                        # 尝试从数据库中查询API工具提供者，并获取图标URL
                        provider: ApiToolProvider = db.session.query(ApiToolProvider).filter(
                            ApiToolProvider.id == provider_id
                        )
                        meta['tool_icons'][tool_name] = json.loads(provider.icon)
                    except:
                        # 如果查询失败，则设置默认图标
                        meta['tool_icons'][tool_name] =  {
                            "background": "#252525",
                            "content": "\ud83d\ude01"
                        }

        return meta

api.add_resource(AppParameterApi, '/installed-apps/<uuid:installed_app_id>/parameters', endpoint='installed_app_parameters')
api.add_resource(ExploreAppMetaApi, '/installed-apps/<uuid:installed_app_id>/meta', endpoint='installed_app_meta')
