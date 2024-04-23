import base64
import hashlib
import hmac
import logging
import os
import time
from typing import Optional

from flask import current_app

from extensions.ext_storage import storage

# 定义支持的图片扩展名列表，并将其转换为大写形式以方便后续比较
IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'webp', 'gif', 'svg']
IMAGE_EXTENSIONS.extend([ext.upper() for ext in IMAGE_EXTENSIONS])

class UploadFileParser:
    """
    上传文件解析器类，用于处理上传文件的图像数据获取和签名URL的生成与验证。
    """
    
    @classmethod
    def get_image_data(cls, upload_file, force_url: bool = False) -> Optional[str]:
        """
        获取上传文件的图像数据，根据配置和参数决定返回数据的形式（URL或Base64编码的字符串）。

        :param upload_file: 上传的文件对象。
        :param force_url: 是否强制返回URL形式的数据。
        :return: 图像数据的URL或Base64编码字符串，如果不符合条件则返回None。
        """
        # 检查上传文件是否为空
        if not upload_file:
            return None

        # 检查文件扩展名是否支持
        if upload_file.extension not in IMAGE_EXTENSIONS:
            return None

        # 根据配置和参数决定返回数据的形式
        if current_app.config['MULTIMODAL_SEND_IMAGE_FORMAT'] == 'url' or force_url:
            return cls.get_signed_temp_image_url(upload_file.id)
        else:
            try:
                # 尝试从存储中加载图像文件，并进行Base64编码
                data = storage.load(upload_file.key)
            except FileNotFoundError:
                logging.error(f'File not found: {upload_file.key}')
                return None

            encoded_string = base64.b64encode(data).decode('utf-8')
            return f'data:{upload_file.mime_type};base64,{encoded_string}'

    @classmethod
    def get_signed_temp_image_url(cls, upload_file_id) -> str:
        """
        为上传的文件生成带签名的临时URL，用于访问图像预览。

        :param upload_file_id: 上传文件的ID。
        :return: 带签名的临时URL。
        """
        # 获取基础URL并构建图像预览URL
        base_url = current_app.config.get('FILES_URL')
        image_preview_url = f'{base_url}/files/{upload_file_id}/image-preview'

        # 生成签名所需的时间戳、随机数和签名字符串，并进行编码
        timestamp = str(int(time.time()))
        nonce = os.urandom(16).hex()
        data_to_sign = f"image-preview|{upload_file_id}|{timestamp}|{nonce}"
        secret_key = current_app.config['SECRET_KEY'].encode()
        sign = hmac.new(secret_key, data_to_sign.encode(), hashlib.sha256).digest()
        encoded_sign = base64.urlsafe_b64encode(sign).decode()

        # 返回带签名参数的URL
        return f"{image_preview_url}?timestamp={timestamp}&nonce={nonce}&sign={encoded_sign}"

    @classmethod
    def verify_image_file_signature(cls, upload_file_id: str, timestamp: str, nonce: str, sign: str) -> bool:
        """
        验证上传文件图像签名的有效性。

        :param upload_file_id: 文件ID。
        :param timestamp: 时间戳。
        :param nonce: 随机数。
        :param sign: 签名字符串。
        :return: 如果签名有效返回True，否则返回False。
        """
        # 构建用于重新计算签名的数据字符串
        data_to_sign = f"image-preview|{upload_file_id}|{timestamp}|{nonce}"
        secret_key = current_app.config['SECRET_KEY'].encode()
        recalculated_sign = hmac.new(secret_key, data_to_sign.encode(), hashlib.sha256).digest()
        recalculated_encoded_sign = base64.urlsafe_b64encode(recalculated_sign).decode()

        # 验证签名是否匹配并检查时间戳是否过期
        if sign != recalculated_encoded_sign:
            return False

        current_time = int(time.time())
        return current_time - int(timestamp) <= 300  # 判断是否在5分钟有效期内