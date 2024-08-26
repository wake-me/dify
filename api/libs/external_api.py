import re
import sys

from flask import current_app, got_request_exception
from flask_restful import Api, http_status_message
from werkzeug.datastructures import Headers
from werkzeug.exceptions import HTTPException

from core.errors.error import AppInvokeQuotaExceededError


class ExternalApi(Api):
    def handle_error(self, e):
        """
        处理API错误，将抛出的异常转换为Flask响应，包括适当的HTTP状态码和响应体。

        :param e: 抛出的异常对象
        :type e: Exception
        :return: 转换后的Flask响应对象
        """

        # 发送请求异常事件
        got_request_exception.send(current_app, exception=e)

        headers = Headers()
        # 如果异常是HTTPException类型
        if isinstance(e, HTTPException):
            # 如果已有响应体，则直接返回该响应体
            if e.response is not None:
                resp = e.get_response()
                return resp

            # 获取HTTP状态码和默认错误信息
            status_code = e.code
            default_data = {
                "code": re.sub(r"(?<!^)(?=[A-Z])", "_", type(e).__name__).lower(),
                "message": getattr(e, "description", http_status_message(status_code)),
                "status": status_code,
            }

            if (
                default_data["message"]
                and default_data["message"] == "Failed to decode JSON object: Expecting value: line 1 column 1 (char 0)"
            ):
                default_data["message"] = "Invalid JSON payload received or JSON payload is empty."

            # 从HTTP异常中获取响应头
            headers = e.get_response().headers
        # 如果异常是ValueError类型
        elif isinstance(e, ValueError):
            # 设置状态码和默认错误信息
            status_code = 400
            default_data = {
                "code": "invalid_param",
                "message": str(e),
                "status": status_code,
            }
        elif isinstance(e, AppInvokeQuotaExceededError):
            status_code = 429
            default_data = {
                "code": "too_many_requests",
                "message": str(e),
                "status": status_code,
            }
        else:
            # 其他异常，默认为服务器错误
            status_code = 500
            default_data = {
                "message": http_status_message(status_code),
            }

        # Werkzeug exceptions generate a content-length header which is added
        # to the response in addition to the actual content-length header
        # https://github.com/flask-restful/flask-restful/issues/534
        remove_headers = ("Content-Length",)

        for header in remove_headers:
            headers.pop(header, None)

        data = getattr(e, "data", default_data)

        # 处理自定义错误信息
        error_cls_name = type(e).__name__
        if error_cls_name in self.errors:
            custom_data = self.errors.get(error_cls_name, {})
            custom_data = custom_data.copy()
            status_code = custom_data.get("status", 500)

            if "message" in custom_data:
                custom_data["message"] = custom_data["message"].format(
                    message=str(e.description if hasattr(e, "description") else e)
                )
            data.update(custom_data)

        # 记录500及以上状态码的异常到日志
        if status_code and status_code >= 500:
            exc_info = sys.exc_info()
            if exc_info[1] is None:
                exc_info = None
            current_app.log_exception(exc_info)

        # 处理不支持的媒体类型错误（406）
        if status_code == 406 and self.default_mediatype is None:
            supported_mediatypes = list(self.representations.keys())  # 只支持application/json
            fallback_mediatype = supported_mediatypes[0] if supported_mediatypes else "text/plain"
            data = {"code": "not_acceptable", "message": data.get("message")}
            resp = self.make_response(data, status_code, headers, fallback_mediatype=fallback_mediatype)
        elif status_code == 400:
            if isinstance(data.get("message"), dict):
                param_key, param_value = list(data.get("message").items())[0]
                data = {"code": "invalid_param", "message": param_value, "params": param_key}
            else:
                if "code" not in data:
                    data["code"] = "unknown"

            resp = self.make_response(data, status_code, headers)
        else:
            if "code" not in data:
                data["code"] = "unknown"

            resp = self.make_response(data, status_code, headers)

        # 如果是未授权的访问（401），则对响应进行特殊处理
        if status_code == 401:
            resp = self.unauthorized(resp)
        return resp
