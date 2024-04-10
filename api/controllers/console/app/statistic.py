from datetime import datetime
from decimal import Decimal

import pytz
from flask import jsonify
from flask_login import current_user
from flask_restful import Resource, reqparse

from controllers.console import api
from controllers.console.app import _get_app
from controllers.console.setup import setup_required
from controllers.console.wraps import account_initialization_required
from extensions.ext_database import db
from libs.helper import datetime_string
from libs.login import login_required


class DailyConversationStatistic(Resource):
    """
    日对话统计资源类，用于处理与应用每日对话统计相关的请求。

    属性:
        Resource: 父类，提供基本的资源处理方法。
    """

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, app_id):
        """
        处理获取指定应用的每日对话统计信息的请求。

        参数:
            app_id (str): 应用的ID。

        返回:
            jsonify: 包含每日对话统计数据的JSON响应。
        """
        # 获取当前登录的用户账户
        account = current_user
        # 将app_id转换为字符串类型
        app_id = str(app_id)
        # 根据app_id获取应用模型
        app_model = _get_app(app_id)

        # 初始化请求参数解析器
        parser = reqparse.RequestParser()
        # 添加开始时间参数
        parser.add_argument('start', type=datetime_string('%Y-%m-%d %H:%M'), location='args')
        # 添加结束时间参数
        parser.add_argument('end', type=datetime_string('%Y-%m-%d %H:%M'), location='args')
        # 解析请求参数
        args = parser.parse_args()

        # 构造SQL查询语句
        sql_query = '''
        SELECT date(DATE_TRUNC('day', created_at AT TIME ZONE 'UTC' AT TIME ZONE :tz )) AS date, count(distinct messages.conversation_id) AS conversation_count
            FROM messages where app_id = :app_id 
        '''
        # 准备SQL查询需要的参数
        arg_dict = {'tz': account.timezone, 'app_id': app_model.id}

        # 获取账户时区和UTC时区对象
        timezone = pytz.timezone(account.timezone)
        utc_timezone = pytz.utc

        # 如果指定了开始时间，则更新SQL查询语句以加入时间范围条件
        if args['start']:
            start_datetime = datetime.strptime(args['start'], '%Y-%m-%d %H:%M')
            start_datetime = start_datetime.replace(second=0)

            start_datetime_timezone = timezone.localize(start_datetime)
            start_datetime_utc = start_datetime_timezone.astimezone(utc_timezone)

            sql_query += ' and created_at >= :start'
            arg_dict['start'] = start_datetime_utc

        # 如果指定了结束时间，则更新SQL查询语句以加入时间范围条件
        if args['end']:
            end_datetime = datetime.strptime(args['end'], '%Y-%m-%d %H:%M')
            end_datetime = end_datetime.replace(second=0)

            end_datetime_timezone = timezone.localize(end_datetime)
            end_datetime_utc = end_datetime_timezone.astimezone(utc_timezone)

            sql_query += ' and created_at < :end'
            arg_dict['end'] = end_datetime_utc

        # 完善SQL查询语句，准备执行
        sql_query += ' GROUP BY date order by date'

        # 初始化响应数据列表
        response_data = []

        # 开始数据库事务
        with db.engine.begin() as conn:
            # 执行SQL查询
            rs = conn.execute(db.text(sql_query), arg_dict)
            # 遍历查询结果，构建响应数据
            for i in rs:
                response_data.append({
                    'date': str(i.date),
                    'conversation_count': i.conversation_count
                })

        # 返回构建好的统计信息JSON响应
        return jsonify({
            'data': response_data
        })


