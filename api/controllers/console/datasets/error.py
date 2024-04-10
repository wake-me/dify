from libs.exception import BaseHTTPException


# 定义了一系列与文件上传和处理相关的HTTP异常
class NoFileUploadedError(BaseHTTPException):
    """未上传文件错误。表示在请求中没有包含预期的文件。
    Attributes:
        error_code (str): 错误代码，用于标识错误类型。
        description (str): 错误描述，提供关于错误的简要说明。
        code (int): HTTP状态码，表示错误的严重性和类型。
    """
    error_code = 'no_file_uploaded'
    description = "Please upload your file."
    code = 400

class TooManyFilesError(BaseHTTPException):
    """上传文件数量过多错误。表示上传的文件数量超过了允许的最大值。
    Attributes:
        error_code (str): 错误代码，用于标识错误类型。
        description (str): 错误描述，提供关于错误的简要说明。
        code (int): HTTP状态码，表示错误的严重性和类型。
    """
    error_code = 'too_many_files'
    description = "Only one file is allowed."
    code = 400

class FileTooLargeError(BaseHTTPException):
    """上传文件过大错误。表示上传的文件大小超过了服务器允许的最大值。
    Attributes:
        error_code (str): 错误代码，用于标识错误类型。
        description (str): 错误描述，包含关于超过文件大小限制的额外信息。
        code (int): HTTP状态码，表示错误的严重性和类型。
    """
    error_code = 'file_too_large'
    description = "File size exceeded. {message}"
    code = 413

class UnsupportedFileTypeError(BaseHTTPException):
    """上传文件类型不受支持错误。表示上传的文件类型不在服务器支持的范围内。
    Attributes:
        error_code (str): 错误代码，用于标识错误类型。
        description (str): 错误描述，提供关于不受支持的文件类型的说明。
        code (int): HTTP状态码，表示错误的严重性和类型。
    """
    error_code = 'unsupported_file_type'
    description = "File type not allowed."
    code = 415

class HighQualityDatasetOnlyError(BaseHTTPException):
    """仅支持高质数据集错误。表示当前操作仅支持高质量的数据集。
    Attributes:
        error_code (str): 错误代码，用于标识错误类型。
        description (str): 错误描述，提供关于操作限制的说明。
        code (int): HTTP状态码，表示错误的严重性和类型。
    """
    error_code = 'high_quality_dataset_only'
    description = "Current operation only supports 'high-quality' datasets."
    code = 400

class DatasetNotInitializedError(BaseHTTPException):
    """数据集未初始化错误。表示数据集仍在初始化或索引构建过程中，不可进行操作。
    Attributes:
        error_code (str): 错误代码，用于标识错误类型。
        description (str): 错误描述，提供关于数据集状态的说明。
        code (int): HTTP状态码，表示错误的严重性和类型。
    """
    error_code = 'dataset_not_initialized'
    description = "The dataset is still being initialized or indexing. Please wait a moment."
    code = 400

class ArchivedDocumentImmutableError(BaseHTTPException):
    """归档文档不可编辑错误。表示已经归档的文档不允许进行修改。
    Attributes:
        error_code (str): 错误代码，用于标识错误类型。
        description (str): 错误描述，提供关于归档文档属性的说明。
        code (int): HTTP状态码，表示错误的严重性和类型。
    """
    error_code = 'archived_document_immutable'
    description = "The archived document is not editable."
    code = 403

class DatasetNameDuplicateError(BaseHTTPException):
    """数据集名称重复错误。表示尝试创建一个具有与现有数据集相同名称的新数据集。
    Attributes:
        error_code (str): 错误代码，用于标识错误类型。
        description (str): 错误描述，提供关于数据集名称重复的说明。
        code (int): HTTP状态码，表示错误的严重性和类型。
    """
    error_code = 'dataset_name_duplicate'
    description = "The dataset name already exists. Please modify your dataset name."
    code = 409

class InvalidActionError(BaseHTTPException):
    """无效操作错误。表示尝试执行一个不存在或者无意义的操作。
    Attributes:
        error_code (str): 错误代码，用于标识错误类型。
        description (str): 错误描述，提供关于操作无效的说明。
        code (int): HTTP状态码，表示错误的严重性和类型。
    """
    error_code = 'invalid_action'
    description = "Invalid action."
    code = 400

class DocumentAlreadyFinishedError(BaseHTTPException):
    """文档已经完成错误。表示文档已经处理完成，不允许重复处理。
    Attributes:
        error_code (str): 错误代码，用于标识错误类型。
        description (str): 错误描述，提供关于文档状态的说明。
        code (int): HTTP状态码，表示错误的严重性和类型。
    """
    error_code = 'document_already_finished'
    description = "The document has been processed. Please refresh the page or go to the document details."
    code = 400

class DocumentIndexingError(BaseHTTPException):
    """文档索引错误。表示文档正在被处理，暂时无法进行编辑等操作。
    Attributes:
        error_code (str): 错误代码，用于标识错误类型。
        description (str): 错误描述，提供关于文档索引状态的说明。
        code (int): HTTP状态码，表示错误的严重性和类型。
    """
    error_code = 'document_indexing'
    description = "The document is being processed and cannot be edited."
    code = 400

class InvalidMetadataError(BaseHTTPException):
    """无效元数据错误。表示提交的元数据内容不正确。
    Attributes:
        error_code (str): 错误代码，用于标识错误类型。
        description (str): 错误描述，提供关于元数据验证失败的说明。
        code (int): HTTP状态码，表示错误的严重性和类型。
    """
    error_code = 'invalid_metadata'
    description = "The metadata content is incorrect. Please check and verify."
    code = 400