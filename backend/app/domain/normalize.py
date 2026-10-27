"""RawJob (whatever a source returned) -> NormalizedJob (what we store)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from app.domain import dedupe, extraction_rules
from app.domain.html_text import clean_description
from app.models.enums import EmploymentType, PayStatus, RemoteType, SalaryPeriod, Seniority
from app.providers.sources import RawJob

_CURRENCIES = {"USD", "GBP", "EUR", "INR", "PKR", "CAD", "AUD", "CHF", "SGD", "AED", "NZD"}


@dataclass
class NormalizedJob:
    source: str
    source_job_id: str
    title: str
    normalized_title: str
    company_name: str
    normalized_company: str
    company_url: str | None
    location_raw: str | None
    location: dict[str, str] | None
    remote_type: RemoteType
    employment_type: EmploymentType
    seniority: Seniority | None
    min_years_experience: Decimal | None
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    salary_period: SalaryPeriod | None
    pay_status: PayStatus
    required_skills: list[str]
    description_text: str | None
    contact_emails: list[str]
    primary_url: str
    apply_url: str | None
    url_hash: str
    dedupe_hash: str
    posted_at: datetime | None
    raw_meta: dict[str, object] = field(default_factory=dict)


def _location_parts(raw: str | None) -> dict[str, str] | None:
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        return None
    if len(parts) == 1:
        return {"city": parts[0]}
    if len(parts) == 2:
        return {"city": parts[0], "country": parts[1]}
    return {"city": parts[0], "region": parts[1], "country": parts[-1]}


def normalize(raw: RawJob) -> NormalizedJob:
    title = " ".join(raw.title.split())[:300]
    company = " ".join(raw.company.split())[:200] or "Unknown"
    text = clean_description(raw.description, raw.description_is_html)
    body = text or ""

    remote = extraction_rules.detect_remote(title, raw.location, body, raw.is_remote)
    is_remote = remote == RemoteType.REMOTE

    salary_min = int(raw.salary_min) if raw.salary_min else None
    salary_max = int(raw.salary_max) if raw.salary_max else None
    currency = (raw.salary_currency or "").upper() or None
    period = SalaryPeriod(raw.salary_period) if raw.salary_period else None
    parsed = None if salary_min or salary_max else extraction_rules.parse_salary(body)
    if parsed:
        salary_min, salary_max = parsed.min, parsed.max
        currency, period = parsed.currency, parsed.period
    if salary_min and not salary_max:
        salary_max = salary_min
    if currency and currency not in _CURRENCIES:
        currency = None

    years = extraction_rules.extract_min_years(body)
    skills = extraction_rules.extract_skills(f"{title}\n{' '.join(raw.tags)}\n{body}")
    found = [e.lower() for e in raw.emails] + extraction_rules.extract_emails(body)
    emails = list(dict.fromkeys(found))

    return NormalizedJob(
        source=raw.source,
        source_job_id=raw.source_job_id[:300],
        title=title,
        normalized_title=dedupe.normalize_title(title),
        company_name=company,
        normalized_company=dedupe.normalize_company(company),
        company_url=raw.company_url,
        location_raw=raw.location,
        location=_location_parts(raw.location),
        remote_type=remote,
        employment_type=extraction_rules.detect_employment(raw.job_type, title),
        seniority=extraction_rules.seniority_from_title(title),
        min_years_experience=Decimal(str(years)) if years is not None else None,
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=currency,
        salary_period=period,
        pay_status=extraction_rules.detect_pay(title, body, bool(salary_min or salary_max)),
        required_skills=skills,
        description_text=text,
        contact_emails=emails[:5],
        primary_url=raw.url,
        apply_url=raw.apply_url,
        url_hash=dedupe.url_hash(raw.url),
        dedupe_hash=dedupe.dedupe_hash(company, title, raw.location, is_remote),
        posted_at=raw.posted_at,
        raw_meta={"tags": raw.tags[:20], "job_type": raw.job_type},
    )