class DailyTerminalsStatistic(Resource):
    """
    日终端统计信息类，提供通过APP ID获取每日终端用户数量的统计信息。

    方法:
    - get: 根据提供的app_id和可选的时间范围，获取每日终端用户数量的统计信息。
    """

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, app_id):
        """
        获取指定APP ID的每日终端用户数量的统计信息。

        参数:
        - app_id: 字符串，指定的应用程序ID。

        返回值:
        - 一个包含每日终端用户数量统计信息的JSON对象。
        """

        # 当前登录的用户
        account = current_user
        app_id = str(app_id)  # 确保app_id为字符串类型
        app_model = _get_app(app_id)  # 获取app模型

        # 解析请求参数
        parser = reqparse.RequestParser()
        parser.add_argument('start', type=datetime_string('%Y-%m-%d %H:%M'), location='args')
        parser.add_argument('end', type=datetime_string('%Y-%m-%d %H:%M'), location='args')
        args = parser.parse_args()

        # 构建SQL查询语句
        sql_query = '''
                SELECT date(DATE_TRUNC('day', created_at AT TIME ZONE 'UTC' AT TIME ZONE :tz )) AS date, count(distinct messages.from_end_user_id) AS terminal_count
                    FROM messages where app_id = :app_id 
                '''
        arg_dict = {'tz': account.timezone, 'app_id': app_model.id}

        # 处理时区
        timezone = pytz.timezone(account.timezone)
        utc_timezone = pytz.utc

        # 如果提供了开始时间，则添加到SQL查询中
        if args['start']:
            start_datetime = datetime.strptime(args['start'], '%Y-%m-%d %H:%M')
            start_datetime = start_datetime.replace(second=0)

            start_datetime_timezone = timezone.localize(start_datetime)
            start_datetime_utc = start_datetime_timezone.astimezone(utc_timezone)

            sql_query += ' and created_at >= :start'
            arg_dict['start'] = start_datetime_utc

        # 如果提供了结束时间，则添加到SQL查询中
        if args['end']:
            end_datetime = datetime.strptime(args['end'], '%Y-%m-%d %H:%M')
            end_datetime = end_datetime.replace(second=0)

            end_datetime_timezone = timezone.localize(end_datetime)
            end_datetime_utc = end_datetime_timezone.astimezone(utc_timezone)

            sql_query += ' and created_at < :end'
            arg_dict['end'] = end_datetime_utc

        sql_query += ' GROUP BY date order by date'

        # 执行查询并构建响应数据
        response_data = []

        with db.engine.begin() as conn:
            rs = conn.execute(db.text(sql_query), arg_dict)            
            for i in rs:
                response_data.append({
                    'date': str(i.date),
                    'terminal_count': i.terminal_count
                })

        # 返回统计信息
        return jsonify({
            'data': response_data
        })


