"""The tracker board: which column each application status sits in, and where cards can go.

Columns: Saved -> Applied -> Replied -> Interview -> Offer / Rejected.
Statuses the app manages itself (drafting, ready, queued) live inside a column; the user
moves cards only between columns.
"""

from __future__ import annotations

from typing import Literal

from app.models.enums import ApplicationStatus as S

Column = Literal["saved", "applied", "replied", "interview", "offer", "rejected"]
COLUMNS: tuple[Column, ...] = ("saved", "applied", "replied", "interview", "offer", "rejected")

_COLUMN_OF: dict[S, Column] = {
    S.SAVED: "saved",
    S.DRAFTING: "saved",
    S.READY: "saved",
    S.QUEUED: "applied",
    S.APPLIED: "applied",
    S.REPLIED: "replied",
    S.INTERVIEW: "interview",
    S.OFFER: "offer",
    S.REJECTED: "rejected",
    S.WITHDRAWN: "rejected",
}
# Dropping a card into a column sets this status (withdrawn is chosen explicitly).
STATUS_FOR: dict[Column, S] = {
    "saved": S.SAVED,  # the service makes it READY when drafts exist
    "applied": S.APPLIED,
    "replied": S.REPLIED,
    "interview": S.INTERVIEW,
    "offer": S.OFFER,
    "rejected": S.REJECTED,
}
# Past "applied": the candidate already applied, so no follow-up reminder is needed.
AFTER_APPLY = (S.REPLIED, S.INTERVIEW, S.OFFER, S.REJECTED, S.WITHDRAWN)
APPLIED_OR_LATER = (S.APPLIED, *AFTER_APPLY)


def column_of(status: S) -> Column:
    return _COLUMN_OF[status]


def target_status(column: Column, current: S, withdrawn: bool = False) -> S:
    """The status a card gets when dropped into `column` (moving within a column keeps it)."""
    if withdrawn:
        return S.WITHDRAWN
    if column_of(current) == column:
        return current
    return STATUS_FOR[column]


def position_between(before: float | None, after: float | None) -> float:
    """Fractional ordering: a position between two neighbours (either may be missing)."""
    if before is None and after is None:
        return 1000.0
    if before is None:
        return (after or 0.0) - 1000.0
    if after is None:
        return before + 1000.0
    return (before + after) / 2
