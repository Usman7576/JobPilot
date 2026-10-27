"""Fake job sources for pipeline and API tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.providers.sources import RawJob, SourceError, SourceInfo, SourceQuery


def raw_job(
    source: str, n: int, *, title: str = "Python Developer", company: str = "Acme Inc"
) -> RawJob:
    return RawJob(
        source=source,
        source_job_id=f"{source}-{n}",
        url=f"https://{source}.example.com/jobs/{n}?utm_source=x",
        title=f"{title} {n}" if n else title,
        company=company,
        location="Berlin, Germany",
        description=(
            "<p>We use Python, FastAPI and PostgreSQL on AWS.</p>"
            "<p>3+ years of experience required. Apply: jobs@acme.example</p>"
        ),
        description_is_html=True,
        posted_at=datetime.now(UTC) - timedelta(days=1),
    )


class FakeSource:
    def __init__(
        self,
        name: str,
        jobs: list[RawJob] | None = None,
        *,
        error: SourceError | None = None,
        configured: bool = True,
        default_on: bool = True,
    ) -> None:
        self.info = SourceInfo(
            name=name,
            label=name.title(),
            kind="api",
            default_on=default_on,
            requires_key=not configured,
            note="fake",
            min_interval_seconds=0,
        )
        self.jobs = jobs or []
        self.error = error
        self.configured = configured
        self.queries: list[SourceQuery] = []

    def is_configured(self) -> bool:
        return self.configured

    def fetch(self, query: SourceQuery) -> list[RawJob]:
        self.queries.append(query)
        if self.error:
            raise self.error
        return list(self.jobs)