class DailyTokenCostStatistic(Resource):
    """
    日用量统计资源类，用于获取每日令牌消耗量的统计信息。
    
    方法:
    - get: 根据应用ID和时间范围获取每日令牌消耗量及总价格。
    
    参数:
    - app_id: 应用的唯一标识符。
    
    返回值:
    - 一个包含每日统计信息的JSON对象，每个统计信息包括日期、令牌消耗量和总价格。
    """

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, app_id):
        """
        根据应用ID和可选的时间范围获取每日的令牌消耗量和总价格的统计信息。
        
        参数:
        - app_id: 应用的ID。
        
        返回:
        - 包含每日统计信息的JSON响应。
        """
        # 获取当前登录的用户账户
        account = current_user
        app_id = str(app_id)  # 将app_id转换为字符串
        app_model = _get_app(app_id)  # 获取app模型

        # 解析请求参数中的开始和结束时间
        parser = reqparse.RequestParser()
        parser.add_argument('start', type=datetime_string('%Y-%m-%d %H:%M'), location='args')
        parser.add_argument('end', type=datetime_string('%Y-%m-%d %H:%M'), location='args')
        args = parser.parse_args()

        # 构建SQL查询语句
        sql_query = '''
                SELECT date(DATE_TRUNC('day', created_at AT TIME ZONE 'UTC' AT TIME ZONE :tz )) AS date, 
                    (sum(messages.message_tokens) + sum(messages.answer_tokens)) as token_count,
                    sum(total_price) as total_price
                    FROM messages where app_id = :app_id 
                '''
        arg_dict = {'tz': account.timezone, 'app_id': app_model.id}

        # 处理时区转换
        timezone = pytz.timezone(account.timezone)
        utc_timezone = pytz.utc

        # 如果提供了开始时间，添加到SQL查询中
        if args['start']:
            start_datetime = datetime.strptime(args['start'], '%Y-%m-%d %H:%M')
            start_datetime = start_datetime.replace(second=0)

            start_datetime_timezone = timezone.localize(start_datetime)
            start_datetime_utc = start_datetime_timezone.astimezone(utc_timezone)

            sql_query += ' and created_at >= :start'
            arg_dict['start'] = start_datetime_utc

        # 如果提供了结束时间，添加到SQL查询中
        if args['end']:
            end_datetime = datetime.strptime(args['end'], '%Y-%m-%d %H:%M')
            end_datetime = end_datetime.replace(second=0)

            end_datetime_timezone = timezone.localize(end_datetime)
            end_datetime_utc = end_datetime_timezone.astimezone(utc_timezone)

            sql_query += ' and created_at < :end'
            arg_dict['end'] = end_datetime_utc

        sql_query += ' GROUP BY date order by date'

        # 执行查询并将结果格式化为响应数据
        response_data = []

        with db.engine.begin() as conn:
            rs = conn.execute(db.text(sql_query), arg_dict)
            for i in rs:
                response_data.append({
                    'date': str(i.date),
                    'token_count': i.token_count,
                    'total_price': i.total_price,
                    'currency': 'USD'
                })

        # 返回格式化后的统计信息
        return jsonify({
            'data': response_data
        })


class AverageSessionInteractionStatistic(Resource):
    """
    平均会话交互统计类，用于获取指定应用的平均会话交互数据。
    
    方法:
    - get: 根据提供的应用ID和时间范围，获取平均会话交互统计数据。
    
    参数:
    - app_id: 字符串，指定的应用ID。
    
    返回值:
    - 一个包含会话交互统计数据的JSON对象。
    """

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, app_id):
        """
        获取指定应用的平均会话交互统计数据。
        
        参数:
        - app_id: 字符串，指定的应用ID。
        
        返回值:
        - 包含会话交互统计数据的JSON对象。
        """
        # 获取当前登录的用户账户
        account = current_user
        app_id = str(app_id)  # 将app_id转换为字符串
        # 根据app_id获取应用模型
        app_model = _get_app(app_id, 'chat')

        # 初始化请求参数解析器
        parser = reqparse.RequestParser()
        # 添加开始时间和结束时间参数
        parser.add_argument('start', type=datetime_string('%Y-%m-%d %H:%M'), location='args')
        parser.add_argument('end', type=datetime_string('%Y-%m-%d %H:%M'), location='args')
        args = parser.parse_args()  # 解析参数

        # 构建SQL查询语句
        sql_query = """SELECT date(DATE_TRUNC('day', c.created_at AT TIME ZONE 'UTC' AT TIME ZONE :tz )) AS date, 
AVG(subquery.message_count) AS interactions
FROM (SELECT m.conversation_id, COUNT(m.id) AS message_count
    FROM conversations c
    JOIN messages m ON c.id = m.conversation_id
    WHERE c.override_model_configs IS NULL AND c.app_id = :app_id"""
        arg_dict = {'tz': account.timezone, 'app_id': app_model.id}  # 查询参数字典

        # 处理时区转换
        timezone = pytz.timezone(account.timezone)
        utc_timezone = pytz.utc

        # 如果指定了开始时间，则添加到SQL查询中
        if args['start']:
            start_datetime = datetime.strptime(args['start'], '%Y-%m-%d %H:%M')
            start_datetime = start_datetime.replace(second=0)

            start_datetime_timezone = timezone.localize(start_datetime)
            start_datetime_utc = start_datetime_timezone.astimezone(utc_timezone)

            sql_query += ' and c.created_at >= :start'
            arg_dict['start'] = start_datetime_utc

        # 如果指定了结束时间，则添加到SQL查询中
        if args['end']:
            end_datetime = datetime.strptime(args['end'], '%Y-%m-%d %H:%M')
            end_datetime = end_datetime.replace(second=0)

            end_datetime_timezone = timezone.localize(end_datetime)
            end_datetime_utc = end_datetime_timezone.astimezone(utc_timezone)

            sql_query += ' and c.created_at < :end'
            arg_dict['end'] = end_datetime_utc

        # 完善SQL查询语句并准备执行
        sql_query += """
        GROUP BY m.conversation_id) subquery
LEFT JOIN conversations c on c.id=subquery.conversation_id
GROUP BY date
ORDER BY date"""

        response_data = []  # 初始化响应数据列表
        
        # 执行SQL查询并处理结果
        with db.engine.begin() as conn:
            rs = conn.execute(db.text(sql_query), arg_dict)
            for i in rs:
                response_data.append({
                    'date': str(i.date),
                    'interactions': float(i.interactions.quantize(Decimal('0.01')))
                })

        # 返回交互统计数据
        return jsonify({
            'data': response_data
        })


