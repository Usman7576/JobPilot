from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from app.models.enums import EmploymentType, RemoteType, SalaryPeriod, Seniority
from app.schemas.common import ApiModel

JobSort = Literal["posted", "discovered"]


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
    required_skills: list[str]
    snippet: str | None
    posted_at: datetime | None
    discovered_at: datetime
    sources: list[str]
    url: str
    apply_url: str | None
    has_contact_email: bool
    dismissed: bool


class JobDetail(JobCard):
    description_text: str | None
    contact_emails: list[str]
    source_links: list[JobSourceLink]


class JobPage(ApiModel):
    items: list[JobCard]
    total: int
    has_more: bool
