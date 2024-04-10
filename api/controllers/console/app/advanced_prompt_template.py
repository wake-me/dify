from flask_restful import Resource, reqparse

from controllers.console import api
from controllers.console.setup import setup_required
from controllers.console.wraps import account_initialization_required
from libs.login import login_required
from services.advanced_prompt_template_service import AdvancedPromptTemplateService


class AdvancedPromptTemplateList(Resource):
    """
    高级提示模板列表资源类，用于处理与高级提示模板相关的RESTful请求。
    """
    
    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        """
        处理获取高级提示模板的请求。
        
        参数:
        - app_mode: 应用模式，字符串类型，必需。
        - model_mode: 模型模式，字符串类型，必需。
        - has_context: 是否有上下文，字符串类型，非必需，默认为'true'。
        - model_name: 模型名称，字符串类型，必需。
        
        返回值:
        - 返回高级提示模板服务根据提供的参数获取的提示模板。
        """
         
        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('app_mode', type=str, required=True, location='args')
        parser.add_argument('model_mode', type=str, required=True, location='args')
        parser.add_argument('has_context', type=str, required=False, default='true', location='args')
        parser.add_argument('model_name', type=str, required=True, location='args')
        args = parser.parse_args()

        # 调用服务层获取提示模板
        return AdvancedPromptTemplateService.get_prompt(args)

api.add_resource(AdvancedPromptTemplateList, '/app/prompt-templates')