class UserSatisfactionRateStatistic(Resource):
    """
    用户满意度统计资源类，提供获取特定应用的用户满意度统计数据接口。
    
    方法:
    - get: 根据指定的应用ID和时间范围，获取用户消息和反馈的数量，以及计算满意度。
    
    参数:
    - app_id: 字符串，应用的唯一标识符。
    
    返回值:
    - 一个包含满意度统计数据的JSON对象，其中每个条目包含日期、消息数量、反馈数量和满意度。
    """

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, app_id):
        """
        获取特定应用的用户满意度统计数据。
        
        参数:
        - app_id: 应用的ID，字符串类型。
        
        返回:
        - 满意度统计数据的JSON响应。
        """
        # 获取当前登录的用户账户
        account = current_user
        app_id = str(app_id)  # 确保app_id为字符串类型
        app_model = _get_app(app_id)  # 获取应用模型

        # 解析请求参数中的开始和结束时间
        parser = reqparse.RequestParser()
        parser.add_argument('start', type=datetime_string('%Y-%m-%d %H:%M'), location='args')
        parser.add_argument('end', type=datetime_string('%Y-%m-%d %H:%M'), location='args')
        args = parser.parse_args()

        # 构造SQL查询语句
        sql_query = '''
                        SELECT date(DATE_TRUNC('day', m.created_at AT TIME ZONE 'UTC' AT TIME ZONE :tz )) AS date, 
                            COUNT(m.id) as message_count, COUNT(mf.id) as feedback_count 
                            FROM messages m
                            LEFT JOIN message_feedbacks mf on mf.message_id=m.id
                            WHERE m.app_id = :app_id 
                        '''
        arg_dict = {'tz': account.timezone, 'app_id': app_model.id}  # 查询参数

        # 处理时区转换
        timezone = pytz.timezone(account.timezone)
        utc_timezone = pytz.utc

        # 根据请求参数添加时间范围过滤条件
        if args['start']:
            start_datetime = datetime.strptime(args['start'], '%Y-%m-%d %H:%M')
            start_datetime = start_datetime.replace(second=0)

            start_datetime_timezone = timezone.localize(start_datetime)
            start_datetime_utc = start_datetime_timezone.astimezone(utc_timezone)

            sql_query += ' and m.created_at >= :start'
            arg_dict['start'] = start_datetime_utc

        if args['end']:
            end_datetime = datetime.strptime(args['end'], '%Y-%m-%d %H:%M')
            end_datetime = end_datetime.replace(second=0)

            end_datetime_timezone = timezone.localize(end_datetime)
            end_datetime_utc = end_datetime_timezone.astimezone(utc_timezone)

            sql_query += ' and m.created_at < :end'
            arg_dict['end'] = end_datetime_utc

        sql_query += ' GROUP BY date order by date'  # 结束查询语句构建

        response_data = []

        # 执行SQL查询并处理结果
        with db.engine.begin() as conn:
            rs = conn.execute(db.text(sql_query), arg_dict)
            for i in rs:
                response_data.append({
                    'date': str(i.date),
                    'rate': round((i.feedback_count * 1000 / i.message_count) if i.message_count > 0 else 0, 2),
                })

        # 返回满意度统计数据的JSON响应
        return jsonify({
            'data': response_data
        })

