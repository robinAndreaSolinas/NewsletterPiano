import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os
from abc import ABC, abstractmethod


class EmailInterface(ABC):

    from_address: str
    to: list[str]
    cc: list[str]
    bcc: list[str]
    subject: str
    body: str
    attachments: list[str]

    @property
    @abstractmethod
    def recipients(self) -> list[str]:
        """Lists of all recipients(to + cc + bcc)."""
        ...

    @property
    @abstractmethod
    def message(self) -> str:
        """returns the message in string format."""
        ...


class Email(EmailInterface):
    def __init__(self,
                 from_address: list[str] | str,
                 to: list[str] | str,
                 *,
                 cc: list[str] | str = None,
                 bcc: list[str] | str = None,
                 subject: str = None,
                 body: str = None,
                 attachments: list[str] = None,
                 ):
        self.from_address = from_address if isinstance(from_address, str) else ', '.join(from_address)
        self.to = to if isinstance(to, list) else [to]
        self.cc = cc if isinstance(cc, list) else [cc] if cc else []
        self.bcc = bcc if isinstance(bcc, list) else [bcc] if bcc else []
        self.subject = subject or ""
        self.body = body or ""
        self.attachments = attachments or []

    @property
    def recipients(self):
        return self.to + self.cc + self.bcc

    @property
    def message(self):
        msg = MIMEMultipart()
        msg['From'] = self.from_address
        msg['To'] = ', '.join(self.to)
        msg['Cc'] = ', '.join(self.cc)
        # NB BCC not included in the header
        msg['Subject'] = self.subject

        msg.attach(MIMEText(self.body, 'html' if '<' in self.body and '>' in self.body else 'plain', 'UTF-8'))

        for attachment_path in self.attachments:
            if os.path.exists(attachment_path):
                with open(attachment_path, 'rb') as attachment_file:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment_file.read())
                    encoders.encode_base64(part)
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename={os.path.basename(attachment_path)}'
                    )
                    msg.attach(part)

        return msg.as_string()


def send(*email: EmailInterface,
         smtp_server: str = "localhost",
         smtp_port: int = 587,
         username: str = None,
         password: str = None,
         use_tls: bool = True):
    
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            if use_tls:
                server.starttls()

            if username and password:
                server.login(username, password)

            for mail in email:
                server.sendmail(mail.from_address, mail.recipients, mail.message)

    except smtplib.SMTPException as e:
        raise smtplib.SMTPException(f"Error sending email: {str(e)}")

__all__ = ["Email", "send"]