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
    "id": fields.String,
    "type": fields.String,
    "token": fields.String,
    "last_used_at": TimestampField,
    "created_at": TimestampField,
}

api_key_list = {"data": fields.List(fields.Nested(api_key_fields), attribute="items")}


def _get_resource(resource_id, tenant_id, resource_model):
    resource = resource_model.query.filter_by(id=resource_id, tenant_id=tenant_id).first()

    # 如果查询结果为空，表示资源不存在，抛出404错误
    if resource is None:
        flask_restful.abort(404, message=f"{resource_model.__name__} not found.")

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
        resource_id = str(resource_id)
        _get_resource(resource_id, current_user.current_tenant_id, self.resource_model)
        keys = (
            db.session.query(ApiToken)
            .filter(ApiToken.type == self.resource_type, getattr(ApiToken, self.resource_id_field) == resource_id)
            .all()
        )
        return {"items": keys}

    @marshal_with(api_key_fields)
    def post(self, resource_id):
        resource_id = str(resource_id)
        _get_resource(resource_id, current_user.current_tenant_id, self.resource_model)
        if not current_user.is_admin_or_owner:
            raise Forbidden()  # 如果用户不是管理员或资源所有者，则抛出Forbidden异常

        current_key_count = (
            db.session.query(ApiToken)
            .filter(ApiToken.type == self.resource_type, getattr(ApiToken, self.resource_id_field) == resource_id)
            .count()
        )

        if current_key_count >= self.max_keys:
            flask_restful.abort(
                400,
                message=f"Cannot create more than {self.max_keys} API keys for this resource type.",
                code="max_keys_exceeded",
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
        resource_id = str(resource_id)
        api_key_id = str(api_key_id)
        _get_resource(resource_id, current_user.current_tenant_id, self.resource_model)

        # 检查当前用户是否有权限删除（必须是管理员或资源所有者）
        if not current_user.is_admin_or_owner:
            raise Forbidden()

        key = (
            db.session.query(ApiToken)
            .filter(
                getattr(ApiToken, self.resource_id_field) == resource_id,
                ApiToken.type == self.resource_type,
                ApiToken.id == api_key_id,
            )
            .first()
        )

        if key is None:
            flask_restful.abort(404, message="API key not found")

        # 删除指定的API密钥并提交事务
        db.session.query(ApiToken).filter(ApiToken.id == api_key_id).delete()
        db.session.commit()

        return {"result": "success"}, 204


class AppApiKeyListResource(BaseApiKeyListResource):
    def after_request(self, resp):
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Credentials"] = "true"
        return resp

    resource_type = "app"
    resource_model = App
    resource_id_field = "app_id"
    token_prefix = "app-"


class AppApiKeyResource(BaseApiKeyResource):
    def after_request(self, resp):
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Credentials"] = "true"
        return resp

    resource_type = "app"
    resource_model = App
    resource_id_field = "app_id"


class DatasetApiKeyListResource(BaseApiKeyListResource):
    def after_request(self, resp):
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Credentials"] = "true"
        return resp

    resource_type = "dataset"
    resource_model = Dataset
    resource_id_field = "dataset_id"
    token_prefix = "ds-"


class DatasetApiKeyResource(BaseApiKeyResource):
    def after_request(self, resp):
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Credentials"] = "true"
        return resp

    resource_type = "dataset"
    resource_model = Dataset
    resource_id_field = "dataset_id"

    resource_type = 'dataset'  # 指定资源类型为数据集
    resource_model = Dataset  # 指定使用的数据模型为Dataset
    resource_id_field = 'dataset_id'  # 指定资源ID的字段名称为dataset_id

api.add_resource(AppApiKeyListResource, "/apps/<uuid:resource_id>/api-keys")
api.add_resource(AppApiKeyResource, "/apps/<uuid:resource_id>/api-keys/<uuid:api_key_id>")
api.add_resource(DatasetApiKeyListResource, "/datasets/<uuid:resource_id>/api-keys")
api.add_resource(DatasetApiKeyResource, "/datasets/<uuid:resource_id>/api-keys/<uuid:api_key_id>")