class AverageResponseTimeStatistic(Resource):
    """
    平均响应时间统计类，用于提供应用的平均响应时间数据。
    
    方法:
    - get: 根据提供的应用ID和时间范围，获取该应用的平均响应时间统计信息。
    
    参数:
    - app_id: 字符串类型，应用的唯一标识符。
    
    返回值:
    - 返回一个包含平均响应时间数据的JSON对象。
    """

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, app_id):
        """
        获取指定应用的平均响应时间统计数据。
        
        参数:
        - app_id: 字符串类型，指定的应用ID。
        
        返回值:
        - 包含平均响应时间数据的JSON对象。
        """
        # 获取当前登录的用户账户
        account = current_user
        # 将app_id转换为字符串类型
        app_id = str(app_id)
        # 根据app_id获取应用模型
        app_model = _get_app(app_id, 'completion')

        # 初始化请求参数解析器
        parser = reqparse.RequestParser()
        # 添加开始时间参数
        parser.add_argument('start', type=datetime_string('%Y-%m-%d %H:%M'), location='args')
        # 添加结束时间参数
        parser.add_argument('end', type=datetime_string('%Y-%m-%d %H:%M'), location='args')
        # 解析请求参数
        args = parser.parse_args()

        # 构造SQL查询语句
        sql_query = '''
                SELECT date(DATE_TRUNC('day', created_at AT TIME ZONE 'UTC' AT TIME ZONE :tz )) AS date, 
                    AVG(provider_response_latency) as latency
                    FROM messages
                    WHERE app_id = :app_id
                '''
        # 准备SQL查询需要的参数
        arg_dict = {'tz': account.timezone, 'app_id': app_model.id}

        # 获取账户时区和UTC时区对象
        timezone = pytz.timezone(account.timezone)
        utc_timezone = pytz.utc

        # 处理开始时间参数，将其加入到SQL查询条件中
        if args['start']:
            start_datetime = datetime.strptime(args['start'], '%Y-%m-%d %H:%M')
            start_datetime = start_datetime.replace(second=0)

            start_datetime_timezone = timezone.localize(start_datetime)
            start_datetime_utc = start_datetime_timezone.astimezone(utc_timezone)

            sql_query += ' and created_at >= :start'
            arg_dict['start'] = start_datetime_utc

        # 处理结束时间参数，将其加入到SQL查询条件中
        if args['end']:
            end_datetime = datetime.strptime(args['end'], '%Y-%m-%d %H:%M')
            end_datetime = end_datetime.replace(second=0)

            end_datetime_timezone = timezone.localize(end_datetime)
            end_datetime_utc = end_datetime_timezone.astimezone(utc_timezone)

            sql_query += ' and created_at < :end'
            arg_dict['end'] = end_datetime_utc

        # 完善SQL查询语句，准备执行
        sql_query += ' GROUP BY date order by date'

        # 初始化存储查询结果的列表
        response_data = []

        # 开始数据库事务
        with db.engine.begin() as conn:
            # 执行SQL查询
            rs = conn.execute(db.text(sql_query), arg_dict)            
            # 遍历查询结果，构造响应数据
            for i in rs:
                response_data.append({
                    'date': str(i.date),
                    'latency': round(i.latency * 1000, 4)
                })

        # 返回构造好的平均响应时间数据
        return jsonify({
            'data': response_data
        })


