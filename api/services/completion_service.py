import json
from collections.abc import Generator
from typing import Any, Union

from sqlalchemy import and_

from core.application_manager import ApplicationManager
from core.entities.application_entities import InvokeFrom
from core.file.message_file_parser import MessageFileParser
from extensions.ext_database import db
from models.model import Account, App, AppModelConfig, Conversation, EndUser, Message
from services.app_model_config_service import AppModelConfigService
from services.errors.app import MoreLikeThisDisabledError
from services.errors.app_model_config import AppModelConfigBrokenError
from services.errors.conversation import ConversationCompletedError, ConversationNotExistsError
from services.errors.message import MessageNotExistsError


class CompletionService:

    @classmethod
    def completion(cls, app_model: App, user: Union[Account, EndUser], args: Any,
                invoke_from: InvokeFrom, streaming: bool = True,
                is_model_config_override: bool = False) -> Union[dict, Generator]:
        """
        完成特定应用模型的会话。

        :param cls: 类名，用于调用类方法和属性。
        :param app_model: 应用模型实例，包含应用的配置和状态信息。
        :param user: 用户实例，可以是账户或终端用户。
        :param args: 包含会话参数的字典，如输入查询、文件等。
        :param invoke_from: 指示调用来源的枚举。
        :param streaming: 是否启用流式处理，默认为True。
        :param is_model_config_override: 是否覆盖模型配置，默认为False。
        :return: 根据请求和配置生成的响应，可以是字典或生成器。
        """
        # 判断是否为流式模式
        inputs = args['inputs']
        query = args['query']
        files = args['files'] if 'files' in args and args['files'] else []
        auto_generate_name = args['auto_generate_name'] \
            if 'auto_generate_name' in args else True

        # 验证应用模式和查询
        if app_model.mode != 'completion':
            if not query:
                raise ValueError('query is required')

            if query:
                if not isinstance(query, str):
                    raise ValueError('query must be a string')

                query = query.replace('\x00', '')

        conversation_id = args['conversation_id'] if 'conversation_id' in args else None

        # 根据会话ID初始化会话对象
        conversation = None
        if conversation_id:
            conversation_filter = [
                Conversation.id == args['conversation_id'],
                Conversation.app_id == app_model.id,
                Conversation.status == 'normal'
            ]

            if isinstance(user, Account):
                conversation_filter.append(Conversation.from_account_id == user.id)
            else:
                conversation_filter.append(Conversation.from_end_user_id == user.id if user else None)

            conversation = db.session.query(Conversation).filter(and_(*conversation_filter)).first()

            if not conversation:
                raise ConversationNotExistsError()

            if conversation.status != 'normal':
                raise ConversationCompletedError()

            # 处理模型配置覆盖
            if not conversation.override_model_configs:
                app_model_config = db.session.query(AppModelConfig).filter(
                    AppModelConfig.id == conversation.app_model_config_id,
                    AppModelConfig.app_id == app_model.id
                ).first()

                if not app_model_config:
                    raise AppModelConfigBrokenError()
            else:
                conversation_override_model_configs = json.loads(conversation.override_model_configs)

                app_model_config = AppModelConfig(
                    id=conversation.app_model_config_id,
                    app_id=app_model.id,
                )

                app_model_config = app_model_config.from_model_config_dict(conversation_override_model_configs)

        else:
            # 无会话ID时，处理默认模型配置
            if app_model.app_model_config_id is None:
                raise AppModelConfigBrokenError()

            app_model_config = app_model.app_model_config

            if not app_model_config:
                raise AppModelConfigBrokenError()

            # 处理模型配置覆盖
            if is_model_config_override:
                if not isinstance(user, Account):
                    raise Exception("Only account can override model config")

                model_config = AppModelConfigService.validate_configuration(
                    tenant_id=app_model.tenant_id,
                    account=user,
                    config=args['model_config'],
                    app_mode=app_model.mode
                )

                app_model_config = AppModelConfig(
                    id=app_model_config.id,
                    app_id=app_model.id,
                )

                app_model_config = app_model_config.from_model_config_dict(model_config)

        # 清理输入，根据模型配置规则
        inputs = cls.get_cleaned_inputs(inputs, app_model_config)

        # 解析文件
        message_file_parser = MessageFileParser(tenant_id=app_model.tenant_id, app_id=app_model.id)
        file_objs = message_file_parser.validate_and_transform_files_arg(
            files,
            app_model_config,
            user
        )

        # 生成并返回响应
        application_manager = ApplicationManager()
        return application_manager.generate(
            tenant_id=app_model.tenant_id,
            app_id=app_model.id,
            app_model_config_id=app_model_config.id,
            app_model_config_dict=app_model_config.to_dict(),
            app_model_config_override=is_model_config_override,
            user=user,
            invoke_from=invoke_from,
            inputs=inputs,
            query=query,
            files=file_objs,
            conversation=conversation,
            stream=streaming,
            extras={
                "auto_generate_conversation_name": auto_generate_name
            }
        )

    @classmethod
    def generate_more_like_this(cls, app_model: App, user: Union[Account, EndUser],
                                message_id: str, invoke_from: InvokeFrom, streaming: bool = True) \
            -> Union[dict, Generator]:
        """
        生成与给定消息更相似的内容。
        
        :param cls: 类的引用，用于调用本静态方法。
        :param app_model: 应用模型实例，指定生成内容所属的应用。
        :param user: 用户账户，可以是终端用户或管理员账户。
        :param message_id: 指定参考的消息ID，用于生成更相似的内容。
        :param invoke_from: 指明调用来源，例如API或控制台。
        :param streaming: 是否启用流式返回结果，默认为True。
        :return: 根据生成内容的类型，可能返回字典或生成器对象。
        
        :raises ValueError: 如果用户参数为空。
        :raises MessageNotExistsError: 如果指定的消息不存在。
        :raises MoreLikeThisDisabledError: 如果应用配置中禁用了“更像此”功能。
        """

        # 校验用户参数，不允许为None
        if not user:
            raise ValueError('user cannot be None')

        # 从数据库查询指定的消息
        message = db.session.query(Message).filter(
            Message.id == message_id,
            Message.app_id == app_model.id,
            Message.from_source == ('api' if isinstance(user, EndUser) else 'console'),
            Message.from_end_user_id == (user.id if isinstance(user, EndUser) else None),
            Message.from_account_id == (user.id if isinstance(user, Account) else None),
        ).first()

        # 如果消息不存在，则抛出异常
        if not message:
            raise MessageNotExistsError()

        # 获取当前应用模型的配置，并校验是否启用了“更像此”功能
        current_app_model_config = app_model.app_model_config
        more_like_this = current_app_model_config.more_like_this_dict

        if not current_app_model_config.more_like_this or more_like_this.get("enabled", False) is False:
            raise MoreLikeThisDisabledError()

        # 更新应用模型的配置，以用于生成更相似的内容
        app_model_config = message.app_model_config
        model_dict = app_model_config.model_dict
        completion_params = model_dict.get('completion_params')
        completion_params['temperature'] = 0.9  # 设置生成内容的随机性参数
        model_dict['completion_params'] = completion_params
        app_model_config.model = json.dumps(model_dict)

        # 解析文件，准备用于生成的文件对象
        message_file_parser = MessageFileParser(tenant_id=app_model.tenant_id, app_id=app_model.id)
        file_objs = message_file_parser.transform_message_files(
            message.files, app_model_config
        )

        # 调用应用管理器，生成更相似的内容
        application_manager = ApplicationManager()
        return application_manager.generate(
            tenant_id=app_model.tenant_id,
            app_id=app_model.id,
            app_model_config_id=app_model_config.id,
            app_model_config_dict=app_model_config.to_dict(),
            app_model_config_override=True,
            user=user,
            invoke_from=invoke_from,
            inputs=message.inputs,
            query=message.query,
            files=file_objs,
            conversation=None,
            stream=streaming,
            extras={
                "auto_generate_conversation_name": False  # 不自动生成会话名称
            }
        )

    @classmethod
    def get_cleaned_inputs(cls, user_inputs: dict, app_model_config: AppModelConfig):
        """
        清洗用户输入的数据。
        
        参数:
        - cls: 类的引用，用于可能的类方法调用，但在此函数中未使用。
        - user_inputs: 字典类型，包含用户提供的原始输入数据。
        - app_model_config: AppModelConfig 类的实例，包含应用模型的配置信息，如用户输入表单的配置。
        
        返回值:
        - 清洗后的用户输入数据字典，确保数据符合要求，不包含无效或非法的输入。
        """
        if user_inputs is None:
            user_inputs = {}

        filtered_inputs = {}

        # 根据表单配置过滤和处理用户输入，处理必填字段、默认值和选项值
        input_form_config = app_model_config.user_input_form_list
        for config in input_form_config:
            input_config = list(config.values())[0]
            variable = input_config["variable"]

            input_type = list(config.keys())[0]

            # 处理用户未提供或为空的输入
            if variable not in user_inputs or not user_inputs[variable]:
                if input_type == "external_data_tool":
                    continue
                if "required" in input_config and input_config["required"]:
                    raise ValueError(f"{variable} is required in input form")
                else:
                    filtered_inputs[variable] = input_config["default"] if "default" in input_config else ""
                    continue

            value = user_inputs[variable]

            # 确保输入值为字符串类型
            if value:
                if not isinstance(value, str):
                    raise ValueError(f"{variable} in input form must be a string")

            # 处理选择类型输入，确保值在选项范围内
            if input_type == "select":
                options = input_config["options"] if "options" in input_config else []
                if value not in options:
                    raise ValueError(f"{variable} in input form must be one of the following: {options}")
            else:
                # 处理其他类型输入，检查字符串最大长度
                if 'max_length' in input_config:
                    max_length = input_config['max_length']
                    if len(value) > max_length:
                        raise ValueError(f'{variable} in input form must be less than {max_length} characters')

            # 移除可能的空字符，并为无值情况设置为 None
            filtered_inputs[variable] = value.replace('\x00', '') if value else None

        return filtered_inputs
