from os.path import abspath, dirname, join
from threading import Lock
from typing import Any

from transformers import GPT2Tokenizer as TransformerGPT2Tokenizer

# 初始化全局变量
_tokenizer = None
_lock = Lock()

class GPT2Tokenizer:
    @staticmethod
    def _get_num_tokens_by_gpt2(text: str) -> int:
        """
        使用GPT-2分词器获取文本的令牌数量
        
        参数:
        text: str - 需要分词的文本字符串
        
        返回值:
        int - 文本字符串分词后的令牌数量
        """
        _tokenizer = GPT2Tokenizer.get_encoder()  # 获取GPT-2分词器
        tokens = _tokenizer.encode(text, verbose=False)  # 对文本进行编码
        return len(tokens)  # 返回编码后令牌的数目
    
    @staticmethod
    def get_num_tokens(text: str) -> int:
        """
        获取输入文本的令牌数量
        
        参数:
        text: str - 需要计算令牌数量的文本字符串
        
        返回值:
        int - 输入文本的令牌数量
        """
        return GPT2Tokenizer._get_num_tokens_by_gpt2(text)  # 调用内部方法计算令牌数量
    
    @staticmethod
    def get_encoder() -> Any:
        """
        获取GPT-2的分词器实例
        
        返回值:
        Any - GPT-2分词器的实例，具体类型依据实现而定
        """
        global _tokenizer, _lock  # 引用全局变量
        with _lock:  # 确保线程安全
            if _tokenizer is None:  # 如果分词器尚未初始化
                base_path = abspath(__file__)  # 获取当前文件的绝对路径
                gpt2_tokenizer_path = join(dirname(base_path), 'gpt2')  # 拼接GPT-2分词器路径
                _tokenizer = TransformerGPT2Tokenizer.from_pretrained(gpt2_tokenizer_path)  # 从预训练模型加载分词器

            return _tokenizer  # 返回GPT-2分词器实例