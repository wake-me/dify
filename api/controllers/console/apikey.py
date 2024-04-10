import flask_restful
from flask_login import current_user
from flask_restful import Resource, fields, marshal_with
from werkzeug.exceptions import Forbidden

from extensions.ext_database import db
from libs.helper import TimestampField
from libs.login import login_required
from models.dataset import Dataset
from models.model import ApiToken, App

from . import api
from .setup import setup_required
from .wraps import account_initialization_required

# 定义API密钥的字段结构
api_key_fields = {
    'id': fields.String,  # 密钥ID
    'type': fields.String,  # 密钥类型
    'token': fields.String,  # 密钥令牌
    'last_used_at': TimestampField,  # 密钥最后使用时间
    'created_at': TimestampField  # 密钥创建时间
}

# 定义API密钥列表的结构，包含多个密钥项
api_key_list = {
    'data': fields.List(fields.Nested(api_key_fields), attribute="items")  # 密钥列表数据
}


def _get_resource(resource_id, tenant_id, resource_model):
    """
    根据资源ID和租户ID查询指定资源。
    
    :param resource_id: 要查询的资源ID。
    :param tenant_id: 要查询的资源所属的租户ID。
    :param resource_model: 资源的模型类，用于数据库查询。
    :return: 查询到的资源对象。如果指定资源不存在，则抛出404错误。
    """
    # 根据资源ID和租户ID查询资源
    resource = resource_model.query.filter_by(
        id=resource_id, tenant_id=tenant_id
    ).first()

    # 如果查询结果为空，表示资源不存在，抛出404错误
    if resource is None:
        flask_restful.abort(
            404, message=f"{resource_model.__name__} not found.")

    return resource


class BaseApiKeyListResource(Resource):
    """
    基础API密钥列表资源类，用于处理与特定资源相关的API密钥列表的GET和POST请求。
    """

    method_decorators = [account_initialization_required, login_required, setup_required]
    # 请求方法的装饰器列表，用于确保请求的用户已经完成账户初始化、登录和设置。

    resource_type = None
    resource_model = None
    resource_id_field = None
    token_prefix = None
    max_keys = 10
    # 类变量，用于定义资源类型、模型、资源ID字段、密钥前缀和最大密钥数。

    @marshal_with(api_key_list)
    def get(self, resource_id):
        """
        处理获取特定资源的API密钥列表的GET请求。
        
        :param resource_id: 资源的ID，字符串类型。
        :return: 包含API密钥列表的字典。
        """
        resource_id = str(resource_id)  # 确保resource_id为字符串类型
        _get_resource(resource_id, current_user.current_tenant_id,
                      self.resource_model)  # 验证资源是否存在
        keys = db.session.query(ApiToken). \
            filter(ApiToken.type == self.resource_type, getattr(ApiToken, self.resource_id_field) == resource_id). \
            all()  # 查询与指定资源相关联的API密钥
        return {"items": keys}

    @marshal_with(api_key_fields)
    def post(self, resource_id):
        """
        处理创建一个新的API密钥的POST请求。
        
        :param resource_id: 资源的ID，字符串类型。
        :return: 新创建的API密钥对象。
        """
        resource_id = str(resource_id)  # 确保resource_id为字符串类型
        _get_resource(resource_id, current_user.current_tenant_id,
                      self.resource_model)  # 验证资源是否存在

        if not current_user.is_admin_or_owner:
            raise Forbidden()  # 如果用户不是管理员或资源所有者，则抛出Forbidden异常

        # 检查是否已达到可创建的API密钥的最大数量
        current_key_count = db.session.query(ApiToken). \
            filter(ApiToken.type == self.resource_type, getattr(ApiToken, self.resource_id_field) == resource_id). \
            count()
        if current_key_count >= self.max_keys:
            flask_restful.abort(
                400,
                message=f"Cannot create more than {self.max_keys} API keys for this resource type.",
                code='max_keys_exceeded'
            )

        # 创建新的API密钥并添加到数据库
        key = ApiToken.generate_api_key(self.token_prefix, 24)  # 生成API密钥
        api_token = ApiToken()
        setattr(api_token, self.resource_id_field, resource_id)  # 设置资源ID
        api_token.tenant_id = current_user.current_tenant_id  # 设置租户ID
        api_token.token = key  # 设置密钥值
        api_token.type = self.resource_type  # 设置密钥类型
        db.session.add(api_token)  # 将新密钥添加到数据库会话
        db.session.commit()  # 提交数据库更改
        return api_token, 201  # 返回新创建的API密钥对象和状态码201


class BaseApiKeyResource(Resource):
    """
    API密钥资源基类，提供删除API密钥的功能。
    
    属性:
    method_decorators (list): 用于此资源类的方法的装饰器列表，包括账户初始化所需、登录所需和设置所需。
    resource_type (str): 资源类型。
    resource_model (str): 资源模型。
    resource_id_field (str): 资源ID字段。
    """
    
    method_decorators = [account_initialization_required, login_required, setup_required]

    resource_type = None
    resource_model = None
    resource_id_field = None

    def delete(self, resource_id, api_key_id):
        """
        删除指定的API密钥。
        
        参数:
        resource_id: 资源ID，将被转换为字符串。
        api_key_id: API密钥ID，将被转换为字符串。
        
        返回:
        tuple: 包含成功消息和HTTP状态码的元组。
        """
        resource_id = str(resource_id)  # 转换资源ID为字符串
        api_key_id = str(api_key_id)  # 转换API密钥ID为字符串
        _get_resource(resource_id, current_user.current_tenant_id,
                      self.resource_model)  # 获取资源实例

        # 检查当前用户是否有权限删除（必须是管理员或资源所有者）
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        # 查询指定的API密钥
        key = db.session.query(ApiToken). \
            filter(getattr(ApiToken, self.resource_id_field) == resource_id, ApiToken.type == self.resource_type, ApiToken.id == api_key_id). \
            first()

        if key is None:
            flask_restful.abort(404, message='API key not found')  # 如果API密钥不存在，则返回404错误

        # 删除指定的API密钥并提交事务
        db.session.query(ApiToken).filter(ApiToken.id == api_key_id).delete()
        db.session.commit()

        return {'result': 'success'}, 204  # 返回成功消息和204无内容状态码


