import hashlib
import json
import os
import re
import site
import subprocess
import tempfile
import unicodedata
from contextlib import contextmanager

import requests
from bs4 import BeautifulSoup, CData, Comment, NavigableString
from newspaper import Article
from regex import regex

from core.rag.extractor import extract_processor
from core.rag.extractor.extract_processor import ExtractProcessor

# 定义一个完整的页面模板，包含页面的基本结构和占位符。
FULL_TEMPLATE = """
TITLE: {title}
AUTHORS: {authors}
PUBLISH DATE: {publish_date}
TOP_IMAGE_URL: {top_image}
TEXT:

{text}
"""


def page_result(text: str, cursor: int, max_length: int) -> str:
    """
    分页处理文本，从给定的光标位置开始返回长度为`max_length`的子字符串。
    
    参数:
    text: str - 需要分页的原始文本。
    cursor: int - 开始提取子字符串的光标位置。
    max_length: int - 子字符串的最大长度。
    
    返回:
    str - 从光标位置开始的指定长度的子字符串。
    """
    return text[cursor: cursor + max_length]


def get_url(url: str, user_agent: str = None) -> str:
    """
    获取URL的内容并以字符串形式返回。
    
    参数:
    url: str - 需要获取内容的URL地址。
    user_agent: str - 发送请求时使用的用户代理字符串，默认为None（使用预定义的用户代理）。
    
    返回:
    str - 从URL获取到的内容，如果请求失败或内容类型不受支持，将返回相应的错误信息。
    """
    # 设置请求头
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    if user_agent:
        headers["User-Agent"] = user_agent
    
    # 定义支持的内容类型
    supported_content_types = extract_processor.SUPPORT_URL_CONTENT_TYPES + ["text/html"]

    # 发送GET请求并处理响应
    response = requests.get(url, headers=headers, allow_redirects=True, timeout=(5, 10))

    # 检查状态码
    if response.status_code != 200:
        return "URL returned status code {}.".format(response.status_code)

    # 检查内容类型
    main_content_type = response.headers.get('Content-Type').split(';')[0].strip()
    if main_content_type not in supported_content_types:
        return "Unsupported content-type [{}] of URL.".format(main_content_type)

    # 处理支持的URL内容类型
    if main_content_type in extract_processor.SUPPORT_URL_CONTENT_TYPES:
        return ExtractProcessor.load_from_url(url, return_text=True)

    # 使用readabilipy库提取文章的主要文本
    a = extract_using_readabilipy(response.text)

    # 如果无法提取到有效文本，则尝试使用newspaper3k库进行处理
    if not a['plain_text'] or not a['plain_text'].strip():
        return get_url_from_newspaper3k(url)

    # 使用提取到的信息填充页面模板
    res = FULL_TEMPLATE.format(
        title=a['title'],
        authors=a['byline'],
        publish_date=a['date'],
        top_image="",
        text=a['plain_text'] if a['plain_text'] else "",
    )

    return res

def get_url_from_newspaper3k(url: str) -> str:
    """
    从给定的URL提取文章信息，并格式化为特定的字符串模板。

    参数:
    url (str): 需要提取信息的网页URL。

    返回:
    str: 包含文章标题、作者、发布日期、顶部图片和文本的格式化字符串。
    """

    # 初始化Article对象并下载、解析网页
    a = Article(url)
    a.download()
    a.parse()

    # 使用提取的信息填充模板
    res = FULL_TEMPLATE.format(
        title=a.title,
        authors=a.authors,
        publish_date=a.publish_date,
        top_image=a.top_image,
        text=a.text,
    )

    return res


def extract_using_readabilipy(html):
    """
    使用Readabilipy库从HTML代码中提取文章的主要内容。

    参数:
    html (str): 需要分析的HTML代码。

    返回:
    dict: 包含文章标题、作者、发布日期、内容以及纯文本内容的字典。
    """
    # 使用临时文件存储HTML代码
    with tempfile.NamedTemporaryFile(delete=False, mode='w+') as f_html:
        f_html.write(html)
        f_html.close()
        html_path = f_html.name

    # 使用NodeJS和Readability.js解析HTML，并将结果保存到临时JSON文件
    article_json_path = html_path + ".json"
    jsdir = os.path.join(find_module_path('readabilipy'), 'javascript')
    with chdir(jsdir):
        subprocess.check_call(["node", "ExtractArticle.js", "-i", html_path, "-o", article_json_path])

    # 从JSON文件中读取解析结果
    with open(article_json_path, encoding="utf-8") as json_file:
        input_json = json.loads(json_file.read())

    # 清理临时文件
    os.unlink(article_json_path)
    os.unlink(html_path)

    # 初始化存储文章信息的字典
    article_json = {
        "title": None,
        "byline": None,
        "date": None,
        "content": None,
        "plain_content": None,
        "plain_text": None
    }

    # 填充文章信息字典
    if input_json:
        if "title" in input_json and input_json["title"]:
            article_json["title"] = input_json["title"]
        if "byline" in input_json and input_json["byline"]:
            article_json["byline"] = input_json["byline"]
        if "date" in input_json and input_json["date"]:
            article_json["date"] = input_json["date"]
        if "content" in input_json and input_json["content"]:
            article_json["content"] = input_json["content"]
            article_json["plain_content"] = plain_content(article_json["content"], False, False)
            article_json["plain_text"] = extract_text_blocks_as_plain_text(article_json["plain_content"])
        if "textContent" in input_json and input_json["textContent"]:
            article_json["plain_text"] = input_json["textContent"]
            article_json["plain_text"] = re.sub(r'\n\s*\n', '\n', article_json["plain_text"])

    return article_json


