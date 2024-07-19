import logging
import time

import click
from celery import shared_task
from flask import render_template

from configs import dify_config
from extensions.ext_mail import mail


@shared_task(queue='mail')
def send_invite_member_mail_task(language: str, to: str, token: str, inviter_name: str, workspace_name: str):
    """
    异步发送邀请成员的邮件
    :param language: 邮件接收者的语言偏好，用于指定邮件语言版本
    :param to: 邮件接收者的邮箱地址
    :param token: 邮件中的激活链接token，用于激活账户
    :param inviter_name: 邀请者的姓名
    :param workspace_name: 工作空间的名称
    Usage: send_invite_member_mail_task.delay(langauge, to, token, inviter_name, workspace_name)
    """
    # 检查邮件服务是否已初始化
    if not mail.is_inited():
        return

    # 记录开始发送邀请邮件的日志
    logging.info(click.style('Start send invite member mail to {} in workspace {}'.format(to, workspace_name),
                             fg='green'))
    start_at = time.perf_counter()

    # send invite member mail using different languages
    try:
        url = f'{dify_config.CONSOLE_WEB_URL}/activate?token={token}'
        if language == 'zh-Hans':
            # 发送中文版本的邀请邮件
            html_content = render_template('invite_member_mail_template_zh-CN.html',
                                           to=to,
                                           inviter_name=inviter_name,
                                           workspace_name=workspace_name,
                                           url=url)
            mail.send(to=to, subject="立即加入 Dify 工作空间", html=html_content)
        else:
            # 发送英文版本的邀请邮件
            html_content = render_template('invite_member_mail_template_en-US.html',
                                           to=to,
                                           inviter_name=inviter_name,
                                           workspace_name=workspace_name,
                                           url=url)
            mail.send(to=to, subject="Join Dify Workspace Now", html=html_content)

        end_at = time.perf_counter()
        # 记录邀请邮件发送成功及耗时的日志
        logging.info(
            click.style('Send invite member mail to {} succeeded: latency: {}'.format(to, end_at - start_at),
                        fg='green'))
    except Exception:
        # 记录邀请邮件发送失败的日志
        logging.exception("Send invite member mail to {} failed".format(to))