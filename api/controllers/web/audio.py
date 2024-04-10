import logging

from flask import request
from werkzeug.exceptions import InternalServerError

import services
from controllers.web import api
from controllers.web.error import (
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
from controllers.web.wraps import WebApiResource
from core.errors.error import ModelCurrentlyNotSupportError, ProviderTokenNotInitError, QuotaExceededError
from core.model_runtime.errors.invoke import InvokeError
from models.model import App
from services.audio_service import AudioService
from services.errors.audio import (
    AudioTooLargeServiceError,
    NoAudioUploadedServiceError,
    ProviderNotSupportSpeechToTextServiceError,
    UnsupportedAudioTypeServiceError,
)


class AudioApi(WebApiResource):
    """
    音频API类，提供音频处理相关的接口。

    继承自WebApiResource，提供POST方法用于处理音频转文字的请求。
    """

    def post(self, app_model: App, end_user):
        file = request.files['file']

        try:
            # 调用音频服务进行音频转文字处理
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
            # 处理提供者不支持语音转文字服务错误
            raise ProviderNotSupportSpeechToTextError()
        except ProviderTokenNotInitError as ex:
            # 处理提供者令牌未初始化错误
            raise ProviderNotInitializeError(ex.description)
        except QuotaExceededError:
            # 处理配额超过错误
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
            # 处理其他所有异常，记录日志并抛出内部服务错误
            logging.exception(f"internal server error: {str(e)}")
            raise InternalServerError()


class TextApi(WebApiResource):
    def post(self, app_model: App, end_user):
        try:
            # 调用音频服务进行文本转语音转换
            response = AudioService.transcript_tts(
                app_model=app_model,
                text=request.form['text'],
                end_user=end_user.external_user_id,
                voice=request.form.get('voice'),
                streaming=False
            )

            # 返回转换后的音频数据
            return {'data': response.data.decode('latin1')}
        except services.errors.app_model_config.AppModelConfigBrokenError:
            # 记录应用模型配置错误并抛出
            logging.exception("App model config broken.")
            raise AppUnavailableError()
        except NoAudioUploadedServiceError:
            # 抛出未上传音频错误
            raise NoAudioUploadedError()
        except AudioTooLargeServiceError as e:
            # 抛出音频文件过大错误
            raise AudioTooLargeError(str(e))
        except UnsupportedAudioTypeServiceError:
            # 抛出不支持的音频类型错误
            raise UnsupportedAudioTypeError()
        except ProviderNotSupportSpeechToTextServiceError:
            # 抛出服务提供商不支持文本转语音错误
            raise ProviderNotSupportSpeechToTextError()
        except ProviderTokenNotInitError as ex:
            # 抛出服务提供商令牌未初始化错误
            raise ProviderNotInitializeError(ex.description)
        except QuotaExceededError:
            # 抛出配额超出错误
            raise ProviderQuotaExceededError()
        except ModelCurrentlyNotSupportError:
            # 抛出当前模型不支持错误
            raise ProviderModelCurrentlyNotSupportError()
        except InvokeError as e:
            # 抛出调用错误
            raise CompletionRequestError(e.description)
        except ValueError as e:
            # 抛出值错误
            raise e
        except Exception as e:
            # 记录并抛出内部服务器错误
            logging.exception(f"internal server error: {str(e)}")
            raise InternalServerError()


api.add_resource(AudioApi, '/audio-to-text')
api.add_resource(TextApi, '/text-to-audio')
