
import re
import uuid
from json import dumps as json_dumps
from json import loads as json_loads
from json.decoder import JSONDecodeError

from requests import get
from yaml import YAMLError, safe_load

from core.tools.entities.common_entities import I18nObject
from core.tools.entities.tool_bundle import ApiToolBundle
from core.tools.entities.tool_entities import ApiProviderSchemaType, ToolParameter
from core.tools.errors import ToolApiSchemaError, ToolNotSupportedError, ToolProviderNotFoundError


class ApiBasedToolSchemaParser:
    @staticmethod
    def parse_openapi_to_tool_bundle(openapi: dict, extra_info: dict = None, warning: dict = None) -> list[ApiToolBundle]:
        warning = warning if warning is not None else {}
        extra_info = extra_info if extra_info is not None else {}

        # 将 OpenAPI 中的描述信息添加到 extra_info 中
        if 'description' in openapi['info']:
            extra_info['description'] = openapi['info']['description']
        else:
            extra_info['description'] = ''

        if len(openapi['servers']) == 0:
            raise ToolProviderNotFoundError('No server found in the openapi yaml.')

        server_url = openapi['servers'][0]['url']

        # 列出所有接口
        interfaces = []
        for path, path_item in openapi['paths'].items():
            methods = ['get', 'post', 'put', 'delete', 'patch', 'head', 'options', 'trace']
            for method in methods:
                if method in path_item:
                    interfaces.append({
                        'path': path,
                        'method': method,
                        'operation': path_item[method],
                    })

        # 获取所有参数
        bundles = []
        for interface in interfaces:
            # 转换参数
            parameters = []
            if 'parameters' in interface['operation']:
                for parameter in interface['operation']['parameters']:
                    tool_parameter = ToolParameter(
                        name=parameter['name'],
                        label=I18nObject(
                            en_US=parameter['name'],
                            zh_Hans=parameter['name']
                        ),
                        human_description=I18nObject(
                            en_US=parameter.get('description', ''),
                            zh_Hans=parameter.get('description', '')
                        ),
                        type=ToolParameter.ToolParameterType.STRING,
                        required=parameter.get('required', False),
                        form=ToolParameter.ToolParameterForm.LLM,
                        llm_description=parameter.get('description'),
                        default=parameter['schema']['default'] if 'schema' in parameter and 'default' in parameter['schema'] else None,
                    )
                
                    # 检查是否有类型信息
                    typ = ApiBasedToolSchemaParser._get_tool_parameter_type(parameter)
                    if typ:
                        tool_parameter.type = typ

                    parameters.append(tool_parameter)
            # 检查是否有请求体
            if 'requestBody' in interface['operation']:
                request_body = interface['operation']['requestBody']
                if 'content' in request_body:
                    for content_type, content in request_body['content'].items():
                        # 如果存在引用，获取引用并覆盖内容
                        if 'schema' not in content:
                            continue

                        if '$ref' in content['schema']:
                            # 获取引用
                            root = openapi
                            reference = content['schema']['$ref'].split('/')[1:]
                            for ref in reference:
                                root = root[ref]
                            # 覆盖内容
                            interface['operation']['requestBody']['content'][content_type]['schema'] = root

                    # 解析请求体参数
                    if 'schema' in interface['operation']['requestBody']['content'][content_type]:
                        body_schema = interface['operation']['requestBody']['content'][content_type]['schema']
                        required = body_schema['required'] if 'required' in body_schema else []
                        properties = body_schema['properties'] if 'properties' in body_schema else {}
                        for name, property in properties.items():
                            tool = ToolParameter(
                                name=name,
                                label=I18nObject(
                                    en_US=name,
                                    zh_Hans=name
                                ),
                                human_description=I18nObject(
                                    en_US=property['description'] if 'description' in property else '',
                                    zh_Hans=property['description'] if 'description' in property else ''
                                ),
                                type=ToolParameter.ToolParameterType.STRING,
                                required=name in required,
                                form=ToolParameter.ToolParameterForm.LLM,
                                llm_description=property['description'] if 'description' in property else '',
                                default=property['default'] if 'default' in property else None,
                            )

                            # 检查是否有类型信息
                            typ = ApiBasedToolSchemaParser._get_tool_parameter_type(property)
                            if typ:
                                tool.type = typ

                            parameters.append(tool)

            # 检查参数是否重复
            parameters_count = {}
            for parameter in parameters:
                if parameter.name not in parameters_count:
                    parameters_count[parameter.name] = 0
                parameters_count[parameter.name] += 1
            for name, count in parameters_count.items():
                if count > 1:
                    warning['duplicated_parameter'] = f'Parameter {name} is duplicated.'

            # 检查是否存在 operationId，如果不存在，则使用 $path_$method 作为 operationId
            if 'operationId' not in interface['operation']:
                # 移除特殊字符，以确保 operationId 是有效的 ^[a-zA-Z0-9_-]{1,64}$
                path = interface['path']
                if interface['path'].startswith('/'):
                    path = interface['path'][1:]
                # 移除特殊字符，以确保 operationId 是有效的 ^[a-zA-Z0-9_-]{1,64}$
                path = re.sub(r'[^a-zA-Z0-9_-]', '', path)
                if not path:
                    path = str(uuid.uuid4())
                    
                interface['operation']['operationId'] = f'{path}_{interface["method"]}'

            bundles.append(ApiToolBundle(
                server_url=server_url + interface['path'],
                method=interface['method'],
                summary=interface['operation']['description'] if 'description' in interface['operation'] else 
                        interface['operation']['summary'] if 'summary' in interface['operation'] else None,
                operation_id=interface['operation']['operationId'],
                parameters=parameters,
                author='',
                icon=None,
                openapi=interface['operation'],
            ))

        return bundles
    
    @staticmethod
    def _get_tool_parameter_type(parameter: dict) -> ToolParameter.ToolParameterType:
        """
        根据给定的参数字典确定工具参数的类型。
        
        参数:
        - parameter: 一个字典，包含关于参数的描述。预期包含键'type'或'schema'，
                    其中'schema'也是一个字典，包含键'type'。
        
        返回值:
        - 返回 ToolParameter.ToolParameterType 中定义的枚举类型，指示参数是数字、布尔值、字符串中的哪一种。
        """
        # 如果 parameter 为空，则初始化为一个空字典
        parameter = parameter or {}
        typ = None
        # 尝试直接从 parameter 获取 'type'，如果不存在则从其 'schema' 字典中获取
        if 'type' in parameter:
            typ = parameter['type']
        elif 'schema' in parameter and 'type' in parameter['schema']:
            typ = parameter['schema']['type']
        
        # 根据 typ 的值返回相应的 ToolParameterType
        if typ == 'integer' or typ == 'number':
            return ToolParameter.ToolParameterType.NUMBER
        elif typ == 'boolean':
            return ToolParameter.ToolParameterType.BOOLEAN
        elif typ == 'string':
            return ToolParameter.ToolParameterType.STRING

    @staticmethod
    def parse_openapi_yaml_to_tool_bundle(yaml: str, extra_info: dict = None, warning: dict = None) -> list[ApiToolBundle]:
        """
        将 OpenAPI YAML 字符串解析为工具捆绑包列表。

        :param yaml: OpenAPI 规范的 YAML 字符串。
        :param extra_info: 附加信息字典，可用于提供额外的上下文信息给解析过程（可选）。
        :param warning: 警告信息字典，用于收集解析过程中遇到的非致命性问题（可选）。
        :return: 解析得到的 ApiBasedToolBundle 对象列表。
        """
        # 如果未提供警告或额外信息，则默认为空字典
        warning = warning if warning is not None else {}
        extra_info = extra_info if extra_info is not None else {}

        # 安全加载 YAML 字符串为字典
        openapi: dict = safe_load(yaml)
        if openapi is None:
            # 如果加载失败，抛出工具 API 架构错误异常
            raise ToolApiSchemaError('Invalid openapi yaml.')
        # 使用解析器将 OpenAPI 字典解析为工具捆绑包列表
        return ApiBasedToolSchemaParser.parse_openapi_to_tool_bundle(openapi, extra_info=extra_info, warning=warning)
    
    @staticmethod
    def parse_swagger_to_openapi(swagger: dict, extra_info: dict = None, warning: dict = None) -> dict:
        """
        将Swagger规范的字典转换为OpenAPI规范的字典。

        :param swagger: 符合Swagger 2.0规范的字典。
        :param extra_info: 用于存储额外信息的字典，可选。
        :param warning: 用于记录警告信息的字典，可选。
        :return: 一个符合OpenAPI 3.0规范的字典。
        """
        # 初始化OpenAPI规范的基础信息
        info = swagger.get('info', {
            'title': 'Swagger',
            'description': 'Swagger',
            'version': '1.0.0'
        })

        servers = swagger.get('servers', [])

        # 检查是否提供了服务器信息
        if len(servers) == 0:
            raise ToolApiSchemaError('No server found in the swagger yaml.')

        # 构建OpenAPI规范的初始结构
        openapi = {
            'openapi': '3.0.0',
            'info': {
                'title': info.get('title', 'Swagger'),
                'description': info.get('description', 'Swagger'),
                'version': info.get('version', '1.0.0')
            },
            'servers': servers,
            'paths': {},
            'components': {
                'schemas': {}
            }
        }

        # 检查和转换路径信息
        if 'paths' not in swagger or len(swagger['paths']) == 0:
            raise ToolApiSchemaError('No paths found in the swagger yaml.')

        # 遍历并转换每个路径和方法
        for path, path_item in swagger['paths'].items():
            openapi['paths'][path] = {}
            for method, operation in path_item.items():
                # 检查operationId是否存在
                if 'operationId' not in operation:
                    raise ToolApiSchemaError(f'No operationId found in operation {method} {path}.')
                
                # 检查摘要或描述是否存在，并记录警告
                if ('summary' not in operation or len(operation['summary']) == 0) and \
                    ('description' not in operation or len(operation['description']) == 0):
                    warning['missing_summary'] = f'No summary or description found in operation {method} {path}.'
                
                # 转换并填充路径信息
                openapi['paths'][path][method] = {
                    'operationId': operation['operationId'],
                    'summary': operation.get('summary', ''),
                    'description': operation.get('description', ''),
                    'parameters': operation.get('parameters', []),
                    'responses': operation.get('responses', {}),
                }

                # 如果存在请求体信息，则添加
                if 'requestBody' in operation:
                    openapi['paths'][path][method]['requestBody'] = operation['requestBody']

        # 转换定义部分
        for name, definition in swagger['definitions'].items():
            openapi['components']['schemas'][name] = definition

        return openapi

    @staticmethod
    def parse_openai_plugin_json_to_tool_bundle(json: str, extra_info: dict = None, warning: dict = None) -> list[ApiToolBundle]:
        """
            解析 OpenAI 插件的 JSON 字符串为工具捆绑包

            :param json: JSON 字符串
            :param extra_info: 额外信息字典，可选，默认为 None
            :param warning: 警告信息字典，可选，默认为 None
            :return: 工具捆绑包列表

            此函数首先尝试从提供的 JSON 字符串中加载 OpenAI 插件信息，验证其 API 类型是否支持，
            然后从指定的 API URL 获取 OpenAPI YAML 文件，并将其解析为工具捆绑包列表。
        """
        # 如果未提供警告信息或额外信息，则初始化为空字典
        warning = warning if warning is not None else {}
        extra_info = extra_info if extra_info is not None else {}

        try:
            openai_plugin = json_loads(json)
            api = openai_plugin['api']
            api_url = api['url']
            api_type = api['type']
        except:
            raise ToolProviderNotFoundError('Invalid openai plugin json.')
        
        if api_type != 'openapi':
            raise ToolNotSupportedError('Only openapi is supported now.')
        
        # 从 API URL 获取 OpenAPI YAML 内容
        response = get(api_url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        }, timeout=5)

        if response.status_code != 200:
            raise ToolProviderNotFoundError('cannot get openapi yaml from url.')
        
        # 解析获取到的 OpenAPI YAML 文本为工具捆绑包列表
        return ApiBasedToolSchemaParser.parse_openapi_yaml_to_tool_bundle(response.text, extra_info=extra_info, warning=warning)
    
    @staticmethod
    def auto_parse_to_tool_bundle(content: str, extra_info: dict = None, warning: dict = None) -> tuple[list[ApiToolBundle], str]:
        """
            auto parse to tool bundle

            :param content: the content
            :return: tools bundle, schema_type
        """
        warning = warning if warning is not None else {}
        extra_info = extra_info if extra_info is not None else {}

        # 去除内容两端的空白字符
        content = content.strip()
        loaded_content = None
        json_error = None
        yaml_error = None
        
        # 尝试解析JSON格式内容
        try:
            loaded_content = json_loads(content)
        except JSONDecodeError as e:
            json_error = e

        # 如果JSON解析失败，尝试解析YAML格式内容
        if loaded_content is None:
            try:
                loaded_content = safe_load(content)
            except YAMLError as e:
                yaml_error = e
        # 如果两种格式都解析失败，抛出错误
        if loaded_content is None:
            raise ToolApiSchemaError(f'Invalid api schema, schema is neither json nor yaml. json error: {str(json_error)}, yaml error: {str(yaml_error)}')

        # 初始化不同API规范解析相关的错误变量和schema类型
        swagger_error = None
        openapi_error = None
        openapi_plugin_error = None
        schema_type = None
        
        # 尝试以OpenAPI规范解析内容
        try:
            openapi = ApiBasedToolSchemaParser.parse_openapi_to_tool_bundle(loaded_content, extra_info=extra_info, warning=warning)
            schema_type = ApiProviderSchemaType.OPENAPI.value
            return openapi, schema_type
        except ToolApiSchemaError as e:
            openapi_error = e
        
        # 如果OpenAPI解析失败，尝试以Swagger规范解析
        try:
            converted_swagger = ApiBasedToolSchemaParser.parse_swagger_to_openapi(loaded_content, extra_info=extra_info, warning=warning)
            schema_type = ApiProviderSchemaType.SWAGGER.value
            return ApiBasedToolSchemaParser.parse_openapi_to_tool_bundle(converted_swagger, extra_info=extra_info, warning=warning), schema_type
        except ToolApiSchemaError as e:
            swagger_error = e
        
        # 如果Swagger解析失败，尝试解析为OpenAPI插件格式
        try:
            openapi_plugin = ApiBasedToolSchemaParser.parse_openai_plugin_json_to_tool_bundle(json_dumps(loaded_content), extra_info=extra_info, warning=warning)
            return openapi_plugin, ApiProviderSchemaType.OPENAI_PLUGIN.value
        except ToolNotSupportedError as e:
            # 如果不是支持的插件格式，记录错误信息
            openapi_plugin_error = e

        # 如果所有解析尝试都失败，抛出解析错误
        raise ToolApiSchemaError(f'Invalid api schema, openapi error: {str(openapi_error)}, swagger error: {str(swagger_error)}, openapi plugin error: {str(openapi_plugin_error)}')
