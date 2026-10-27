"""Registry of every job source. Users pick which ones to use in their preferences."""

from __future__ import annotations

from app.providers.sources.base import (
    JobSource,
    RawJob,
    SourceError,
    SourceInfo,
    SourceQuery,
)
from app.providers.sources.feeds import ArbeitnowSource, RemotiveSource
from app.providers.sources.jobspy_source import JobSpySource
from app.providers.sources.keyed_apis import AdzunaSource, JoobleSource, SerpApiSource

_SOURCES: list[JobSource] = [
    ArbeitnowSource(),
    AdzunaSource(),
    JoobleSource(),
    RemotiveSource(),
    SerpApiSource(),
    JobSpySource("linkedin", "LinkedIn", interval=10),
    JobSpySource("indeed", "Indeed", interval=5),
    JobSpySource("glassdoor", "Glassdoor", interval=10),
    JobSpySource("google", "Google Jobs", interval=5),
]

_override: dict[str, JobSource] | None = None


def set_sources_override(sources: list[JobSource] | None) -> None:
    """Tests replace the registry with fake sources."""
    global _override
    _override = {s.info.name: s for s in sources} if sources is not None else None


def all_sources() -> dict[str, JobSource]:
    return _override if _override is not None else {s.info.name: s for s in _SOURCES}


def default_source_names() -> list[str]:
    return [name for name, s in all_sources().items() if s.info.default_on]


__all__ = [
    "JobSource",
    "RawJob",
    "SourceError",
    "SourceInfo",
    "SourceQuery",
    "all_sources",
    "default_source_names",
    "set_sources_override",
]
