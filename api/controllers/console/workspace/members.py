from flask import current_app
from flask_login import current_user
from flask_restful import Resource, abort, marshal_with, reqparse

import services
from controllers.console import api
from controllers.console.setup import setup_required
from controllers.console.wraps import account_initialization_required, cloud_edition_billing_resource_check
from extensions.ext_database import db
from fields.member_fields import account_with_role_list_fields
from libs.login import login_required
from models.account import Account, TenantAccountRole
from services.account_service import RegisterService, TenantService
from services.errors.account import AccountAlreadyInTenantError


class MemberListApi(Resource):
    """
    列出当前租户的所有成员。

    无参数要求。
    
    返回值:
        - 'result': 操作结果，固定为'success'。
        - 'accounts': 当前租户的所有成员信息列表。
    """

    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(account_with_role_list_fields)
    def get(self):
        # 从当前用户所属的租户中获取成员列表
        members = TenantService.get_tenant_members(current_user.current_tenant)
        return {'result': 'success', 'accounts': members}, 200

class MemberInviteEmailApi(Resource):
    """通过电子邮件邀请新成员。"""

    @setup_required
    @login_required
    @account_initialization_required
    @cloud_edition_billing_resource_check('members')
    def post(self):
        """
        发送邀请邮件给新成员。
        
        参数:
        - 无（通过JSON请求体传递）
        
        返回值:
        - 成功邀请的成员信息，包括状态（成功或失败）、电子邮件地址、激活链接（如果成功）或错误信息。
        
        错误代码:
        - 'invalid-role': 角色无效。
        """
        
        # 解析请求体中的参数
        parser = reqparse.RequestParser()
        parser.add_argument('emails', type=str, required=True, location='json', action='append')
        parser.add_argument('role', type=str, required=True, default='admin', location='json')
        parser.add_argument('language', type=str, required=False, location='json')
        args = parser.parse_args()

        # 提取邀请信息
        invitee_emails = args['emails']
        invitee_role = args['role']
        interface_language = args['language']
        if not TenantAccountRole.is_non_owner_role(invitee_role):
            return {'code': 'invalid-role', 'message': 'Invalid role'}, 400

        # 获取当前邀请人
        inviter = current_user
        invitation_results = []
        console_web_url = current_app.config.get("CONSOLE_WEB_URL")
        # 遍历被邀请人电子邮件列表，发送邀请
        for invitee_email in invitee_emails:
            try:
                # 邀请新成员
                token = RegisterService.invite_new_member(inviter.current_tenant, invitee_email, interface_language, role=invitee_role, inviter=inviter)
                invitation_results.append({
                    'status': 'success',
                    'email': invitee_email,
                    'url': f'{console_web_url}/activate?email={invitee_email}&token={token}'
                })
            except AccountAlreadyInTenantError:
                # 如果账户已存在于租户中，则不发送邀请，但记录成功状态并提供登录链接
                invitation_results.append({
                    'status': 'success',
                    'email': invitee_email,
                    'url': f'{console_web_url}/signin'
                })
                break  # 无需继续邀请
            except Exception as e:
                # 记录邀请失败信息
                invitation_results.append({
                    'status': 'failed',
                    'email': invitee_email,
                    'message': str(e)
                })

        # 返回邀请结果
        return {
            'result': 'success',
            'invitation_results': invitation_results,
        }, 201


class MemberCancelInviteApi(Resource):
    """通过成员ID取消邀请。"""

    @setup_required
    @login_required
    @account_initialization_required
    def delete(self, member_id):
        """
        取消指定成员的邀请。

        参数:
        - member_id: 要取消邀请的成员ID。

        返回值:
        - 当操作成功时，返回一个包含'success'结果和204状态码的响应；
        - 当操作失败时，根据不同的错误类型返回相应的错误信息和状态码。
        """
        # 从数据库中查询成员信息
        member = db.session.query(Account).filter(Account.id == str(member_id)).first()
        if not member:
            abort(404)  # 成员不存在时，返回404错误

        try:
            # 尝试从当前租户中移除成员
            TenantService.remove_member_from_tenant(current_user.current_tenant, member, current_user)
        except services.errors.account.CannotOperateSelfError as e:
            # 当操作自身时引发的错误
            return {'code': 'cannot-operate-self', 'message': str(e)}, 400
        except services.errors.account.NoPermissionError as e:
            # 当没有权限时引发的错误
            return {'code': 'forbidden', 'message': str(e)}, 403
        except services.errors.account.MemberNotInTenantError as e:
            # 当成员不在租户中时引发的错误
            return {'code': 'member-not-found', 'message': str(e)}, 404
        except Exception as e:
            raise ValueError(str(e))  # 处理未预期的错误

        # 成功移除成员，返回成功信息
        return {'result': 'success'}, 204


class MemberUpdateRoleApi(Resource):
    """用于更新成员角色的API接口类。"""

    @setup_required
    @login_required
    @account_initialization_required
    def put(self, member_id):
        """
        更新指定成员的角色。

        参数:
        - member_id: 要更新角色的成员ID。

        返回值:
        - 当角色有效时，返回更新成功的消息；
        - 当角色无效时，返回错误消息和400状态码；
        - 当成员不存在时，返回404状态码。
        """
        parser = reqparse.RequestParser()
        parser.add_argument('role', type=str, required=True, location='json')
        args = parser.parse_args()
        new_role = args['role']

        if not TenantAccountRole.is_valid_role(new_role):
            return {'code': 'invalid-role', 'message': 'Invalid role'}, 400

        member = db.session.get(Account, str(member_id))
        if not member:
            abort(404)

        try:
            # 尝试更新成员角色
            TenantService.update_member_role(current_user.current_tenant, member, new_role, current_user)
        except Exception as e:
            # 如果遇到异常，抛出价值观错误
            raise ValueError(str(e))

        # TODO: 处理403权限错误的情况

        return {'result': 'success'}


class DatasetOperatorMemberListApi(Resource):
    """List all members of current tenant."""

    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(account_with_role_list_fields)
    def get(self):
        members = TenantService.get_dataset_operator_members(current_user.current_tenant)
        return {'result': 'success', 'accounts': members}, 200


api.add_resource(MemberListApi, '/workspaces/current/members')
api.add_resource(MemberInviteEmailApi, '/workspaces/current/members/invite-email')
api.add_resource(MemberCancelInviteApi, '/workspaces/current/members/<uuid:member_id>')
api.add_resource(MemberUpdateRoleApi, '/workspaces/current/members/<uuid:member_id>/update-role')
api.add_resource(DatasetOperatorMemberListApi, '/workspaces/current/dataset-operators')
