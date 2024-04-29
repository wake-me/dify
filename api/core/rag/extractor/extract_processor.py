import tempfile
from pathlib import Path
from typing import Union

import requests
from flask import current_app

from core.rag.extractor.csv_extractor import CSVExtractor
from core.rag.extractor.entity.datasource_type import DatasourceType
from core.rag.extractor.entity.extract_setting import ExtractSetting
from core.rag.extractor.excel_extractor import ExcelExtractor
from core.rag.extractor.html_extractor import HtmlExtractor
from core.rag.extractor.markdown_extractor import MarkdownExtractor
from core.rag.extractor.notion_extractor import NotionExtractor
from core.rag.extractor.pdf_extractor import PdfExtractor
from core.rag.extractor.text_extractor import TextExtractor
from core.rag.extractor.unstructured.unstructured_doc_extractor import UnstructuredWordExtractor
from core.rag.extractor.unstructured.unstructured_eml_extractor import UnstructuredEmailExtractor
from core.rag.extractor.unstructured.unstructured_epub_extractor import UnstructuredEpubExtractor
from core.rag.extractor.unstructured.unstructured_markdown_extractor import UnstructuredMarkdownExtractor
from core.rag.extractor.unstructured.unstructured_msg_extractor import UnstructuredMsgExtractor
from core.rag.extractor.unstructured.unstructured_ppt_extractor import UnstructuredPPTExtractor
from core.rag.extractor.unstructured.unstructured_pptx_extractor import UnstructuredPPTXExtractor
from core.rag.extractor.unstructured.unstructured_text_extractor import UnstructuredTextExtractor
from core.rag.extractor.unstructured.unstructured_xml_extractor import UnstructuredXmlExtractor
from core.rag.models.document import Document
from extensions.ext_storage import storage
from models.model import UploadFile

SUPPORT_URL_CONTENT_TYPES = ['application/pdf', 'text/plain']
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"


