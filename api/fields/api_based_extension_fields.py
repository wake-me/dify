from flask_restful import fields

from libs.helper import TimestampField


class HiddenAPIKey(fields.Raw):
    """
    一个用于隐藏API密钥信息的类。
    
    方法:
    - output: 根据API密钥的长度，返回一个隐藏了中间字符的字符串。
    
    参数:
    - key: 字段的键名，此处未使用。
    - obj: 包含API密钥的对象。
    
    返回值:
    - 根据API密钥长度返回适当隐藏后的字符串。
    """
    def output(self, key, obj):
        api_key = obj.api_key
        # 判断API密钥长度并隐藏中间字符
        if len(api_key) <= 8:
            return api_key[0] + "******" + api_key[-1]
        # If the api_key is greater than 8 characters, show the first three and the last three characters
        else:
            return api_key[:3] + "******" + api_key[-3:]

api_based_extension_fields = {
    "id": fields.String,
    "name": fields.String,
    "api_endpoint": fields.String,
    "api_key": HiddenAPIKey,
    "created_at": TimestampField,
}
