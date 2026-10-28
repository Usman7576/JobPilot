"""Worker-side: start daily searches when they're due, and email the digest afterwards."""

from __future__ import annotations

import html
import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.schedule import is_due
from app.models import Job, JobMatch, Preference, SearchRun, User, UserJob
from app.models.enums import MatchStage, SearchKind, SearchTrigger
from app.providers.mailer import OutgoingMail, get_mailer
from app.services import matching
from app.services.search_pipeline import ACTIVE_STATUSES
from app.services.search_service import new_run

log = get_logger(__name__)
DIGEST_LIMIT = 10


def _last_scheduled(session: Session, user_id: uuid.UUID, kind: str) -> datetime | None:
    last: datetime | None = session.scalar(
        select(func.max(SearchRun.created_at)).where(
            SearchRun.user_id == user_id,
            SearchRun.trigger == SearchTrigger.SCHEDULED,
            SearchRun.query_snapshot["kind"].astext == kind,
        )
    )
    return last


def _busy(session: Session, user_id: uuid.UUID) -> bool:
    return bool(
        session.scalar(
            select(func.count())
            .select_from(SearchRun)
            .where(SearchRun.user_id == user_id, SearchRun.status.in_(ACTIVE_STATUSES))
        )
    )


def dispatch_due(session: Session, now: datetime | None = None) -> list[uuid.UUID]:
    """Start the daily searches that are due. One run per user per tick: a user with both
    jobs and internships gets the second search on a later tick, once the first is done."""
    from app.tasks.search_tasks import run_search

    now = now or datetime.now(UTC)
    rows = session.execute(
        select(Preference, User)
        .join(User, User.id == Preference.user_id)
        .where(
            Preference.daily_search_enabled.is_(True),
            User.is_active.is_(True),
            User.deletion_requested_at.is_(None),
            func.cardinality(Preference.target_titles) > 0,
            func.cardinality(Preference.sources) > 0,
        )
    ).all()
    started: list[uuid.UUID] = []
    for pref, user in rows:
        if _busy(session, user.id):
            continue
        for kind in pref.daily_search_kinds:
            last = _last_scheduled(session, user.id, kind)
            if not is_due(now, user.timezone, pref.daily_search_hour, last):
                continue
            run, sources = new_run(pref, SearchKind(kind), SearchTrigger.SCHEDULED)
            session.add(run)
            session.flush()
            session.add_all(sources)
            session.commit()
            run_search.delay(str(run.id))
            started.append(run.id)
            log.info("scheduled_search_started", kind=kind)
            break
    return started


def send_digest(session: Session, run: SearchRun) -> bool:
    """Email the new strong matches this scheduled run found. Nothing new, no email."""
    pref = session.get(Preference, run.user_id)
    user = session.get(User, run.user_id)
    if pref is None or user is None or not pref.digest_enabled:
        return False
    resume = matching.active_resume(session, run.user_id)
    if resume is None:
        return False
    rows = session.execute(
        select(Job, JobMatch)
        .join(
            UserJob,
            and_(
                UserJob.job_id == Job.id,
                UserJob.user_id == run.user_id,
                UserJob.first_run_id == run.id,
                UserJob.dismissed_at.is_(None),
            ),
        )
        .join(
            JobMatch,
            and_(
                JobMatch.job_id == Job.id,
                JobMatch.resume_id == resume.id,
                JobMatch.profile_version == resume.profile_version,
            ),
        )
        .where(
            JobMatch.stage == MatchStage.SCORED,
            JobMatch.overall_score >= pref.digest_min_score,
        )
        .order_by(JobMatch.overall_score.desc())
        .limit(DIGEST_LIMIT)
    ).all()
    if not rows:
        return False

    base = get_settings().app_base_url
    kind = run.query_snapshot.get("kind", "jobs")
    noun = "internship" if kind == SearchKind.INTERNSHIPS else "job"
    count = len(rows)
    strength = "strong " if pref.digest_min_score >= 80 else ""
    plural = "es" if count != 1 else ""
    subject = f"{count} new {strength}{noun} match{plural} for you (score {pref.digest_min_score}+)"
    lines = [f"Your daily search found {count} new {noun}(s) that fit your resume well:", ""]
    items = []
    for job, match in rows:
        link = f"{base}/jobs/{job.id}"
        lines += [f"{match.overall_score}  {job.title} at {job.company_name}", f"    {link}"]
        if match.why_good_fit:
            lines.append(f"    {match.why_good_fit}")
        lines.append("")
        items.append(
            f'<li style="margin:0 0 12px"><strong>{match.overall_score}</strong> &middot; '
            f'<a href="{html.escape(link)}">{html.escape(job.title)}</a> at '
            f"{html.escape(job.company_name)}"
            + (
                f'<br><span style="color:#555">{html.escape(match.why_good_fit)}</span>'
                if match.why_good_fit
                else ""
            )
            + "</li>"
        )
    footer = f"Change the time or turn this off in Settings: {base}/settings"
    lines.append(footer)
    page = (
        f"<p>Your daily search found {count} new {noun}(s) that fit your resume well:</p>"
        f'<ul style="padding-left:18px">{"".join(items)}</ul>'
        f'<p style="color:#777;font-size:12px">Change the time or turn this off in '
        f'<a href="{html.escape(base)}/settings">Settings</a>.</p>'
    )
    get_mailer().send_sync(
        OutgoingMail(to=user.email, subject=subject, text="\n".join(lines), html=page)
    )
    log.info("digest_sent", matches=count)
    return True
