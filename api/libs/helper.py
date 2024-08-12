import json
import logging
import random
import re
import string
import subprocess
import time
import uuid
from collections.abc import Generator
from datetime import datetime
from hashlib import sha256
from typing import Any, Optional, Union
from zoneinfo import available_timezones

from flask import Response, current_app, stream_with_context
from flask_restful import fields

from core.app.features.rate_limiting.rate_limit import RateLimitGenerator
from extensions.ext_redis import redis_client
from models.account import Account


def run(script):
    """
    执行提供的脚本并返回执行状态和输出。
    
    参数:
    - script: 要执行的脚本命令字符串。
    
    返回:
    - 一个元组，包含命令执行的状态码和输出结果。
    """
    return subprocess.getstatusoutput('source /root/.bashrc && ' + script)


class TimestampField(fields.Raw):
    def format(self, value) -> int:
        return int(value.timestamp())


def email(email):
    # Define a regex pattern for email addresses
    pattern = r"^[\w\.!#$%&'*+\-/=?^_`{|}~]+@([\w-]+\.)+[\w-]{2,}$"
    # Check if the email matches the pattern
    if re.match(pattern, email) is not None:
        return email

    error = ('{email} is not a valid email.'
             .format(email=email))
    raise ValueError(error)


def uuid_value(value):
    """
    验证提供的值是否是一个有效的UUID。
    
    参数:
    - value: 待验证的字符串值。
    
    返回:
    - 验证通过的UUID字符串。
    
    异常:
    - ValueError: 如果提供的值不是一个有效的UUID，则抛出。
    """
    if value == '':
        return str(value)

    try:
        uuid_obj = uuid.UUID(value)
        return str(uuid_obj)
    except ValueError:
        error = ('{value} is not a valid uuid.'
                 .format(value=value))
        raise ValueError(error)

def alphanumeric(value: str):
    # check if the value is alphanumeric and underlined
    if re.match(r'^[a-zA-Z0-9_]+$', value):
        return value

    raise ValueError(f'{value} is not a valid alphanumeric value')

def timestamp_value(timestamp):
    """
    验证提供的的时间戳是否为有效的整数。
    
    参数:
    - timestamp: 待验证的时间戳字符串。
    
    返回:
    - 验证通过的时间戳整数。
    
    异常:
    - ValueError: 如果时间戳无效或为负数，则抛出。
    """
    try:
        int_timestamp = int(timestamp)
        if int_timestamp < 0:
            raise ValueError
        return int_timestamp
    except ValueError:
        error = ('{timestamp} is not a valid timestamp.'
                 .format(timestamp=timestamp))
        raise ValueError(error)


class str_len:
    """
    一个限制输入字符串长度的类。
    
    方法:
    - __call__: 对提供的值进行长度检查。
    """
    def __init__(self, max_length, argument='argument'):
        """
        初始化限制长度的类实例。
        
        参数:
        - max_length: 允许的最大字符串长度。
        - argument: 对象的名称，默认为'argument'。
        """
        self.max_length = max_length
        self.argument = argument

    def __call__(self, value):
        """
        检查提供的值是否符合长度限制。
        
        参数:
        - value: 待检查的字符串值。
        
        返回:
        - 符合长度限制的字符串值。
        
        异常:
        - ValueError: 如果字符串长度超过最大允许长度，则抛出。
        """
        length = len(value)
        if length > self.max_length:
            error = ('Invalid {arg}: {val}. {arg} cannot exceed length {length}'
                     .format(arg=self.argument, val=value, length=self.max_length))
            raise ValueError(error)

        return value


class float_range:
    """
    限制输入为指定范围内的浮点数（包含边界）。
    
    参数:
    - low: 浮点数范围的下界。
    - high: 浮点数范围的上界。
    - argument: 输入参数的名称，默认为'argument'。
    """
    def __init__(self, low, high, argument='argument'):
        self.low = low
        self.high = high
        self.argument = argument

    def __call__(self, value):
        # 将输入转换为浮点数，并检查是否在指定范围内
        value = _get_float(value)
        if value < self.low or value > self.high:
            error = ('Invalid {arg}: {val}. {arg} must be within the range {lo} - {hi}'
                     .format(arg=self.argument, val=value, lo=self.low, hi=self.high))
            raise ValueError(error)

        return value


class datetime_string:
    """
    确保输入字符串符合指定的日期时间格式。
    
    参数:
    - format: 日期时间字符串的格式。
    - argument: 输入参数的名称，默认为'argument'。
    """
    def __init__(self, format, argument='argument'):
        self.format = format
        self.argument = argument

    def __call__(self, value):
        # 尝试将输入字符串按指定格式解析
        try:
            datetime.strptime(value, self.format)
        except ValueError:
            error = ('Invalid {arg}: {val}. {arg} must be conform to the format {format}'
                     .format(arg=self.argument, val=value, format=self.format))
            raise ValueError(error)

        return value


