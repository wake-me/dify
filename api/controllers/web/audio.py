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
from models.model import App, AppModelConfig
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
        """
        处理音频转文字的请求。

        :param app_model: 应用模型，包含应用的相关配置和数据。
        :param end_user: 终端用户信息。
        :return: 返回音频转文字服务的响应结果。
        :raises AppUnavailableError: 如果应用未启用或配置不正确，则抛出应用不可用错误。
        :raises NoAudioUploadedError: 如果没有上传音频，则抛出未上传音频错误。
        :raises AudioTooLargeError: 如果上传的音频文件过大，则抛出音频过大错误。
        :raises UnsupportedAudioTypeError: 如果上传的音频类型不受支持，则抛出不支持的音频类型错误。
        :raises ProviderNotSupportSpeechToTextError: 如果服务提供商不支持语音转文字功能，则抛出提供者不支持错误。
        :raises ProviderNotInitializeError: 如果服务提供商未初始化，则抛出提供者未初始化错误。
        :raises ProviderQuotaExceededError: 如果服务提供商的配额超过限制，则抛出配额超过错误。
        :raises ProviderModelCurrentlyNotSupportError: 如果当前服务提供商的模型不支持，则抛出模型不支持错误。
        :raises CompletionRequestError: 如果完成请求发生错误，则抛出完成请求错误。
        :raises ValueError: 如果出现值错误，则抛出该错误。
        :raises InternalServerError: 如果内部服务发生错误，则抛出内部服务错误。
        """
        # 获取应用模型配置
        app_model_config: AppModelConfig = app_model.app_model_config

        # 检查是否启用了语音到文本的转换
        if not app_model_config.speech_to_text_dict['enabled']:
            raise AppUnavailableError()

        # 获取上传的音频文件
        file = request.files['file']

        try:
            # 调用音频服务进行音频转文字处理
            response = AudioService.transcript_asr(
                tenant_id=app_model.tenant_id,
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
        """
        处理文本转语音的请求。

        参数:
        app_model: App - 应用模型实例，用于获取应用的配置和租户信息。
        end_user: 用户信息，包含外部用户ID，用于指定请求的终端用户。

        返回值:
        一个包含音频数据的字典，音频数据以latin1编码。

        抛出:
        AppUnavailableError: 如果应用配置禁用了文本转语音功能，则抛出此错误。
        NoAudioUploadedError: 如果没有上传音频时抛出此错误。
        AudioTooLargeError: 如果音频文件过大则抛出此错误。
        UnsupportedAudioTypeError: 如果上传了不支持的音频类型则抛出此错误。
        ProviderNotSupportSpeechToTextError: 如果服务提供商不支持文本转语音功能则抛出此错误。
        ProviderNotInitializeError: 如果服务提供商未初始化则抛出此错误。
        ProviderQuotaExceededError: 如果达到服务提供商的配额限制则抛出此错误。
        ProviderModelCurrentlyNotSupportError: 如果当前服务提供商模型不支持则抛出此错误。
        CompletionRequestError: 如果完成请求发生错误则抛出此错误。
        ValueError: 如果出现值错误则抛出。
        InternalServerError: 如果发生内部服务器错误则抛出。
        """

        # 获取应用的模型配置
        app_model_config: AppModelConfig = app_model.app_model_config

        # 检查是否启用了文本转语音功能
        if not app_model_config.text_to_speech_dict['enabled']:
            raise AppUnavailableError()

        try:
            # 调用音频服务进行文本转语音转换
            response = AudioService.transcript_tts(
                tenant_id=app_model.tenant_id,
                text=request.form['text'],
                end_user=end_user.external_user_id,
                voice=request.form['voice'] if request.form['voice'] else app_model.app_model_config.text_to_speech_dict.get('voice'),
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
