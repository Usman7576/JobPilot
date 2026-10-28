"""Gmail reply detection (worker side).

Privacy first: the app never lists the inbox. It searches only for messages *from* the
contacts and company domains you applied to, reads just the sender, subject and Gmail's
short preview, and stores only the outcome (a status change and a notification).

- From the exact contact you applied to: the card moves to Replied, and to Interview or
  Rejected when the AI is confident (>= 0.8). Auto-replies don't count as replies.
- From the same company domain only: a suggestion notification, never an automatic move.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domain.contacts import company_domain
from app.integrations import gmail
from app.models import Application, Company, Integration, Job, Notification
from app.models.enums import (
    ApplicationStatus,
    EventActor,
    IntegrationProvider,
    NotificationKind,
    ReplyClassification,
    UsageFeature,
)
from app.prompts.registry import load_prompt, render
from app.providers.llm import LLMError
from app.services import integration_service, llm_gateway
from app.services.application_events import record_event

log = get_logger(__name__)
S = ApplicationStatus
TRACKED = (S.APPLIED, S.REPLIED, S.INTERVIEW)  # waiting on them, or mid-process
LOOKBACK = timedelta(days=30)
OVERLAP = timedelta(hours=1)  # re-check a little of the last window, in case mail arrived late
CONFIDENT = 0.8
SEEN_KEEP = 300
MAX_TERMS = 40  # Gmail search terms per query
# Shared mail providers: a reply from "@gmail.com" says nothing about which company it is.
FREE_MAIL = {"gmail.com", "googlemail.com", "yahoo.com", "outlook.com", "hotmail.com",
             "live.com", "icloud.com", "proton.me", "protonmail.com", "aol.com"}  # fmt: skip
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE = re.compile(r"\+?\d[\d ().-]{7,}\d")

LABEL_TEXT = {
    ReplyClassification.INTERVIEW: "looks like an interview invite",
    ReplyClassification.REJECTION: "looks like a rejection",
    ReplyClassification.POSITIVE: "looks positive",
    ReplyClassification.AUTO_REPLY: "looks like an automatic reply",
    ReplyClassification.OTHER: "needs a look",
}


class ReplyLabel(BaseModel):
    label: Literal["interview", "rejection", "positive", "auto_reply", "other"]
    confidence: float = Field(ge=0, le=1)


@dataclass
class Tracked:
    application: Application
    job: Job
    contact: str | None
    domain: str | None


@dataclass
class CheckResult:
    messages: int = 0
    moved: int = 0
    suggested: int = 0


def _domain_of(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    domain = email.rsplit("@", 1)[1].lower()
    return None if domain in FREE_MAIL else domain


def tracked_applications(session: Session, user_id: uuid.UUID) -> list[Tracked]:
    rows = session.execute(
        select(Application, Job, Company.domain)
        .join(Job, Job.id == Application.job_id)
        .outerjoin(Company, Company.id == Job.company_id)
        .where(Application.user_id == user_id, Application.status.in_(TRACKED))
    ).all()
    out = []
    for app, job, known_domain in rows:
        contact = (app.contact_email or "").lower() or None
        domain = (
            _domain_of(contact) or known_domain or company_domain(job.apply_url, job.primary_url)
        )
        out.append(Tracked(app, job, contact, domain if domain not in FREE_MAIL else None))
    return out


def build_query(items: list[Tracked], since: datetime) -> str | None:
    terms = list(dict.fromkeys(t for i in items for t in (i.contact, i.domain) if t))[:MAX_TERMS]
    if not terms:
        return None
    return f"from:({' OR '.join(terms)}) after:{int(since.timestamp())}"


def _trim(text: str) -> str:
    """Contact details aren't needed to classify a reply: drop them before the AI sees it."""
    return _PHONE.sub("[phone]", _EMAIL.sub("[email]", text))


def classify(
    session: Session, user_id: uuid.UUID, t: Tracked, msg: gmail.MessageMeta
) -> ReplyLabel:
    prompt = render(
        load_prompt("reply_classify", 1),
        job_title=t.job.title,
        company=t.job.company_name,
        subject=_trim(msg.subject),
        preview=_trim(msg.snippet),
    )
    label, _ = llm_gateway.generate(
        session,
        user_id=user_id,
        feature=UsageFeature.CLASSIFY,
        prompt=prompt,
        parse=ReplyLabel.model_validate,
        ref_type="application",
        ref_id=t.application.id,
    )
    return label


