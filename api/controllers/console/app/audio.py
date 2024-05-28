import logging

from flask import request
from flask_restful import Resource, reqparse
from werkzeug.exceptions import InternalServerError

import services
from controllers.console import api
from controllers.console.app.error import (
    AppUnavailableError,
    AudioTooLargeError,
    CompletionRequestError,
    NoAudioUploadedError,
    ProviderModelCurrentlyNotSupportError,
    ProviderNotInitializeError,
    ProviderNotSupportSpeechToTextError,
    ProviderQuotaExceededError,
    UnsupportedAudioTypeError,
)
from controllers.console.app.wraps import get_app_model
from controllers.console.setup import setup_required
from controllers.console.wraps import account_initialization_required
from core.errors.error import ModelCurrentlyNotSupportError, ProviderTokenNotInitError, QuotaExceededError
from core.model_runtime.errors.invoke import InvokeError
from libs.login import login_required
from models.model import AppMode
from services.audio_service import AudioService
from services.errors.audio import (
    AudioTooLargeServiceError,
    NoAudioUploadedServiceError,
    ProviderNotSupportSpeechToTextServiceError,
    UnsupportedAudioTypeServiceError,
)


class ChatMessageAudioApi(Resource):
    """
    处理聊天消息音频的API请求。

    Attributes:
        Resource: 继承自Flask RESTful的Resource类，用于创建RESTful API资源。
    """

    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT])
    def post(self, app_model):
        file = request.files['file']

        try:
            # 尝试使用音频转写服务进行转写
            response = AudioService.transcript_asr(
                app_model=app_model,
                file=file,
                end_user=None,
            )
            return response  # 返回转写服务的响应
        except services.errors.app_model_config.AppModelConfigBrokenError:
            logging.exception("App model config broken.")
            raise AppUnavailableError()  # 应用配置错误处理
        except NoAudioUploadedServiceError:
            raise NoAudioUploadedError()  # 未上传音频处理
        except AudioTooLargeServiceError as e:
            raise AudioTooLargeError(str(e))  # 音频过大错误处理
        except UnsupportedAudioTypeServiceError:
            raise UnsupportedAudioTypeError()  # 不支持的音频类型错误处理
        except ProviderNotSupportSpeechToTextServiceError:
            raise ProviderNotSupportSpeechToTextError()  # 服务提供商不支持语音转文本错误处理
        except ProviderTokenNotInitError as ex:
            raise ProviderNotInitializeError(ex.description)  # 服务提供商令牌未初始化错误处理
        except QuotaExceededError:
            raise ProviderQuotaExceededError()  # 配额超出错误处理
        except ModelCurrentlyNotSupportError:
            raise ProviderModelCurrentlyNotSupportError()  # 当前模型不支持错误处理
        except InvokeError as e:
            raise CompletionRequestError(e.description)  # 调用错误处理
        except ValueError as e:
            raise e  # 价值错误直接抛出
        except Exception as e:
            logging.exception(f"internal server error, {str(e)}.")
            raise InternalServerError()  # 其他未知错误处理

class ChatMessageTextApi(Resource):
    """
    处理聊天消息文本转换为音频的API请求。

    Attributes:
        Resource: 继承自Flask RESTful的Resource类，用于创建RESTful API资源。
    """

    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model
    def post(self, app_model):
        try:
            # 调用音频服务，将文本转换为音频
            response = AudioService.transcript_tts(
                app_model=app_model,
                text=request.form['text'],
                voice=request.form['voice'] if request.form.get('voice') else app_model.app_model_config.text_to_speech_dict.get('voice'),
                streaming=False
            )

            # 返回音频数据
            return {'data': response.data.decode('latin1')}
        except services.errors.app_model_config.AppModelConfigBrokenError:
            # 记录应用模型配置错误日志，并抛出应用不可用错误
            logging.exception("App model config broken.")
            raise AppUnavailableError()
        except NoAudioUploadedServiceError:
            # 抛出无音频上传错误
            raise NoAudioUploadedError()
        except AudioTooLargeServiceError as e:
            # 抛出音频过大错误
            raise AudioTooLargeError(str(e))
        except UnsupportedAudioTypeServiceError:
            # 抛出不支持的音频类型错误
            raise UnsupportedAudioTypeError()
        except ProviderNotSupportSpeechToTextServiceError:
            # 抛出提供商不支持语音转文本服务错误
            raise ProviderNotSupportSpeechToTextError()
        except ProviderTokenNotInitError as ex:
            # 抛出提供商令牌未初始化错误
            raise ProviderNotInitializeError(ex.description)
        except QuotaExceededError:
            # 抛出提供商配额超出错误
            raise ProviderQuotaExceededError()
        except ModelCurrentlyNotSupportError:
            # 抛出当前提供商模型不支持错误
            raise ProviderModelCurrentlyNotSupportError()
        except InvokeError as e:
            # 抛出完成请求错误
            raise CompletionRequestError(e.description)
        except ValueError as e:
            # 抛出值错误
            raise e
        except Exception as e:
            # 记录内部服务器错误日志，并抛出内部服务器错误
            logging.exception(f"internal server error, {str(e)}.")
            raise InternalServerError()


class TextModesApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model
    def get(self, app_model):
        try:
            # 解析请求参数
            parser = reqparse.RequestParser()
            parser.add_argument('language', type=str, required=True, location='args')
            args = parser.parse_args()

            # 调用音频服务，获取支持的文本到语音转换语言
            response = AudioService.transcript_tts_voices(
                tenant_id=app_model.tenant_id,
                language=args['language'],
            )

            return response
        except services.errors.audio.ProviderNotSupportTextToSpeechLanageServiceError:
            # 处理文本到语音语言服务不支持的错误
            raise AppUnavailableError("Text to audio voices language parameter loss.")
        except NoAudioUploadedServiceError:
            # 处理未上传音频的错误
            raise NoAudioUploadedError()
        except AudioTooLargeServiceError as e:
            # 处理音频文件过大的错误
            raise AudioTooLargeError(str(e))
        except UnsupportedAudioTypeServiceError:
            # 处理不支持的音频类型的错误
            raise UnsupportedAudioTypeError()
        except ProviderNotSupportSpeechToTextServiceError:
            # 处理语音到文本服务不被支持的错误
            raise ProviderNotSupportSpeechToTextError()
        except ProviderTokenNotInitError as ex:
            # 处理服务提供商令牌未初始化的错误
            raise ProviderNotInitializeError(ex.description)
        except QuotaExceededError:
            # 处理配额超出的错误
            raise ProviderQuotaExceededError()
        except ModelCurrentlyNotSupportError:
            # 处理当前模型不支持的错误
            raise ProviderModelCurrentlyNotSupportError()
        except InvokeError as e:
            # 处理调用错误
            raise CompletionRequestError(e.description)
        except ValueError as e:
            # 处理值错误，直接抛出
            raise e
        except Exception as e:
            # 处理其他所有内部服务器错误
            logging.exception(f"internal server error, {str(e)}.")
            raise InternalServerError()


api.add_resource(ChatMessageAudioApi, '/apps/<uuid:app_id>/audio-to-text')
api.add_resource(ChatMessageTextApi, '/apps/<uuid:app_id>/text-to-audio')
api.add_resource(TextModesApi, '/apps/<uuid:app_id>/text-to-audio/voices')
