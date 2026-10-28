from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage
from urllib.parse import unquote, urlparse

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from app.providers.mailer.base import OutgoingMail


class SmtpMailer:
    """SMTP via URL: smtp://host:port (plain), smtp+starttls://user:pass@host:587, smtps://..."""

    def __init__(self, url: str, sender: str) -> None:
        parsed = urlparse(url)
        self._scheme = parsed.scheme
        self._host = parsed.hostname or "localhost"
        self._port = parsed.port or (465 if parsed.scheme == "smtps" else 25)
        self._user = unquote(parsed.username) if parsed.username else None
        self._password = unquote(parsed.password) if parsed.password else None
        self._sender = sender

    async def send(self, mail: OutgoingMail) -> None:
        await asyncio.to_thread(self._send_sync, mail)

    def send_sync(self, mail: OutgoingMail) -> None:
        self._send_sync(mail)

    @retry(
        retry=retry_if_exception_type((smtplib.SMTPException, OSError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10),
        reraise=True,
    )
    def _send_sync(self, mail: OutgoingMail) -> None:
        msg = EmailMessage()
        msg["From"] = self._sender
        msg["To"] = mail.to
        msg["Subject"] = mail.subject
        msg.set_content(mail.text)
        if mail.html:
            msg.add_alternative(mail.html, subtype="html")

        smtp_cls = smtplib.SMTP_SSL if self._scheme == "smtps" else smtplib.SMTP
        with smtp_cls(self._host, self._port, timeout=15) as client:
            if self._scheme == "smtp+starttls":
                client.starttls()
            if self._user and self._password:
                client.login(self._user, self._password)
            client.send_message(msg)