class TokensPerSecondStatistic(Resource):
    """
    用于获取每秒令牌数统计信息的类。
    
    要求登录、账户初始化且需要设置好应用ID。
    
    参数:
    - app_id: 应用的唯一标识符。
    
    返回值:
    - 包含每秒令牌数统计数据的JSON对象。
    """

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, app_id):
        """
        处理GET请求，获取指定应用的每秒令牌数统计信息。
        
        参数:
        - app_id: 字符串类型，指定应用的ID。
        
        返回:
        - 包含统计结果的JSON响应。
        """
        # 获取当前登录的用户账户
        account = current_user
        app_id = str(app_id)  # 确保app_id为字符串类型
        app_model = _get_app(app_id)  # 获取应用模型

        # 解析请求参数：开始时间和结束时间
        parser = reqparse.RequestParser()
        parser.add_argument('start', type=datetime_string('%Y-%m-%d %H:%M'), location='args')
        parser.add_argument('end', type=datetime_string('%Y-%m-%d %H:%M'), location='args')
        args = parser.parse_args()

        # 构造SQL查询语句，用于统计每秒令牌数
        sql_query = '''SELECT date(DATE_TRUNC('day', created_at AT TIME ZONE 'UTC' AT TIME ZONE :tz )) AS date, 
    CASE 
        WHEN SUM(provider_response_latency) = 0 THEN 0
        ELSE (SUM(answer_tokens) / SUM(provider_response_latency))
    END as tokens_per_second
FROM messages
WHERE app_id = :app_id'''
        arg_dict = {'tz': account.timezone, 'app_id': app_model.id}

        # 处理时区转换
        timezone = pytz.timezone(account.timezone)
        utc_timezone = pytz.utc

        # 如果指定了开始时间，则添加到SQL查询条件中
        if args['start']:
            start_datetime = datetime.strptime(args['start'], '%Y-%m-%d %H:%M')
            start_datetime = start_datetime.replace(second=0)

            start_datetime_timezone = timezone.localize(start_datetime)
            start_datetime_utc = start_datetime_timezone.astimezone(utc_timezone)

            sql_query += ' and created_at >= :start'
            arg_dict['start'] = start_datetime_utc

        # 如果指定了结束时间，则添加到SQL查询条件中
        if args['end']:
            end_datetime = datetime.strptime(args['end'], '%Y-%m-%d %H:%M')
            end_datetime = end_datetime.replace(second=0)

            end_datetime_timezone = timezone.localize(end_datetime)
            end_datetime_utc = end_datetime_timezone.astimezone(utc_timezone)

            sql_query += ' and created_at < :end'
            arg_dict['end'] = end_datetime_utc

        # 执行SQL查询并构造响应数据
        response_data = []

        with db.engine.begin() as conn:
            rs = conn.execute(db.text(sql_query), arg_dict)
            for i in rs:
                response_data.append({
                    'date': str(i.date),
                    'tps': round(i.tokens_per_second, 4)
                })

        # 返回统计结果的JSON响应
        return jsonify({
            'data': response_data
        })

api.add_resource(DailyConversationStatistic, '/apps/<uuid:app_id>/statistics/daily-conversations')
api.add_resource(DailyTerminalsStatistic, '/apps/<uuid:app_id>/statistics/daily-end-users')
api.add_resource(DailyTokenCostStatistic, '/apps/<uuid:app_id>/statistics/token-costs')
api.add_resource(AverageSessionInteractionStatistic, '/apps/<uuid:app_id>/statistics/average-session-interactions')
api.add_resource(UserSatisfactionRateStatistic, '/apps/<uuid:app_id>/statistics/user-satisfaction-rate')
api.add_resource(AverageResponseTimeStatistic, '/apps/<uuid:app_id>/statistics/average-response-time')
api.add_resource(TokensPerSecondStatistic, '/apps/<uuid:app_id>/statistics/tokens-per-second')