class AppApiKeyListResource(BaseApiKeyListResource):
    """
    AppApiKeyListResource类，继承自BaseApiKeyListResource，用于处理App的API密钥列表资源。
    
    属性:
    - resource_type: 指定资源类型为'app'。
    - resource_model: 指定使用的模型为App。
    - resource_id_field: 指定资源ID字段为'app_id'。
    - token_prefix: 指定token的前缀为'app-'。
    
    方法:
    - after_request: 请求处理后添加跨域资源共享(CORS)头部信息。
    """
    
    def after_request(self, resp):
        """
        请求处理后的方法，用于添加跨域资源共享(CORS)头部信息到响应中。
        
        参数:
        - resp: 请求处理后的响应对象。
        
        返回:
        - 修改后的响应对象，添加了允许跨域访问的头部信息。
        """
        resp.headers['Access-Control-Allow-Origin'] = '*'  # 允许所有来源进行跨域访问
        resp.headers['Access-Control-Allow-Credentials'] = 'true'  # 允许使用凭证（如cookies）
        return resp

class AppApiKeyResource(BaseApiKeyResource):
    """
    AppApiKeyResource类，继承自BaseApiKeyResource，用于处理APP的API密钥资源。
    
    属性:
    - resource_type: 指定资源类型为'app'。
    - resource_model: 指定资源模型为App，表示操作的数据模型。
    - resource_id_field: 指定资源ID字段为'app_id'，用于标识资源的唯一ID。
    
    方法:
    - after_request: 请求处理后的钩子函数，用于设置跨域请求头。
    """

    def after_request(self, resp):
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Credentials'] = 'true'
        return resp

    resource_type = 'app'
    resource_model = App
    resource_id_field = 'app_id'


class DatasetApiKeyListResource(BaseApiKeyListResource):
    """
    数据集API密钥列表资源类，继承自BaseApiKeyListResource。
    
    方法:
    - after_request: 请求处理后执行的函数，用于设置响应的跨域资源共享（CORS）头。
    
    属性:
    - resource_type: 资源类型，此处为'dataset'。
    - resource_model: 资源模型，指定为Dataset模型。
    - resource_id_field: 资源ID字段，此处为'dataset_id'。
    - token_prefix: 密钥前缀，设置为'ds-'。
    """

    def after_request(self, resp):
        """
        请求处理后执行的函数，用于设置响应的跨域资源共享（CORS）头。
        
        参数:
        - resp: 请求处理后的响应对象。
        
        返回:
        - 修改后的响应对象，设置了允许跨域访问和凭证的响应头。
        """
        resp.headers['Access-Control-Allow-Origin'] = '*'  # 允许所有来源跨域访问
        resp.headers['Access-Control-Allow-Credentials'] = 'true'  # 允许使用凭证（如cookies）
        return resp

    resource_type = 'dataset'  # 指定资源类型为数据集
    resource_model = Dataset  # 指定使用的数据模型为数据集模型
    resource_id_field = 'dataset_id'  # 指定资源ID的字段名为'dataset_id'
    token_prefix = 'ds-'  # 设置密钥前缀为'ds-'


class DatasetApiKeyResource(BaseApiKeyResource):
    """
    数据集API密钥资源类，继承自BaseApiKeyResource。
    
    方法:
    - after_request: 请求处理后执行的函数，用于设置响应的跨域访问头。
    
    属性:
    - resource_type: 资源类型，此处为'dataset'。
    - resource_model: 资源模型，指定为Dataset模型。
    - resource_id_field: 资源ID字段，此处为'dataset_id'。
    """

    def after_request(self, resp):
        """
        请求处理后执行的函数，用于设置响应的跨域访问头。
        
        参数:
        - resp: 请求处理后的响应对象。
        
        返回:
        - 修改后的响应对象，设置了允许跨域访问的头信息。
        """
        resp.headers['Access-Control-Allow-Origin'] = '*'  # 允许所有来源进行跨域访问
        resp.headers['Access-Control-Allow-Credentials'] = 'true'  # 允许使用凭证（如cookies）
        return resp

    resource_type = 'dataset'  # 指定资源类型为数据集
    resource_model = Dataset  # 指定使用的数据模型为Dataset
    resource_id_field = 'dataset_id'  # 指定资源ID的字段名称为dataset_id

api.add_resource(AppApiKeyListResource, '/apps/<uuid:resource_id>/api-keys')
api.add_resource(AppApiKeyResource,
                 '/apps/<uuid:resource_id>/api-keys/<uuid:api_key_id>')
api.add_resource(DatasetApiKeyListResource,
                 '/datasets/<uuid:resource_id>/api-keys')
api.add_resource(DatasetApiKeyResource,
                 '/datasets/<uuid:resource_id>/api-keys/<uuid:api_key_id>')
