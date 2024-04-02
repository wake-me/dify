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
        """
        发送电子邮件。

        参数:
        mail: dict - 包含邮件信息的字典，应包含 subject, to 和 html 键。
        """
        # 连接到 SMTP 服务器
        smtp = smtplib.SMTP(self.server, self.port)
        # 如果配置了 TLS，则开始 TLS 加密会话
        if self._use_tls:
            smtp.starttls()
        # 如果提供了用户名和密码，则登录 SMTP 服务器
        if self.username and self.password:
            smtp.login(self.username, self.password)
        # 构建邮件消息体
        msg = MIMEMultipart()
        msg['Subject'] = mail['subject']
        msg['From'] = self._from
        msg['To'] = mail['to']
        # 添加邮件正文
        msg.attach(MIMEText(mail['html'], 'html'))
        # 发送邮件
        smtp.sendmail(self.username, mail['to'], msg.as_string())
        # 关闭与 SMTP 服务器的连接
        smtp.quit()