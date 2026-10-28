from functools import lru_cache

from app.core.config import get_settings
from app.providers.mailer.base import Mailer, OutgoingMail
from app.providers.mailer.console import ConsoleMailer
from app.providers.mailer.smtp import SmtpMailer

_override: Mailer | None = None


def set_mailer_override(mailer: Mailer | None) -> None:
    """Tests swap in a fake for worker-side mail (the API side uses dependency overrides)."""
    global _override
    _override = mailer


def get_mailer() -> Mailer:
    if _override is not None:
        return _override
    return _build()


@lru_cache
def _build() -> Mailer:
    settings = get_settings()
    if settings.mail_backend == "smtp":
        return SmtpMailer(settings.smtp_url, settings.mail_from)
    return ConsoleMailer()


__all__ = ["Mailer", "OutgoingMail", "get_mailer", "set_mailer_override"]
