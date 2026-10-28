from __future__ import annotations

from datetime import UTC, datetime

from app.domain.schedule import is_due, local_date


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def test_due_once_per_local_day_at_or_after_the_hour() -> None:
    # 03:30 UTC is 08:30 in Karachi (UTC+5).
    now = at("2026-10-28T03:30:00")
    assert is_due(now, "Asia/Karachi", 8, last_run=None)
    assert not is_due(now, "Asia/Karachi", 9, last_run=None)  # not 9 there yet
    assert not is_due(now, "Asia/Karachi", 8, last_run=at("2026-10-28T03:05:00"))  # ran today
    assert is_due(now, "Asia/Karachi", 8, last_run=at("2026-10-27T03:05:00"))  # yesterday


def test_a_missed_hour_still_runs_later_that_day() -> None:
    assert is_due(at("2026-10-28T15:00:00"), "UTC", 8, last_run=at("2026-10-27T08:00:00"))


def test_days_are_counted_in_the_users_time_zone() -> None:
    # 22:00 UTC on the 27th is already the 28th in Karachi.
    assert local_date(at("2026-10-27T22:00:00"), "Asia/Karachi").isoformat() == "2026-10-28"
    last = at("2026-10-27T20:00:00")  # 01:00 on the 28th in Karachi
    assert not is_due(at("2026-10-28T04:00:00"), "Asia/Karachi", 8, last_run=last)


def test_unknown_time_zone_falls_back_to_utc() -> None:
    assert is_due(at("2026-10-28T09:00:00"), "Mars/Olympus", 8, last_run=None)
