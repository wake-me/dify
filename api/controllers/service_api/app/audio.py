import logging

from flask import request
from flask_restful import Resource, reqparse
from werkzeug.exceptions import InternalServerError

import services
from controllers.service_api import api
from controllers.service_api.app.error import (
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
from controllers.service_api.wraps import FetchUserArg, WhereisUserArg, validate_app_token
from core.errors.error import ModelCurrentlyNotSupportError, ProviderTokenNotInitError, QuotaExceededError
from core.model_runtime.errors.invoke import InvokeError
from models.model import App, AppMode, EndUser
from services.audio_service import AudioService
from services.errors.audio import (
    AudioTooLargeServiceError,
    NoAudioUploadedServiceError,
    ProviderNotSupportSpeechToTextServiceError,
    UnsupportedAudioTypeServiceError,
)


class AudioApi(Resource):
    """
    音频API类，用于处理音频相关的API请求。

    Attributes:
        Resource: 继承自Flask-RESTful的Resource类，用于创建RESTful API资源。
    """

    @validate_app_token(fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.FORM))
    def post(self, app_model: App, end_user: EndUser):
        file = request.files['file']

        try:
            # 调用音频转文字服务
            response = AudioService.transcript_asr(
                app_model=app_model,
                file=file,
                end_user=end_user
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
            # 处理音频过大错误
            raise AudioTooLargeError(str(e))
        except UnsupportedAudioTypeServiceError:
            # 处理不支持的音频类型错误
            raise UnsupportedAudioTypeError()
        except ProviderNotSupportSpeechToTextServiceError:
            # 处理服务提供商不支持音频转文字错误
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
            # 直接抛出值错误
            raise e
        except Exception as e:
            # 处理其他所有异常
            logging.exception("internal server error.")
            raise InternalServerError()


class TextApi(Resource):
    """
    处理文本到语音的API请求。

    Parameters:
    - app_model: App 类型，代表应用模型，用于获取应用相关的配置和信息。
    - end_user: EndUser 类型，代表最终用户，用于标识请求的用户。

    Returns:
    - 返回音频服务的响应，具体取决于音频服务的实现。
    """

    @validate_app_token(fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.JSON))
    def post(self, app_model: App, end_user: EndUser):
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
                end_user=end_user.external_user_id,
                voice=voice,
                text=text
            )

            return response
        except services.errors.app_model_config.AppModelConfigBrokenError:
            # 处理应用模型配置错误的情况
            logging.exception("App model config broken.")
            raise AppUnavailableError()
        except NoAudioUploadedServiceError:
            # 处理未上传音频的错误
            raise NoAudioUploadedError()
        except AudioTooLargeServiceError as e:
            # 处理音频过大错误
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
            # 直接抛出值错误
            raise e
        except Exception as e:
            # 处理其他内部服务器错误
            logging.exception("internal server error.")
            raise InternalServerError()


api.add_resource(AudioApi, '/audio-to-text')
api.add_resource(TextApi, '/text-to-audio')
