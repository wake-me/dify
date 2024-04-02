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
            # 如果密钥长度小于等于8个字符，显示首尾字符，中间用星号隐藏
            return api_key[0] + '******' + api_key[-1]
        else:
            # 如果密钥长度大于8个字符，显示开头三个和末尾三个字符，中间用星号隐藏
            return api_key[:3] + '******' + api_key[-3:]

api_based_extension_fields = {
    'id': fields.String,  # 扩展的ID
    'name': fields.String,  # 扩展的名称
    'api_endpoint': fields.String,  # API的端点地址
    'api_key': HiddenAPIKey,  # 使用HiddenAPIKey类隐藏API密钥
    'created_at': TimestampField  # 创建时间戳
}