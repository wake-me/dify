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
from models.model import App, AppModelConfig, EndUser
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
        """
        处理音频转文字的POST请求。

        Args:
            app_model: App模型实例，包含应用的相关配置和信息。
            end_user: EndUser模型实例，代表请求的终端用户。

        Returns:
            返回音频转文字服务的响应结果。

        Raises:
            AppUnavailableError: 如果应用配置禁用了音频转文字功能，则抛出此错误。
            NoAudioUploadedError: 如果没有上传音频文件，则抛出此错误。
            AudioTooLargeError: 如果上传的音频文件过大，则抛出此错误。
            UnsupportedAudioTypeError: 如果上传的音频类型不被支持，则抛出此错误。
            ProviderNotSupportSpeechToTextError: 如果服务提供商不支持音频转文字功能，则抛出此错误。
            ProviderNotInitializeError: 如果服务提供商的令牌未初始化，则抛出此错误。
            ProviderQuotaExceededError: 如果达到服务提供商的配额限制，则抛出此错误。
            ProviderModelCurrentlyNotSupportError: 如果当前服务提供商的模型不支持，则抛出此错误。
            CompletionRequestError: 如果完成请求发生错误，则抛出此错误。
            ValueError: 如果出现值错误，则抛出此错误。
            InternalServerError: 如果发生内部服务器错误，则抛出此错误。
        """
        # 检查音频转文字功能是否启用
        app_model_config: AppModelConfig = app_model.app_model_config
        if not app_model_config.speech_to_text_dict['enabled']:
            raise AppUnavailableError()

        # 获取上传的音频文件
        file = request.files['file']

        try:
            # 调用音频转文字服务
            response = AudioService.transcript_asr(
                tenant_id=app_model.tenant_id,
                file=file,
                end_user=end_user.get_id()
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
        # 初始化请求解析器，用于解析POST请求中的参数
        parser = reqparse.RequestParser()
        parser.add_argument('text', type=str, required=True, nullable=False, location='json')
        parser.add_argument('streaming', type=bool, required=False, nullable=False, location='json')
        args = parser.parse_args()

        try:
            # 调用音频服务进行文本转语音处理
            response = AudioService.transcript_tts(
                tenant_id=app_model.tenant_id,
                text=args['text'],
                end_user=end_user.get_id(),
                voice=app_model.app_model_config.text_to_speech_dict.get('voice'),
                streaming=args['streaming']
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
