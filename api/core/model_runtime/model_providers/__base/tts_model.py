import logging
import re
from abc import abstractmethod
from typing import Optional

from pydantic import ConfigDict

from core.model_runtime.entities.model_entities import ModelPropertyKey, ModelType
from core.model_runtime.model_providers.__base.ai_model import AIModel

logger = logging.getLogger(__name__)


class TTSModel(AIModel):
    """
    TTS模型类，用于语音合成模型的管理。
    """

    model_type: ModelType = ModelType.TTS  # 指定模型类型为TTS

    # pydantic configs
    model_config = ConfigDict(protected_namespaces=())

    def invoke(self, model: str, tenant_id: str, credentials: dict, content_text: str, voice: str,
               user: Optional[str] = None):
        """
        调用大型语言模型进行语音合成。

        :param model: 模型名称。
        :param tenant_id: 用户租户ID。
        :param credentials: 模型认证信息。
        :param content_text: 需要被转换为语音的文本内容。
        :param voice: 模型的音色。
        :param streaming: 输出是否为流式。
        :param user: 唯一用户ID，可选。
        :return: 转换后的音频文件。
        """
        try:
            return self._invoke(model=model, credentials=credentials, user=user,
                                content_text=content_text, voice=voice, tenant_id=tenant_id)
        except Exception as e:
            # 转换调用过程中的错误为统一的异常格式并抛出
            raise self._transform_invoke_error(e)

    @abstractmethod
    def _invoke(self, model: str, tenant_id: str, credentials: dict, content_text: str, voice: str,
                user: Optional[str] = None):
        """
        实际调用大型语言模型进行语音合成的抽象方法。

        :param model: 模型名称。
        :param tenant_id: 用户租户ID。
        :param credentials: 模型认证信息。
        :param voice: 模型的音色。
        :param content_text: 需要被转换为语音的文本内容。
        :param streaming: 输出是否为流式。
        :param user: 唯一用户ID，可选。
        :return: 转换后的音频文件。
        """
        raise NotImplementedError  # 该方法需要在子类中实现
    def get_tts_model_voices(self, model: str, credentials: dict, language: Optional[str] = None) -> list:
        """
        获取指定TTS模型的声音列表

        :param language: TTS语言
        :param model: 模型名称
        :param credentials: 模型凭证
        :return: 声音列表
        """
        # 获取模型架构
        model_schema = self.get_model_schema(model, credentials)

        # 检查模型架构是否存在，并且包含声音属性
        if model_schema and ModelPropertyKey.VOICES in model_schema.model_properties:
            voices = model_schema.model_properties[ModelPropertyKey.VOICES]
            # 如果指定了语言，则筛选出对应语言的声音列表；否则返回所有声音列表
            if language:
                return [{'name': d['name'], 'value': d['mode']} for d in voices if
                        language and language in d.get('language')]
            else:
                return [{'name': d['name'], 'value': d['mode']} for d in voices]

    def _get_model_default_voice(self, model: str, credentials: dict) -> any:
        """
        获取指定TTS模型的默认声音

        :param model: 模型名称
        :param credentials: 模型凭证
        :return: 返回指定模型的默认声音
        """
        # 获取模型的架构
        model_schema = self.get_model_schema(model, credentials)

        # 检查模型架构是否存在，并且包含默认声音属性
        if model_schema and ModelPropertyKey.DEFAULT_VOICE in model_schema.model_properties:
            return model_schema.model_properties[ModelPropertyKey.DEFAULT_VOICE]

    def _get_model_audio_type(self, model: str, credentials: dict) -> str:
        """
        获取给定TTS模型的音频类型

        :param model: 模型名称
        :param credentials: 模型凭证
        :return: 音频类型（voice）
        """
        # 根据模型名称和凭证获取模型架构
        model_schema = self.get_model_schema(model, credentials)

        # 检查模型架构是否存在，并且包含音频类型的属性
        if model_schema and ModelPropertyKey.AUDIO_TYPE in model_schema.model_properties:
            return model_schema.model_properties[ModelPropertyKey.AUDIO_TYPE]

    def _get_model_word_limit(self, model: str, credentials: dict) -> int:
        """
        获取给定TTS模型的单词限制
        :param model: 模型名称，类型为字符串
        :param credentials: 凭证信息，用于模型访问，类型为字典
        :return: 返回模型的单词限制，类型为整数
        """
        # 获取模型架构
        model_schema = self.get_model_schema(model, credentials)

        # 检查模型架构是否存在，并且包含单词限制属性
        if model_schema and ModelPropertyKey.WORD_LIMIT in model_schema.model_properties:
            return model_schema.model_properties[ModelPropertyKey.WORD_LIMIT]

    def _get_model_workers_limit(self, model: str, credentials: dict) -> int:
        """
        获取给定TTS模型的音频最大工作线程数

        :param model: 指定的文本转语音模型名称
        :param credentials: 用于认证的凭证字典
        :return: 返回模型配置的最大工作线程数，类型为int

        通过模型架构获取指定模型的最大工作线程数。如果模型架构中定义了最大工作线程数，则返回该值。
        """
        # 获取模型架构
        model_schema = self.get_model_schema(model, credentials)

        # 检查模型架构是否存在且包含最大工作线程数的属性
        if model_schema and ModelPropertyKey.MAX_WORKERS in model_schema.model_properties:
            return model_schema.model_properties[ModelPropertyKey.MAX_WORKERS]

    @staticmethod
    def _split_text_into_sentences(org_text, max_length=2000, pattern=r'[。.!?]'):
        match = re.compile(pattern)
        tx = match.finditer(org_text)
        start = 0
        result = []
        one_sentence = ''
        for i in tx:
            end = i.regs[0][1]
            tmp = org_text[start:end]
            if len(one_sentence + tmp) > max_length:
                result.append(one_sentence)
                one_sentence = ''
            one_sentence += tmp
            start = end
        last_sens = org_text[start:]
        if last_sens:
            one_sentence += last_sens
        if one_sentence != '':
            result.append(one_sentence)
        return result