def find_module_path(module_name):
    """
    查找给定模块的路径。

    参数:
    module_name (str): 需要查找路径的模块名称。

    返回:
    str: 模块的路径；如果找不到，则返回None。
    """
    # 遍历所有站点包路径，寻找模块
    for package_path in site.getsitepackages():
        potential_path = os.path.join(package_path, module_name)
        if os.path.exists(potential_path):
            return potential_path

    return None

@contextmanager
def chdir(path):
    """
    一个上下文管理器，用于临时更改当前工作目录。
    进入上下文时更改目录，在退出上下文时返回原始目录。
    
    参数:
    path (str): 想要切换到的目录路径。
    
    返回:
    无返回值，但提供一个临时更改目录的上下文。
    """
    original_path = os.getcwd()  # 获取当前工作目录
    os.chdir(path)  # 切换到指定路径
    try:
        yield
    finally:
        os.chdir(original_path)  # 退出时切换回原始目录

def extract_text_blocks_as_plain_text(paragraph_html):
    """
    从HTML段落中提取文本块，并以纯文本形式返回。
    
    参数:
    paragraph_html (str): 包含文本块的HTML段落。
    
    返回:
    list: 包含纯文本表示的文本块的列表。
    """
    # 使用BeautifulSoup加载HTML段落作为DOM
    soup = BeautifulSoup(paragraph_html, 'html.parser')
    
    # 找到所有列表元素
    list_elements = soup.find_all(['ul', 'ol'])
    
    # 为列表项前缀添加"* "，并将列表转换为段落
    for list_element in list_elements:
        plain_items = "".join(list(filter(None, [plain_text_leaf_node(li)["text"] for li in list_element.find_all('li')])))
        list_element.string = plain_items
        list_element.name = "p"  # 将列表元素转换为段落(p标签)
    
    # 选择所有文本块
    text_blocks = [s.parent for s in soup.find_all(string=True)]
    
    # 将文本块转换为纯文本形式
    text_blocks = [plain_text_leaf_node(block) for block in text_blocks]
    
    # 移除空段落
    text_blocks = list(filter(lambda p: p["text"] is not None, text_blocks))
    
    return text_blocks

def plain_text_leaf_node(element):
    """
    从HTML元素中提取纯文本，并进行标准化处理。
    
    参数:
    element: BeautifulSoup对象，表示一个HTML元素。
    
    返回:
    dict: 包含提取的纯文本的字典，如果元素为空，则返回None。
    """
    # 从元素中提取纯文本，移除子HTML元素，进行标准化处理
    plain_text = normalise_text(element.get_text())
    
    # 对列表项进行特殊处理，添加前缀"* "
    if plain_text != "" and element.name == "li":
        plain_text = "* {}, ".format(plain_text)
    
    # 如果纯文本为空，则设置为None
    if plain_text == "":
        plain_text = None
    
    # 如果元素包含"data-node-index"属性，则添加到返回的字典中
    if "data-node-index" in element.attrs:
        plain = {"node_index": element["data-node-index"], "text": plain_text}
    else:
        plain = {"text": plain_text}
    
    return plain

def plain_content(readability_content, content_digests, node_indexes):
    """
    将给定的HTML内容转换为纯文本格式，可选地添加内容摘要和节点索引。
    
    参数:
    readability_content (str): 要转换的HTML内容。
    content_digests (bool): 是否为元素添加内容摘要属性。
    node_indexes (bool): 是否为元素添加节点索引属性。
    
    返回:
    str: 转换后的纯文本内容。
    """
    # 使用BeautifulSoup加载HTML内容作为DOM
    soup = BeautifulSoup(readability_content, 'html.parser')
    
    # 将所有元素转换为纯文本形式
    elements = plain_elements(soup.contents, content_digests, node_indexes)
    
    if node_indexes:
        # 如果需要，为元素添加节点索引属性
        elements = [add_node_indexes(element) for element in elements]
    
    # 使用纯文本元素替换文章内容
    soup.contents = elements
    
    return str(soup)  # 返回转换后的HTML内容

