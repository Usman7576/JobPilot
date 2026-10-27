"""Find who to email for a job: the posting itself, then (optionally) Hunter.io.

Hunter results are cached per company for 30 days in company_contacts and shared across
users, so the free plan's 25 searches a month go a long way. Any Hunter problem just means
"no email found": the user can still apply on the site or type an address.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.contacts import company_domain, pick_best_email
from app.models import Company, CompanyContact, Job
from app.models.enums import ContactSource

log = get_logger(__name__)
HUNTER_URL = "https://api.hunter.io/v2/domain-search"
CACHE_DAYS = 30
_RECRUITING_WORDS = ("recruit", "talent", "hr", "human resources", "people", "hiring")


@dataclass(frozen=True)
class Contact:
    email: str | None
    source: ContactSource
    confidence: int | None


NONE = Contact(None, ContactSource.NONE, None)


def _hunter_rank(row: CompanyContact) -> tuple[int, int]:
    role = (row.role or "").lower()
    return (int(any(w in role for w in _RECRUITING_WORDS)), row.confidence or 0)


def _cached(session: Session, company_id: Any) -> list[CompanyContact]:
    since = datetime.now(UTC) - timedelta(days=CACHE_DAYS)
    return list(
        session.scalars(
            select(CompanyContact).where(
                CompanyContact.company_id == company_id,
                CompanyContact.source == ContactSource.HUNTER_DOMAIN,
                CompanyContact.fetched_at >= since,
            )
        )
    )


def _hunter_search(domain: str | None, company: str) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"api_key": get_settings().hunter_api_key, "limit": 10}
    if domain:
        params["domain"] = domain
    else:
        params["company"] = company
    resp = httpx.get(HUNTER_URL, params=params, timeout=15)
    if resp.status_code != 200:
        log.warning("hunter_failed", status=resp.status_code)
        return []
    emails: list[dict[str, Any]] = (resp.json().get("data") or {}).get("emails") or []
    return emails


def _from_hunter(session: Session, job: Job) -> Contact:
    if job.company_id is not None and (cached := _cached(session, job.company_id)):
        top = max(cached, key=_hunter_rank)
        return Contact(top.email, ContactSource.HUNTER_DOMAIN, top.confidence)

    company = session.get(Company, job.company_id) if job.company_id else None
    domain = (company.domain if company else None) or company_domain(job.apply_url, job.primary_url)
    if company is not None and domain and not company.domain:
        company.domain = domain
    try:
        found = _hunter_search(domain, job.company_name)
    except httpx.HTTPError as exc:
        log.warning("hunter_unreachable", error_type=type(exc).__name__)
        return NONE
    now = datetime.now(UTC)
    rows: list[dict[str, Any]] = [
        {
            "company_id": job.company_id,
            "email": str(e["value"]).lower(),
            "source": ContactSource.HUNTER_DOMAIN,
            "confidence": int(e.get("confidence") or 0),
            "role": " ".join(str(e.get(k) or "") for k in ("position", "department")).strip()
            or None,
            "verified_status": ((e.get("verification") or {}).get("status")),
            "fetched_at": now,
        }
        for e in found
        if e.get("value")
    ]
    if not rows:
        return NONE
    if job.company_id is not None:
        stmt = pg_insert(CompanyContact).values(rows)
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=["company_id", "email"],
                set_={
                    "confidence": stmt.excluded.confidence,
                    "role": stmt.excluded.role,
                    "fetched_at": stmt.excluded.fetched_at,
                },
            )
        )
    best = max(
        rows,
        key=lambda r: (
            int(any(w in (r["role"] or "").lower() for w in _RECRUITING_WORDS)),
            r["confidence"],
        ),
    )
    return Contact(best["email"], ContactSource.HUNTER_DOMAIN, best["confidence"])


def discover(session: Session, job: Job) -> Contact:
    if email := pick_best_email(job.contact_emails):
        return Contact(email, ContactSource.JOB_DESCRIPTION, 90)
    if get_settings().hunter_api_key:
        return _from_hunter(session, job)
    return NONE
