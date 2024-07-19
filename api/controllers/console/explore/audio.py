import logging

from flask import request
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
from controllers.console.explore.wraps import InstalledAppResource
from core.errors.error import ModelCurrentlyNotSupportError, ProviderTokenNotInitError, QuotaExceededError
from core.model_runtime.errors.invoke import InvokeError
from models.model import AppMode
from services.audio_service import AudioService
from services.errors.audio import (
    AudioTooLargeServiceError,
    NoAudioUploadedServiceError,
    ProviderNotSupportSpeechToTextServiceError,
    UnsupportedAudioTypeServiceError,
)


class ChatAudioApi(InstalledAppResource):
    """
    处理聊天音频的API接口类。
    
    方法:
    post: 处理上传的音频文件，并将其转录为文本。
    
    参数:
    installed_app: 安装的应用对象，用于获取应用的相关配置和信息。
    
    返回值:
    返回音频转录的响应数据。
    """
    
    def post(self, installed_app):
        # 获取应用模型和配置
        app_model = installed_app.app

        # 获取上传的音频文件
        file = request.files['file']

        try:
            # 调用音频服务进行音频转录
            response = AudioService.transcript_asr(
                app_model=app_model,
                file=file,
                end_user=None
            )

            return response
        except services.errors.app_model_config.AppModelConfigBrokenError:
            # 处理应用模型配置错误
            logging.exception("App model config broken.")
            raise AppUnavailableError()
        except NoAudioUploadedServiceError:
            # 处理未上传音频错误
            raise NoAudioUploadedError()
        except AudioTooLargeServiceError as e:
            # 处理音频文件过大错误
            raise AudioTooLargeError(str(e))
        except UnsupportedAudioTypeServiceError:
            # 处理不支持的音频类型错误
            raise UnsupportedAudioTypeError()
        except ProviderNotSupportSpeechToTextServiceError:
            # 处理服务提供商不支持语音转文本错误
            raise ProviderNotSupportSpeechToTextError()
        except ProviderTokenNotInitError as ex:
            # 处理服务提供商令牌未初始化错误
            raise ProviderNotInitializeError(ex.description)
        except QuotaExceededError:
            # 处理配额超出错误
            raise ProviderQuotaExceededError()
        except ModelCurrentlyNotSupportError:
            # 处理当前模型不支持错误
            raise ProviderModelCurrentlyNotSupportError()
        except InvokeError as e:
            # 处理调用错误
            raise CompletionRequestError(e.description)
        except ValueError as e:
            # 处理值错误，直接抛出
            raise e
        except Exception as e:
            # 处理其他内部服务器错误
            logging.exception("internal server error.")
            raise InternalServerError()


class ChatTextApi(InstalledAppResource):
    """
    处理聊天文本到语音的API请求。

    Attributes:
        installed_app: 安装的应用对象，用于获取应用相关配置和信息。
    """

    def post(self, installed_app):
        from flask_restful import reqparse

        app_model = installed_app.app
        try:
            parser = reqparse.RequestParser()
            parser.add_argument('message_id', type=str, required=False, location='json')
            parser.add_argument('voice', type=str, location='json')
            parser.add_argument('text', type=str, location='json')
            parser.add_argument('streaming', type=bool, location='json')
            args = parser.parse_args()

            message_id = args.get('message_id', None)
            text = args.get('text', None)
            if (app_model.mode in [AppMode.ADVANCED_CHAT.value, AppMode.WORKFLOW.value]
                    and app_model.workflow
                    and app_model.workflow.features_dict):
                text_to_speech = app_model.workflow.features_dict.get('text_to_speech')
                voice = args.get('voice') if args.get('voice') else text_to_speech.get('voice')
            else:
                try:
                    voice = args.get('voice') if args.get('voice') else app_model.app_model_config.text_to_speech_dict.get('voice')
                except Exception:
                    voice = None
            response = AudioService.transcript_tts(
                app_model=app_model,
                message_id=message_id,
                voice=voice,
                text=text
            )
            return response
        except services.errors.app_model_config.AppModelConfigBrokenError:
            # 记录应用模型配置错误
            logging.exception("App model config broken.")
            raise AppUnavailableError()
        except NoAudioUploadedServiceError:
            # 抛出未上传音频的错误
            raise NoAudioUploadedError()
        except AudioTooLargeServiceError as e:
            # 抛出音频文件过大的错误
            raise AudioTooLargeError(str(e))
        except UnsupportedAudioTypeServiceError:
            # 抛出不支持的音频类型的错误
            raise UnsupportedAudioTypeError()
        except ProviderNotSupportSpeechToTextServiceError:
            # 抛出服务提供商不支持文本转语音的错误
            raise ProviderNotSupportSpeechToTextError()
        except ProviderTokenNotInitError as ex:
            # 抛出服务提供商令牌未初始化的错误
            raise ProviderNotInitializeError(ex.description)
        except QuotaExceededError:
            # 抛出配额超过的错误
            raise ProviderQuotaExceededError()
        except ModelCurrentlyNotSupportError:
            # 抛出当前模型不支持的错误
            raise ProviderModelCurrentlyNotSupportError()
        except InvokeError as e:
            # 抛出调用错误
            raise CompletionRequestError(e.description)
        except ValueError as e:
            # 重新抛出值错误
            raise e
        except Exception as e:
            # 记录内部服务器错误
            logging.exception("internal server error.")
            raise InternalServerError()


api.add_resource(ChatAudioApi, '/installed-apps/<uuid:installed_app_id>/audio-to-text', endpoint='installed_app_audio')
api.add_resource(ChatTextApi, '/installed-apps/<uuid:installed_app_id>/text-to-audio', endpoint='installed_app_text')
# api.add_resource(ChatTextApiWithMessageId, '/installed-apps/<uuid:installed_app_id>/text-to-audio/message-id',
#                  endpoint='installed_app_text_with_message_id')
