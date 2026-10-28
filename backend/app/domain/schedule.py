"""When a user's daily search is due, in their own time zone.

A search is due once per local day, at or after the chosen hour. "At or after" means a
day missed while the computer was off still runs as soon as the scheduler is back.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def local_date(moment: datetime, tz_name: str) -> date:
    return moment.astimezone(zone(tz_name)).date()


def is_due(now: datetime, tz_name: str, hour: int, last_run: datetime | None) -> bool:
    local = now.astimezone(zone(tz_name))
    if local.hour < hour:
        return False
    return last_run is None or local_date(last_run, tz_name) < local.date()
