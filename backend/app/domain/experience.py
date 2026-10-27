"""Years of experience and seniority, computed from work history (not trusted from the LLM)."""

from __future__ import annotations

import re
from datetime import date

from app.models.enums import Seniority
from app.schemas.profile import WorkEntry

_INTERN = re.compile(r"\b(intern|internship|trainee|apprentice)\b", re.I)


def _month_index(value: str | None, today: date, *, is_end: bool) -> int | None:
    if value is None:
        return None
    if value == "present":
        return today.year * 12 + today.month - 1
    parts = value.split("-")
    year = int(parts[0])
    # A bare year means January for a start date and December for an end date.
    month = int(parts[1]) if len(parts) > 1 else (12 if is_end else 1)
    return year * 12 + month - 1


def professional_years(work: list[WorkEntry], today: date | None = None) -> float | None:
    """Total non-internship experience in years, with overlapping jobs counted once."""
    today = today or date.today()
    now = today.year * 12 + today.month - 1
    intervals: list[tuple[int, int]] = []
    for job in work:
        if _INTERN.search(job.title):
            continue
        start = _month_index(job.start, today, is_end=False)
        if start is None:
            continue
        end = _month_index(job.end, today, is_end=True)
        if end is None:
            end = start  # unknown end: count the start month only
        start, end = min(start, now), min(end, now)
        if end >= start:
            intervals.append((start, end + 1))
    if not intervals:
        return None

    intervals.sort()
    months = 0
    cur_start, cur_end = intervals[0]
    for start, end in intervals[1:]:
        if start <= cur_end:
            cur_end = max(cur_end, end)
        else:
            months += cur_end - cur_start
            cur_start, cur_end = start, end
    months += cur_end - cur_start
    return round(months / 12, 1)


def reconcile_years(computed: float | None, llm_value: float | None) -> float | None:
    """Prefer the date math; fall back to the LLM only when dates are missing."""
    if computed is None:
        return llm_value
    return computed


def seniority_from_years(years: float | None) -> Seniority | None:
    if years is None:
        return None
    if years < 3:
        return Seniority.JUNIOR
    if years < 6:
        return Seniority.MID
    if years < 10:
        return Seniority.SENIOR
    return Seniority.STAFF