class ExtractProcessor:
    @classmethod
    def load_from_upload_file(cls, upload_file: UploadFile, return_text: bool = False, is_automatic: bool = False) \
            -> Union[list[Document], str]:
        """
        从上传的文件中加载数据。
        
        :param cls: 类的引用，用于调用提取方法。
        :param upload_file: UploadFile对象，代表上传的文件。
        :param return_text: 布尔值，默认为False，如果为True，则返回文件的文本内容而不是文档对象列表。
        :param is_automatic: 布尔值，默认为False，控制提取过程是否自动进行。
        :return: 如果return_text为True，则返回字符串，包含文件的所有页面内容，用换行符分隔；否则返回文档对象列表。
        """
        # 设置提取参数
        extract_setting = ExtractSetting(
            datasource_type="upload_file",
            upload_file=upload_file,
            document_model='text_model'
        )
        if return_text:
            # 如果需要返回文本，将文档页面内容合并为字符串
            delimiter = '\n'
            return delimiter.join([document.page_content for document in cls.extract(extract_setting, is_automatic)])
        else:
            # 否则，直接返回提取的文档对象列表
            return cls.extract(extract_setting, is_automatic)

    @classmethod
    def load_from_url(cls, url: str, return_text: bool = False) -> Union[list[Document], str]:
        """
        从给定的URL加载内容，并根据返回文本标志返回文档列表或文本字符串。
        
        参数:
        - cls: 类的引用，用于调用提取方法。
        - url: str，要加载内容的URL地址。
        - return_text: bool，标志是否返回文本内容，默认为False，返回Document列表，如果为True，则返回合并后的文本字符串。
        
        返回值:
        - Union[list[Document], str]，如果return_text为False，返回Document对象列表；如果为True，返回合并后的文本字符串。
        """
        # 发起HTTP请求获取URL内容
        response = requests.get(url, headers={
            "User-Agent": USER_AGENT
        })

        # 使用临时目录存储下载的文件
        with tempfile.TemporaryDirectory() as temp_dir:
            # 获取URL对应的文件后缀
            suffix = Path(url).suffix
            # 构造临时文件路径
            file_path = f"{temp_dir}/{next(tempfile._get_candidate_names())}{suffix}"
            # 将获取到的内容写入临时文件
            with open(file_path, 'wb') as file:
                file.write(response.content)
            
            # 设置提取配置
            extract_setting = ExtractSetting(
                datasource_type="upload_file",
                document_model='text_model'
            )
            
            if return_text:
                # 如果需要返回文本，合并所有文档的页面内容并返回
                delimiter = '\n'
                return delimiter.join([document.page_content for document in cls.extract(
                    extract_setting=extract_setting, file_path=file_path)])
            else:
                # 否则，直接返回提取的文档列表
                return cls.extract(extract_setting=extract_setting, file_path=file_path)

    @classmethod
    def extract(cls, extract_setting: ExtractSetting, is_automatic: bool = False,
                file_path: str = None) -> list[Document]:
        """
        根据提供的提取设置，从不同数据源中提取文档信息。
        
        :param cls: 类的引用，用于调用相应的提取器。
        :param extract_setting: 提取设置对象，包含数据源类型、文件信息或Notion信息。
        :param is_automatic: 是否为自动化提取，影响某些提取器的行为。
        :param file_path: 文件的本地路径，如果为None，则从extract_setting中获取上传的文件。
        :return: 提取的文档列表，每个文档是Document类型。
        """
        if extract_setting.datasource_type == DatasourceType.FILE.value:
            # 处理文件类型数据源
            with tempfile.TemporaryDirectory() as temp_dir:
                # 下载文件到临时目录，如果未提供本地路径
                if not file_path:
                    upload_file: UploadFile = extract_setting.upload_file
                    suffix = Path(upload_file.key).suffix
                    file_path = f"{temp_dir}/{next(tempfile._get_candidate_names())}{suffix}"
                    storage.download(upload_file.key, file_path)
                
                input_file = Path(file_path)
                file_extension = input_file.suffix.lower()
                etl_type = current_app.config['ETL_TYPE']
                unstructured_api_url = current_app.config['UNSTRUCTURED_API_URL']
                
                # 根据文件扩展名选择合适的提取器
                if etl_type == 'Unstructured':
                    # 针对自动提取和非自动提取使用不同的提取器
                    extractor = cls.choose_extractor(file_extension, file_path, is_automatic, unstructured_api_url)
                else:
                    extractor = cls.choose_extractor(file_extension, file_path)
                return extractor.extract()
        elif extract_setting.datasource_type == DatasourceType.NOTION.value:
            # 处理Notion数据源
            extractor = NotionExtractor(
                notion_workspace_id=extract_setting.notion_info.notion_workspace_id,
                notion_obj_id=extract_setting.notion_info.notion_obj_id,
                notion_page_type=extract_setting.notion_info.notion_page_type,
                document_model=extract_setting.notion_info.document,
                tenant_id=extract_setting.notion_info.tenant_id,
            )
            return extractor.extract()
        else:
            # 抛出不支持的数据源类型错误
            raise ValueError(f"Unsupported datasource type: {extract_setting.datasource_type}")

    def choose_extractor(file_extension, file_path, is_automatic=False, unstructured_api_url=None):
        """
        根据文件扩展名选择合适的提取器。
        
        :param file_extension: 文件扩展名，小写。
        :param file_path: 文件路径。
        :param is_automatic: 是否为自动化提取，影响某些提取器的行为。
        :param unstructured_api_url: 用于自动化提取的API URL。
        :return: 返回选定的提取器实例。
        """
        # 选择并实例化相应的文件提取器
        if file_extension == '.xlsx' or file_extension == '.xls':
            extractor = ExcelExtractor(file_path)
        elif file_extension == '.pdf':
            extractor = PdfExtractor(file_path)
        elif file_extension in ['.md', '.markdown']:
            extractor = UnstructuredMarkdownExtractor(file_path, unstructured_api_url) if is_automatic \
                else MarkdownExtractor(file_path, autodetect_encoding=True)
        elif file_extension in ['.htm', '.html']:
            extractor = HtmlExtractor(file_path)
        elif file_extension in ['.docx']:
            extractor = UnstructuredWordExtractor(file_path, unstructured_api_url)
        elif file_extension == '.csv':
            extractor = CSVExtractor(file_path, autodetect_encoding=True)
        elif file_extension == '.msg':
            extractor = UnstructuredMsgExtractor(file_path, unstructured_api_url)
        elif file_extension == '.eml':
            extractor = UnstructuredEmailExtractor(file_path, unstructured_api_url)
        elif file_extension == '.ppt':
            extractor = UnstructuredPPTExtractor(file_path, unstructured_api_url)
        elif file_extension == '.pptx':
            extractor = UnstructuredPPTXExtractor(file_path, unstructured_api_url)
        elif file_extension == '.xml':
            extractor = UnstructuredXmlExtractor(file_path, unstructured_api_url)
        elif file_extension == 'epub':
            extractor = UnstructuredEpubExtractor(file_path, unstructured_api_url)
        else:
            # 默认为文本提取器
            extractor = UnstructuredTextExtractor(file_path, unstructured_api_url) if is_automatic \
                else TextExtractor(file_path, autodetect_encoding=True)
        return extractor