def _match(items: list[Tracked], sender: str) -> tuple[Tracked | None, bool]:
    """(application, exact): the exact contact wins; else one tracked app at that domain."""
    for t in items:
        if t.contact and t.contact == sender:
            return t, True
    domain = _domain_of(sender)
    same = [t for t in items if domain and t.domain == domain]
    if not same:
        return None, False
    newest = max(same, key=lambda t: t.application.sent_at or t.application.created_at)
    return newest, False


def _apply(session: Session, t: Tracked, msg: gmail.MessageMeta, label: ReplyLabel) -> bool:
    """Exact-contact reply: update the card. Returns True when the status changed."""
    app = t.application
    kind = ReplyClassification(label.label)
    app.reply_classification = kind
    if kind == ReplyClassification.AUTO_REPLY:
        return False
    app.last_reply_at = max(app.last_reply_at or msg.received_at, msg.received_at)
    app.follow_up_at = None  # they answered: no reminder
    target = app.status
    if app.status == S.APPLIED:
        target = S.REPLIED
    if label.confidence >= CONFIDENT and kind == ReplyClassification.INTERVIEW:
        target = S.INTERVIEW if app.status in (S.APPLIED, S.REPLIED) else target
    if label.confidence >= CONFIDENT and kind == ReplyClassification.REJECTION:
        target = S.REJECTED
    if target == app.status:
        return False
    record_event(
        session, app, target, EventActor.GMAIL,
        f"Reply from {msg.sender}: {LABEL_TEXT[kind]}", from_status=app.status,
    )  # fmt: skip
    app.status = target
    return True


def check(session: Session, user_id: uuid.UUID, now: datetime | None = None) -> CheckResult:
    now = now or datetime.now(UTC)
    result = CheckResult()
    row = session.scalar(
        select(Integration).where(
            Integration.user_id == user_id, Integration.provider == IntegrationProvider.GMAIL
        )
    )
    if row is None or not integration_service.reply_detection_on(row):
        return result
    config = dict(row.config or {})
    items = tracked_applications(session, user_id)
    last = config.get("replies_checked_at")
    since = max(
        (datetime.fromisoformat(last) - OVERLAP) if last else now - LOOKBACK, now - LOOKBACK
    )
    query = build_query(items, since)
    seen: list[str] = list(config.get("reply_seen", []))
    try:
        token = integration_service.access_token(session, row)
        ids = [i for i in gmail.search(token, query) if i not in seen] if query else []
        for message_id in ids:
            msg = gmail.message_meta(token, message_id)
            seen.append(message_id)
            t, exact = _match(items, msg.sender)
            if t is None or msg.received_at < (t.application.sent_at or t.application.created_at):
                continue
            result.messages += 1
            try:
                label = classify(session, user_id, t, msg)
            except LLMError:
                label = ReplyLabel(label="other", confidence=0)
            kind = ReplyClassification(label.label)
            if exact:
                moved = _apply(session, t, msg, label)
                result.moved += moved
                if kind != ReplyClassification.AUTO_REPLY:
                    _notify(session, user_id, t, f"Reply from {t.job.company_name}",
                            f"{LABEL_TEXT[kind].capitalize()}."
                            + (" The card was moved for you." if moved else ""))  # fmt: skip
            elif kind != ReplyClassification.AUTO_REPLY:
                result.suggested += 1
                _notify(session, user_id, t, f"Possible reply from {t.job.company_name}",
                        f"An email from {msg.sender} {LABEL_TEXT[kind]}. "
                        "Check it and move the card if it's about this application.")  # fmt: skip
    except gmail.GmailAuthError as exc:
        integration_service.mark_needs_reauth(session, row, str(exc))
        session.commit()
        return result
    except gmail.GmailSendError as exc:
        row.last_error = str(exc)
        session.commit()
        return result
    row.config = {
        **config,
        "replies_checked_at": now.isoformat(),
        "reply_seen": seen[-SEEN_KEEP:],
    }
    row.last_error = None
    session.commit()
    log.info("replies_checked", messages=result.messages, moved=result.moved)
    return result


def _notify(session: Session, user_id: uuid.UUID, t: Tracked, title: str, body: str) -> None:
    session.add(
        Notification(
            user_id=user_id,
            kind=NotificationKind.REPLY_DETECTED,
            title=title,
            body=body,
            link=f"/applications/{t.application.id}",
        )
    )


def users_to_check(session: Session) -> list[uuid.UUID]:
    rows = session.scalars(
        select(Integration).where(Integration.provider == IntegrationProvider.GMAIL)
    ).all()
    return [r.user_id for r in rows if integration_service.reply_detection_on(r)]
