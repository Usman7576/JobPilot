from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class OutgoingMail:
    to: str
    subject: str
    text: str
    html: str | None = None


class Mailer(Protocol):
    """App-originated mail only (verification, password reset, digests).

    Job applications go through the user's own Gmail, never through this.
    """

    async def send(self, mail: OutgoingMail) -> None: ...
