
import json
import logging

import requests
from flask import current_app
from flask_restful import Resource, reqparse

from . import api


class VersionApi(Resource):
    """
    用于检查和获取新版本信息的API类
    
    方法:
    - get: 获取当前版本信息，并检查是否有更新
    """

    def get(self):
        """
        获取当前版本信息，并检查是否有更新
        
        参数:
        - current_version: 当前应用的版本号，字符串类型，必填
        
        返回值:
        - 一个字典，包含以下键:
            - version: 最新版本号
            - release_date: 最新版本的发布日期
            - release_notes: 最新版本的发布说明
            - can_auto_update: 是否支持自动更新
        """
        # 创建请求参数解析器
        parser = reqparse.RequestParser()
        # 添加当前版本号参数
        parser.add_argument('current_version', type=str, required=True, location='args')
        args = parser.parse_args()  # 解析请求参数

        # 从应用配置中获取检查更新的URL
        check_update_url = current_app.config['CHECK_UPDATE_URL']

        # 如果没有提供检查更新的URL，则直接返回当前版本信息及默认值
        if not check_update_url:
            return {
                'version': '0.0.0',
                'release_date': '',
                'release_notes': '',
                'can_auto_update': False
            }

        try:
            # 向指定URL发送请求，查询更新信息
            response = requests.get(check_update_url, {
                'current_version': args.get('current_version')
            })
        except Exception as error:
            # 如果请求失败，记录警告信息，并返回当前版本信息及默认值
            logging.warning("Check update version error: {}.".format(str(error)))
            return {
                'version': args.get('current_version'),
                'release_date': '',
                'release_notes': '',
                'can_auto_update': False
            }

        # 解析响应内容，并返回最新版本的信息
        content = json.loads(response.content)
        return {
            'version': content['version'],
            'release_date': content['releaseDate'],
            'release_notes': content['releaseNotes'],
            'can_auto_update': content['canAutoUpdate']
        }

api.add_resource(VersionApi, '/version')
