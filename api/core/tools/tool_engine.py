from copy import deepcopy
from datetime import datetime, timezone
from mimetypes import guess_type
from typing import Union

from yarl import URL

from core.app.entities.app_invoke_entities import InvokeFrom
from core.callback_handler.agent_tool_callback_handler import DifyAgentCallbackHandler
from core.callback_handler.workflow_tool_callback_handler import DifyWorkflowCallbackHandler
from core.file.file_obj import FileTransferMethod
from core.tools.entities.tool_entities import ToolInvokeMessage, ToolInvokeMessageBinary, ToolInvokeMeta, ToolParameter
from core.tools.errors import (
    ToolEngineInvokeError,
    ToolInvokeError,
    ToolNotFoundError,
    ToolNotSupportedError,
    ToolParameterValidationError,
    ToolProviderCredentialValidationError,
    ToolProviderNotFoundError,
)
from core.tools.tool.tool import Tool
from core.tools.tool.workflow_tool import WorkflowTool
from core.tools.utils.message_transformer import ToolFileMessageTransformer
from extensions.ext_database import db
from models.model import Message, MessageFile


class ToolEngine:
    """
    Tool runtime engine take care of the tool executions.
    """
    @staticmethod
    def agent_invoke(tool: Tool, tool_parameters: Union[str, dict],
                     user_id: str, tenant_id: str, message: Message, invoke_from: InvokeFrom,
                     agent_tool_callback: DifyAgentCallbackHandler) \
                        -> tuple[str, list[tuple[MessageFile, bool]], ToolInvokeMeta]:
        """
        代理调用工具，依据给定参数执行。

        此方法负责根据提供的参数和回调处理器调用工具，并处理工具响应，
        包括提取二进制数据并转换为适合消息传递的形式。

        参数:
        - tool: 被调用工具的Tool对象实例。
        - tool_parameters: 工具调用参数，可以是字符串或字典形式。
        - user_id: 发起工具调用的用户唯一标识。
        - tenant_id: 用户所属租户的唯一标识。
        - message: 表示初始调用消息的Message对象。
        - invoke_from: InvokeFrom枚举值，指示调用来源。
        - agent_tool_callback: DifyAgentCallbackHandler对象，用于工具调用过程中的回调事件。

        返回:
        一个元组，包含工具的纯文本响应，消息文件列表（如有），以及工具调用元数据。
        """
    
        # 若参数为字符串且工具仅接受单个参数，则转换为字典
        if isinstance(tool_parameters, str):
            # check if this tool has only one parameter
            parameters = [
                parameter for parameter in tool.get_runtime_parameters() 
                if parameter.form == ToolParameter.ToolParameterForm.LLM
            ]
            if parameters and len(parameters) == 1:
                tool_parameters = {
                    parameters[0].name: tool_parameters
                }
            else:
                raise ValueError(f"tool_parameters should be a dict, but got a string: {tool_parameters}")

        # invoke the tool
        try:
            # 通知回调处理器，工具调用开始
            agent_tool_callback.on_tool_start(
                tool_name=tool.identity.name, 
                tool_inputs=tool_parameters
            )

            # 根据给定参数和用户ID调用工具
            meta, response = ToolEngine._invoke(tool, tool_parameters, user_id)
            # 转换工具响应消息，使其适应消息系统
            response = ToolFileMessageTransformer.transform_tool_invoke_messages(
                messages=response, 
                user_id=user_id, 
                tenant_id=tenant_id, 
                conversation_id=message.conversation_id
            )

            # 从工具响应中提取二进制数据以便单独处理
            binary_files = ToolEngine._extract_tool_response_binary(response)
            # 根据提取的二进制数据创建MessageFile对象
            message_files = ToolEngine._create_message_files(
                tool_messages=binary_files,
                agent_message=message,
                invoke_from=invoke_from,
                user_id=user_id
            )

            # 将工具响应转换为纯文本，便于消息发送
            plain_text = ToolEngine._convert_tool_response_to_str(response)

            # 通知回调处理器，工具调用结束
            agent_tool_callback.on_tool_end(
                tool_name=tool.identity.name, 
                tool_inputs=tool_parameters, 
                tool_outputs=plain_text
            )

            # 返回纯文本响应、消息文件列表及元数据
            return plain_text, message_files, meta
        except ToolProviderCredentialValidationError as e:
            error_response = "Please check your tool provider credentials"
            agent_tool_callback.on_tool_error(e)
        except (
            ToolNotFoundError, ToolNotSupportedError, ToolProviderNotFoundError
        ) as e:
            error_response = f"there is not a tool named {tool.identity.name}"
            agent_tool_callback.on_tool_error(e)
        except (
            ToolParameterValidationError
        ) as e:
            error_response = f"tool parameters validation error: {e}, please check your tool parameters"
            agent_tool_callback.on_tool_error(e)
        except ToolInvokeError as e:
            error_response = f"tool invoke error: {e}"
            agent_tool_callback.on_tool_error(e)
        except ToolEngineInvokeError as e:
            meta = e.args[0]
            error_response = f"tool invoke error: {meta.error}"
            agent_tool_callback.on_tool_error(e)
            return error_response, [], meta
        except Exception as e:
            error_response = f"unknown error: {e}"
            agent_tool_callback.on_tool_error(e)
        
        # 返回标准化错误响应，伴随空消息文件列表及错误元数据
        return error_response, [], ToolInvokeMeta.error_instance(error_response)

    @staticmethod
    def workflow_invoke(tool: Tool, tool_parameters: dict,
                        user_id: str, workflow_id: str, 
                        workflow_tool_callback: DifyWorkflowCallbackHandler,
                        workflow_call_depth: int) \
                              -> list[ToolInvokeMessage]:
        """
        根据给定的参数，在工作流中调用工具。

        此函数触发工作流中指定工具的执行，传递给定的参数，并在工具执行的各个阶段（开始、结束、错误）
        通知工作流回调处理器。

        参数:
        - tool: 作为工作流一部分被调用的工具对象。
        - tool_parameters: 调用工具时传递的参数字典。
        - user_id: 启动工作流的用户标识符。
        - workflow_id: 工作流中工具被调用时的唯一标识符。
        - workflow_tool_callback: Dify工作流回调处理器的实例，用于在工具执行的不同阶段回调（开始、结束、错误）。

        返回:
        代表已调用工具响应的工具调用消息对象列表。
        """
        try:
            # 通知回调处理器工具执行即将开始。
            workflow_tool_callback.on_tool_start(
                tool_name=tool.identity.name, 
                tool_inputs=tool_parameters
            )

            if isinstance(tool, WorkflowTool):
                tool.workflow_call_depth = workflow_call_depth + 1

            response = tool.invoke(user_id, tool_parameters)

            # 通知回调处理器工具执行已结束，并传递工具的响应。
            workflow_tool_callback.on_tool_end(
                tool_name=tool.identity.name, 
                tool_inputs=tool_parameters, 
                tool_outputs=response
            )

            return response
        except Exception as e:
            workflow_tool_callback.on_tool_error(e)
            raise e
        
    @staticmethod
    def _invoke(tool: Tool, tool_parameters: dict, user_id: str) \
        -> tuple[ToolInvokeMeta, list[ToolInvokeMessage]]:
        """
        根据给定的参数和用户上下文调用工具。
        
        此函数尝试使用提供的参数和用户标识来执行给定的工具，
        捕获执行元数据并返回工具响应或引发错误。
        
        参数:
        - tool: 被调用的Tool对象。该对象需包含用于构建元数据的'identity'属性
            以及用于执行的'invoke'方法。
        - tool_parameters: 工具执行所需的参数字典。
        - user_id: 发起工具调用的用户的字符串标识符。
        
        返回:
        - 一个包含ToolInvokeMeta对象和ToolInvokeMessage对象列表的元组。Meta对象提供了
        执行时间成本和错误信息等元数据，而消息列表包含了工具执行期间产生的所有消息。
        
        抛出:
        - ToolEngineInvokeError: 如果工具调用过程中发生错误，将抛出ToolEngineInvokeError，
                                其中包含已填充的ToolInvokeMeta对象以供调试和调用者处理。
        """
        # 初始化元数据，记录开始时间及工具的基本识别信息。
        started_at = datetime.now(timezone.utc)
        meta = ToolInvokeMeta(time_cost=0.0, error=None, tool_config={
            'tool_name': tool.identity.name,
            'tool_provider': tool.identity.provider,
            'tool_provider_type': tool.tool_provider_type().value,
            'tool_parameters': deepcopy(tool.runtime.runtime_parameters),
            'tool_icon': tool.identity.icon
        })
        
        try:
            # 尝试使用给定参数和用户ID调用工具。
            response = tool.invoke(user_id, tool_parameters)
        except Exception as e:
            # 如执行工具时出现异常，捕获错误信息并抛出自定义错误。
            meta.error = str(e)
            raise ToolEngineInvokeError(meta)
        finally:
            # 不论成功或失败，计算并更新调用的总耗时。
            ended_at = datetime.now(timezone.utc)
            meta.time_cost = (ended_at - started_at).total_seconds()

        # 返回工具的元数据和响应。
        return meta, response
    
    @staticmethod
    def _convert_tool_response_to_str(tool_response: list[ToolInvokeMessage]) -> str:
        """
        将工具响应列表转换为字符串格式。
        
        参数:
        - tool_response: 工具响应列表，列表中的每个元素都是 ToolInvokeMessage 类型。
        
        返回值:
        - result: 转换后的字符串，包含工具响应的消息文本、链接或图片信息。
        """
        result = ''  # 初始化结果字符串
        
        # 遍历工具响应列表，根据不同的消息类型处理响应信息
        for response in tool_response:
            if response.type == ToolInvokeMessage.MessageType.TEXT:
                result += response.message  # 文本消息直接追加到结果字符串
            elif response.type == ToolInvokeMessage.MessageType.LINK:
                # 链接消息追加到结果字符串，并提示用户检查链接
                result += f"result link: {response.message}. please tell user to check it."
            elif response.type == ToolInvokeMessage.MessageType.IMAGE_LINK or \
                response.type == ToolInvokeMessage.MessageType.IMAGE:
                # 图片消息追加提示信息，告知图片已发送给用户
                result += "image has been created and sent to user already, you do not need to create it, just tell the user to check it now."
            else:
                # 对于其他类型的响应消息，简单处理并追加到结果字符串
                result += f"tool response: {response.message}."

        return result  # 返回处理后的结果字符串
        
    @staticmethod
    def _extract_tool_response_binary(tool_response: list[ToolInvokeMessage]) -> list[ToolInvokeMessageBinary]:
        """
        从工具调用响应列表中提取二进制数据响应。

        此函数遍历提供的响应列表中的每一项，并将类型为 IMAGE_LINK、IMAGE、BLOB 或 LINK（含 mime 类型）的响应
        转换为 ToolInvokeMessageBinary 实例。它优先处理带有明确 mime 类型的消息，如果未指定，则默认使用 'octet/stream'。

        参数:
        - tool_response (list[ToolInvokeMessage]): 包含各个消息及其元数据的工具调用响应列表。

        返回:
        - list[ToolInvokeMessageBinary]: 从输入工具响应中提取的二进制消息对象列表。每个二进制对象包含 mime 类型、
        二进制内容的链接以及一个指示是否应保存内容的标志。
        """
        result = []

        for response in tool_response:
            # 处理图片链接和图片类型响应
            if response.type == ToolInvokeMessage.MessageType.IMAGE_LINK or \
                response.type == ToolInvokeMessage.MessageType.IMAGE:
                mimetype = None
                if response.meta.get('mime_type'):
                    mimetype = response.meta.get('mime_type')
                else:
                    try:
                        url = URL(response.message)
                        extension = url.suffix
                        guess_type_result, _ = guess_type(f'a{extension}')
                        if guess_type_result:
                            mimetype = guess_type_result
                    except Exception:
                        pass
                
                if not mimetype:
                    mimetype = 'image/jpeg'
                    
                result.append(ToolInvokeMessageBinary(
                    mimetype=response.meta.get('mime_type', 'image/jpeg'),
                    url=response.message,
                    save_as=response.save_as,
                ))
            # 处理二进制数据（BLOB）类型响应
            elif response.type == ToolInvokeMessage.MessageType.BLOB:
                result.append(ToolInvokeMessageBinary(
                    mimetype=response.meta.get('mime_type', 'octet/stream'),
                    url=response.message,
                    save_as=response.save_as,
                ))
            # 处理普通链接类型响应，仅当存在 mime 类型时才包含
            elif response.type == ToolInvokeMessage.MessageType.LINK:
                # check if there is a mime type in meta
                if response.meta and 'mime_type' in response.meta:
                    result.append(ToolInvokeMessageBinary(
                        mimetype=response.meta.get('mime_type', 'octet/stream') if response.meta else 'octet/stream',
                        url=response.message,
                        save_as=response.save_as,
                    ))

        return result
    
    @staticmethod
    def _create_message_files(
        tool_messages: list[ToolInvokeMessageBinary],
        agent_message: Message,
        invoke_from: InvokeFrom,
        user_id: str
    ) -> list[tuple[MessageFile, bool]]:
        """
        创建消息文件。

        :param tool_messages: 由ToolInvokeMessageBinary类型的元素组成的列表，表示工具消息。
        :param agent_message: Message类型，表示代理消息。
        :param invoke_from: InvokeFrom枚举类型，表示消息调用来源。
        :param user_id: 字符串，表示用户的ID。
        :return: 由MessageFile类型和布尔值组成的元组列表，列表中的每个元素表示一个消息文件及其是否应保存为变量。
        """
        result = []

        # 遍历tool_messages，为每条消息创建一个MessageFile实例
        for message in tool_messages:
            # 根据消息的mimetype确定文件类型
            file_type = 'bin'
            if 'image' in message.mimetype:
                file_type = 'image'
            elif 'video' in message.mimetype:
                file_type = 'video'
            elif 'audio' in message.mimetype:
                file_type = 'audio'
            elif 'text' in message.mimetype:
                file_type = 'text'
            elif 'pdf' in message.mimetype:
                file_type = 'pdf'
            elif 'zip' in message.mimetype:
                file_type = 'archive'
            # ...

            # 创建MessageFile实例，并根据消息来源和用户ID等信息进行配置
            message_file = MessageFile(
                message_id=agent_message.id,
                type=file_type,
                transfer_method=FileTransferMethod.TOOL_FILE.value,
                belongs_to='assistant',
                url=message.url,
                upload_file_id=None,
                created_by_role=('account'if invoke_from in [InvokeFrom.EXPLORE, InvokeFrom.DEBUGGER] else 'end_user'),
                created_by=user_id,
            )

            # 将message_file实例添加到数据库并提交更改
            db.session.add(message_file)
            db.session.commit()
            db.session.refresh(message_file)

            # 将创建的message_file及其save_as标志添加到结果列表中
            result.append((
                message_file,
                message.save_as
            ))

        # 关闭数据库会话
        db.session.close()

        return result