def _get_float(value):
    """
    将输入转换为浮点数。
    
    参数:
    - value: 待转换的值。
    
    返回:
    - 转换后的浮点数。
    
    异常:
    - ValueError: 如果无法将输入转换为浮点数。
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError('{} is not a valid float'.format(value))

def timezone(timezone_string):
    """
    验证时区字符串的有效性。
    
    参数:
    - timezone_string: 待验证的时区字符串。
    
    返回:
    - 验证通过的时区字符串。
    
    异常:
    - ValueError: 如果时区字符串无效。
    """
    if timezone_string and timezone_string in available_timezones():
        return timezone_string

    error = ('{timezone_string} is not a valid timezone.'
             .format(timezone_string=timezone_string))
    raise ValueError(error)


def generate_string(n):
    """
    生成指定长度的随机字符串。
    
    参数:
    - n: 字符串的长度。
    
    返回:
    - 生成的随机字符串。
    """
    letters_digits = string.ascii_letters + string.digits
    result = ""
    # 生成指定长度的随机字符串
    for i in range(n):
        result += random.choice(letters_digits)

    return result


def get_remote_ip(request) -> str:
    if request.headers.get('CF-Connecting-IP'):
        return request.headers.get('Cf-Connecting-Ip')
    # 如果Cloudflare的IP不存在，尝试获取X-Forwarded-For头中的IP
    elif request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0]
    # 如果以上都不存在，使用请求的远程地址
    else:
        return request.remote_addr


def generate_text_hash(text: str) -> str:
    """
    生成文本的哈希值。
    
    参数:
    - text: 待哈希的文本。
    
    返回:
    - 哈希后的字符串。
    """
    hash_text = str(text) + 'None'  # 添加固定字符串以确保哈希值的唯一性
    return sha256(hash_text.encode()).hexdigest()


def compact_generate_response(response: Union[dict, RateLimitGenerator]) -> Response:
    if isinstance(response, dict):
        return Response(response=json.dumps(response), status=200, mimetype='application/json')
    else:
        def generate() -> Generator:
            yield from response

        return Response(stream_with_context(generate()), status=200,
                        mimetype='text/event-stream')


class TokenManager:

    @classmethod
    def generate_token(cls, account: Account, token_type: str, additional_data: dict = None) -> str:
        old_token = cls._get_current_token_for_account(account.id, token_type)
        if old_token:
            if isinstance(old_token, bytes):
                old_token = old_token.decode('utf-8')
            cls.revoke_token(old_token, token_type)

        token = str(uuid.uuid4())
        token_data = {
            'account_id': account.id,
            'email': account.email,
            'token_type': token_type
        }
        if additional_data:
            token_data.update(additional_data)

        expiry_hours = current_app.config[f'{token_type.upper()}_TOKEN_EXPIRY_HOURS']
        token_key = cls._get_token_key(token, token_type)
        redis_client.setex(
            token_key,
            expiry_hours * 60 * 60,
            json.dumps(token_data)
        )

        cls._set_current_token_for_account(account.id, token, token_type, expiry_hours)
        return token

    @classmethod
    def _get_token_key(cls, token: str, token_type: str) -> str:
        return f'{token_type}:token:{token}'

    @classmethod
    def revoke_token(cls, token: str, token_type: str):
        token_key = cls._get_token_key(token, token_type)
        redis_client.delete(token_key)

    @classmethod
    def get_token_data(cls, token: str, token_type: str) -> Optional[dict[str, Any]]:
        key = cls._get_token_key(token, token_type)
        token_data_json = redis_client.get(key)
        if token_data_json is None:
            logging.warning(f"{token_type} token {token} not found with key {key}")
            return None
        token_data = json.loads(token_data_json)
        return token_data

    @classmethod
    def _get_current_token_for_account(cls, account_id: str, token_type: str) -> Optional[str]:
        key = cls._get_account_token_key(account_id, token_type)
        current_token = redis_client.get(key)
        return current_token

    @classmethod
    def _set_current_token_for_account(cls, account_id: str, token: str, token_type: str, expiry_hours: int):
        key = cls._get_account_token_key(account_id, token_type)
        redis_client.setex(key, expiry_hours * 60 * 60, token)

    @classmethod
    def _get_account_token_key(cls, account_id: str, token_type: str) -> str:
        return f'{token_type}:account:{account_id}'


class RateLimiter:
    def __init__(self, prefix: str, max_attempts: int, time_window: int):
        self.prefix = prefix
        self.max_attempts = max_attempts
        self.time_window = time_window

    def _get_key(self, email: str) -> str:
        return f"{self.prefix}:{email}"

    def is_rate_limited(self, email: str) -> bool:
        key = self._get_key(email)
        current_time = int(time.time())
        window_start_time = current_time - self.time_window

        redis_client.zremrangebyscore(key, '-inf', window_start_time)
        attempts = redis_client.zcard(key)

        if attempts and int(attempts) >= self.max_attempts:
            return True
        return False

    def increment_rate_limit(self, email: str):
        key = self._get_key(email)
        current_time = int(time.time())

        redis_client.zadd(key, {current_time: current_time})
        redis_client.expire(key, self.time_window * 2)