def plain_elements(elements, content_digests, node_indexes):
    """
    将一系列HTML元素转换为纯文本形式，可选地添加内容摘要和节点索引。
    
    参数:
    elements: 要转换的HTML元素列表。
    content_digests (bool): 是否为元素添加内容摘要属性。
    node_indexes (bool): 是否为元素添加节点索引属性。
    
    返回:
    list: 转换后的纯文本元素列表。
    """
    # 为所有元素获取纯文本版本
    elements = [plain_element(element, content_digests, node_indexes)
                for element in elements]
    
    if content_digests:
        # 如果需要，为元素添加内容摘要属性
        elements = [add_content_digest(element) for element in elements]
    
    return elements

def plain_element(element, content_digests, node_indexes):
    # For lists, we make each item plain text
    if is_leaf(element):
        # For leaf node elements, extract the text content, discarding any HTML tags
        # 1. Get element contents as text
        plain_text = element.get_text()
        # 2. Normalise the extracted text string to a canonical representation
        plain_text = normalise_text(plain_text)
        # 3. Update element content to be plain text
        element.string = plain_text
    elif is_text(element):
        if is_non_printing(element):
            # The simplified HTML may have come from Readability.js so might
            # have non-printing text (e.g. Comment or CData). In this case, we
            # keep the structure, but ensure that the string is empty.
            element = type(element)("")
        else:
            plain_text = element.string
            plain_text = normalise_text(plain_text)
            element = type(element)(plain_text)
    else:
        # If not a leaf node or leaf type call recursively on child nodes, replacing
        element.contents = plain_elements(element.contents, content_digests, node_indexes)
    return element


def add_node_indexes(element, node_index="0"):
    # Can't add attributes to string types
    if is_text(element):
        return element
    # Add index to current element
    element["data-node-index"] = node_index
    # Add index to child elements
    for local_idx, child in enumerate(
            [c for c in element.contents if not is_text(c)], start=1):
        # Can't add attributes to leaf string types
        child_index = "{stem}.{local}".format(
            stem=node_index, local=local_idx)
        add_node_indexes(child, node_index=child_index)
    return element


def normalise_text(text):
    """Normalise unicode and whitespace."""
    # Normalise unicode first to try and standardise whitespace characters as much as possible before normalising them
    text = strip_control_characters(text)
    text = normalise_unicode(text)
    text = normalise_whitespace(text)
    return text


def strip_control_characters(text):
    """Strip out unicode control characters which might break the parsing."""
    # Unicode control characters
    #   [Cc]: Other, Control [includes new lines]
    #   [Cf]: Other, Format
    #   [Cn]: Other, Not Assigned
    #   [Co]: Other, Private Use
    #   [Cs]: Other, Surrogate
    control_chars = set(['Cc', 'Cf', 'Cn', 'Co', 'Cs'])
    retained_chars = ['\t', '\n', '\r', '\f']

    # Remove non-printing control characters
    return "".join(["" if (unicodedata.category(char) in control_chars) and (char not in retained_chars) else char for char in text])


def normalise_unicode(text):
    """Normalise unicode such that things that are visually equivalent map to the same unicode string where possible."""
    normal_form = "NFKC"
    text = unicodedata.normalize(normal_form, text)
    return text


def normalise_whitespace(text):
    """Replace runs of whitespace characters with a single space as this is what happens when HTML text is displayed."""
    text = regex.sub(r"\s+", " ", text)
    # Remove leading and trailing whitespace
    text = text.strip()
    return text

def is_leaf(element):
    return (element.name in ['p', 'li'])


def is_text(element):
    return isinstance(element, NavigableString)


def is_non_printing(element):
    return any(isinstance(element, _e) for _e in [Comment, CData])


def add_content_digest(element):
    if not is_text(element):
        element["data-content-digest"] = content_digest(element)
    return element


def content_digest(element):
    if is_text(element):
        # Hash
        trimmed_string = element.string.strip()
        if trimmed_string == "":
            digest = ""
        else:
            digest = hashlib.sha256(trimmed_string.encode('utf-8')).hexdigest()
    else:
        contents = element.contents
        num_contents = len(contents)
        if num_contents == 0:
            # No hash when no child elements exist
            digest = ""
        elif num_contents == 1:
            # If single child, use digest of child
            digest = content_digest(contents[0])
        else:
            # Build content digest from the "non-empty" digests of child nodes
            digest = hashlib.sha256()
            child_digests = list(
                filter(lambda x: x != "", [content_digest(content) for content in contents]))
            for child in child_digests:
                digest.update(child.encode('utf-8'))
            digest = digest.hexdigest()
    return digest
