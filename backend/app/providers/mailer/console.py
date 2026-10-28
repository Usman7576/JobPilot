from __future__ import annotations

import sys

from app.providers.mailer.base import OutgoingMail


class ConsoleMailer:
    """Prints mail to stdout. Dev only: bypasses log redaction on purpose so links are usable."""

    async def send(self, mail: OutgoingMail) -> None:
        self.send_sync(mail)

    def send_sync(self, mail: OutgoingMail) -> None:
        sys.stdout.write(
            f"\n----- MAIL to={mail.to} -----\nSubject: {mail.subject}\n\n{mail.text}\n"
            "-----------------------------\n"
        )
        sys.stdout.flush()
