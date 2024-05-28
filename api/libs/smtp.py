import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


class SMTPClient:
    """
    SMTP 客户端类，用于发送电子邮件。

    参数:
    server: str - SMTP 服务器的地址。
    port: int - SMTP 服务器的端口号。
    username: str - 发送邮件的账户用户名。
    password: str - 发送邮件的账户密码。
    _from: str - 邮件的发件人地址。
    use_tls: bool - 是否使用 TLS 加密连接，默认为 False。
    """

    def __init__(self, server: str, port: int, username: str, password: str, _from: str, use_tls=False):
        # 初始化 SMTP 客户端属性
        self.server = server
        self.port = port
        self._from = _from
        self.username = username
        self.password = password
        self._use_tls = use_tls

    def send(self, mail: dict):
        smtp = None
        try:
            smtp = smtplib.SMTP(self.server, self.port, timeout=10)
            if self._use_tls:
                smtp.starttls()
            if self.username and self.password:
                smtp.login(self.username, self.password)

            msg = MIMEMultipart()
            msg['Subject'] = mail['subject']
            msg['From'] = self._from
            msg['To'] = mail['to']
            msg.attach(MIMEText(mail['html'], 'html'))

            smtp.sendmail(self._from, mail['to'], msg.as_string())
        except smtplib.SMTPException as e:
            logging.error(f"SMTP error occurred: {str(e)}")
            raise
        except TimeoutError as e:
            logging.error(f"Timeout occurred while sending email: {str(e)}")
            raise
        except Exception as e:
            logging.error(f"Unexpected error occurred while sending email: {str(e)}")
            raise
        finally:
            if smtp:
                smtp.quit()
