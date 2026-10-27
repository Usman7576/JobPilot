from functools import lru_cache

from app.core.config import get_settings
from app.providers.mailer.base import Mailer, OutgoingMail
from app.providers.mailer.console import ConsoleMailer
from app.providers.mailer.smtp import SmtpMailer


@lru_cache
def get_mailer() -> Mailer:
    settings = get_settings()
    if settings.mail_backend == "smtp":
        return SmtpMailer(settings.smtp_url, settings.mail_from)
    return ConsoleMailer()


__all__ = ["Mailer", "OutgoingMail", "get_mailer"]
