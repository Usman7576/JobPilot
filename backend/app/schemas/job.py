from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from app.models.enums import EmploymentType, PayStatus, RemoteType, SalaryPeriod, Seniority
from app.schemas.application import ApplicationRef
from app.schemas.common import ApiModel
from app.schemas.match import MatchDetail, MatchSummary

JobSort = Literal["score", "posted", "discovered"]


class JobSourceLink(ApiModel):
    source: str
    label: str
    url: str


class JobCard(ApiModel):
    id: uuid.UUID
    title: str
    company_name: str
    location_raw: str | None
    remote_type: RemoteType
    employment_type: EmploymentType
    seniority: Seniority | None
    min_years_experience: float | None
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    salary_period: SalaryPeriod | None
    pay_status: PayStatus
    required_skills: list[str]
    snippet: str | None
    posted_at: datetime | None
    discovered_at: datetime
    sources: list[str]
    url: str
    apply_url: str | None
    has_contact_email: bool
    dismissed: bool
    match: MatchSummary | None
    # Your application to this job, if any (so the feed can mark it and skip it).
    application: ApplicationRef | None = None


class JobDetail(JobCard):
    description_text: str | None
    contact_emails: list[str]
    source_links: list[JobSourceLink]
    match: MatchDetail | None
    application: ApplicationRef | None


class JobPage(ApiModel):
    items: list[JobCard]
    total: int
    has_more: bool
    filtered_out: int  # jobs hidden by your filters (shown with include_filtered)
    has_resume: bool  # False: no active resume yet, so nothing is scored
