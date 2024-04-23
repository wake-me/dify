import hashlib
import subprocess
import uuid
from abc import abstractmethod
from typing import Optional

from core.model_runtime.entities.model_entities import ModelPropertyKey, ModelType
from core.model_runtime.errors.invoke import InvokeBadRequestError
from core.model_runtime.model_providers.__base.ai_model import AIModel


class TTSModel(AIModel):
    """
    TTS模型类，用于语音合成模型的管理。
    """

    model_type: ModelType = ModelType.TTS  # 指定模型类型为TTS

    def invoke(self, model: str, tenant_id: str, credentials: dict, content_text: str, voice: str, streaming: bool,
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
            self._is_ffmpeg_installed()  # 检查ffmpeg是否安装
            return self._invoke(model=model, credentials=credentials, user=user, streaming=streaming,
                                content_text=content_text, voice=voice, tenant_id=tenant_id)
        except Exception as e:
            # 转换调用过程中的错误为统一的异常格式并抛出
            raise self._transform_invoke_error(e)

    @abstractmethod
    def _invoke(self, model: str, tenant_id: str, credentials: dict, content_text: str, voice: str, streaming: bool,
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
                return [{'name': d['name'], 'value': d['mode']} for d in voices if language and language in d.get('language')]
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
    def _split_text_into_sentences(text: str, limit: int, delimiters=None):
        """
        将文本拆分为句子，确保每个句子的字符数不超过指定限制。
        
        参数:
        text: str - 需要拆分的文本。
        limit: int - 每个句子的最大字符数限制。
        delimiters: set, 可选 - 定义句子分隔符的集合，默认为中文常用的句号、感叹号、问号和分号以及换行符。
        
        返回值:
        generator - 生成器，逐个yield符合限制的句子。
        """
        if delimiters is None:
            delimiters = set('。！？；\n')  # 默认分隔符集

        buf = []  # 用于构建句子的缓冲区
        word_count = 0  # 当前句子字符计数
        for char in text:
            buf.append(char)  # 将字符加入缓冲区
            if char in delimiters:
                if word_count >= limit:
                    yield ''.join(buf)  # 达到字符限制，输出句子
                    buf = []  # 清空缓冲区
                    word_count = 0  # 重置字符计数
                else:
                    word_count += 1  # 遇到分隔符时增加字符计数
            else:
                word_count += 1  # 对非分隔符字符增加字符计数

        if buf:
            yield ''.join(buf)  # 处理最后一个句子，确保不会遗漏

    @staticmethod
    def _is_ffmpeg_installed():
        """
        检查ffmpeg是否已安装。
        
        无参数。
        
        返回值:
        - 返回True如果ffmpeg已安装并可使用。
        - 如果ffmpeg未安装或无法使用，将抛出InvokeBadRequestError异常。
        """
        try:
            output = subprocess.check_output("ffmpeg -version", shell=True)  # 尝试通过命令行获取ffmpeg版本信息
            if "ffmpeg version" in output.decode("utf-8"):  # 检查输出中是否包含"ffmpeg version"字符串
                return True
            else:
                # 如果版本信息不存在，抛出ffmpeg未安装的异常，并提供解决方法的链接
                raise InvokeBadRequestError("ffmpeg is not installed, "
                                            "details: https://docs.dify.ai/getting-started/install-self-hosted"
                                            "/install-faq#id-14.-what-to-do-if-this-error-occurs-in-text-to-speech")
        except Exception:
            # 如果尝试获取ffmpeg版本时发生任何异常，同样抛出ffmpeg未安装的异常
            raise InvokeBadRequestError("ffmpeg is not installed, "
                                        "details: https://docs.dify.ai/getting-started/install-self-hosted"
                                        "/install-faq#id-14.-what-to-do-if-this-error-occurs-in-text-to-speech")

    # Todo: To improve the streaming function
    @staticmethod
    def _get_file_name(file_content: str) -> str:
        """
        根据文件内容生成唯一的文件名。
        
        参数:
        file_content: str - 文件的内容，用于生成唯一标识。
        
        返回值:
        str - 唯一的文件名，基于文件内容的SHA-256散列值和UUID生成。
        """
        # 生成文件内容的SHA-256散列值
        hash_object = hashlib.sha256(file_content.encode())
        hex_digest = hash_object.hexdigest()

        # 定义命名空间UUID，用于生成基于散列值的唯一UUID
        namespace_uuid = uuid.UUID('a5da6ef9-b303-596f-8e88-bf8fa40f4b31')
        # 生成基于命名空间和散列值的唯一UUID
        unique_uuid = uuid.uuid5(namespace_uuid, hex_digest)
        return str(unique_uuid)
