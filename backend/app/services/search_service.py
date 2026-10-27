"""API-side search runs: start (one at a time per user), read progress, cancel."""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, Conflict, NotFound, ServiceUnavailable
from app.core.logging import get_logger
from app.models import JobMatch, Preference, SearchRun, SearchRunSource, User, UserJob
from app.models.enums import MatchStage, SearchKind, SearchStatus, SearchTrigger, SourceRunStatus
from app.providers.sources import all_sources
from app.schemas.match import ScoreEstimate
from app.schemas.search import SearchRunOut, SearchRunSourceOut
from app.services import job_service, llm_gateway, matching
from app.services.search_pipeline import ACTIVE_STATUSES

log = get_logger(__name__)
STALE_AFTER = timedelta(minutes=30)


async def estimate(db: AsyncSession, user: User) -> ScoreEstimate:
    """AI requests the next scoring pass would use (5 jobs per request, best N only)."""
    key = await job_service.active_resume_key(db, user)
    left = llm_gateway.requests_left_today()
    if key is None:
        return ScoreEstimate(
            jobs_to_score=0, llm_requests=0, requests_left_today=left, has_resume=False
        )
    resume_id, version = key
    current = and_(
        JobMatch.job_id == UserJob.job_id,
        JobMatch.resume_id == resume_id,
        JobMatch.profile_version == version,
    )
    unscored = await db.scalar(
        select(func.count())
        .select_from(UserJob)
        .outerjoin(JobMatch, current)
        .where(
            UserJob.user_id == user.id,
            UserJob.dismissed_at.is_(None),
            or_(
                JobMatch.id.is_(None),
                and_(JobMatch.hard_filter_passed.is_(True), JobMatch.stage != MatchStage.SCORED),
            ),
        )
    )
    pref = await db.get(Preference, user.id)
    top_n = (
        pref.stage1_top_n if pref and pref.stage1_top_n else None
    ) or get_settings().stage1_top_n
    jobs = min(int(unscored or 0), top_n)
    return ScoreEstimate(
        jobs_to_score=jobs,
        llm_requests=math.ceil(jobs / matching.BATCH),
        requests_left_today=left,
        has_resume=True,
    )


class SearchNotReady(AppError):
    status_code, code, title = 422, "search_not_ready", "Set your job preferences first"


def to_out(run: SearchRun, sources: list[SearchRunSource]) -> SearchRunOut:
    registry = all_sources()
    return SearchRunOut(
        id=run.id,
        kind=SearchKind((run.query_snapshot or {}).get("kind") or SearchKind.JOBS),
        trigger=run.trigger,
        status=run.status,
        progress=run.progress,
        stage_detail=run.stage_detail,
        counts=run.counts or {},
        error=run.error,
        started_at=run.started_at,
        finished_at=run.finished_at,
        created_at=run.created_at,
        is_active=run.status in ACTIVE_STATUSES,
        sources=[
            SearchRunSourceOut(
                source=s.source,
                label=registry[s.source].info.label if s.source in registry else s.source,
                status=s.status,
                fetched_count=s.fetched_count,
                error_code=s.error_code,
                error_message=s.error_message,
                duration_ms=s.duration_ms,
            )
            for s in sources
        ],
    )


async def _sources_of(db: AsyncSession, run_id: uuid.UUID) -> list[SearchRunSource]:
    rows = await db.scalars(
        select(SearchRunSource)
        .where(SearchRunSource.run_id == run_id)
        .order_by(SearchRunSource.created_at)
    )
    return list(rows)


async def active_run(db: AsyncSession, user: User) -> SearchRun | None:
    run = await db.scalar(
        select(SearchRun)
        .where(SearchRun.user_id == user.id, SearchRun.status.in_(ACTIVE_STATUSES))
        .order_by(SearchRun.created_at.desc())
        .limit(1)
    )
    if run is not None and run.created_at < datetime.now(UTC) - STALE_AFTER:
        # The worker died mid-run; don't let it block new searches forever.
        run.status = SearchStatus.FAILED
        run.error = "This search stopped responding."
        run.finished_at = datetime.now(UTC)
        await db.commit()
        return None
    return run


async def start(
    db: AsyncSession,
    user: User,
    kind: SearchKind = SearchKind.JOBS,
    trigger: SearchTrigger = SearchTrigger.MANUAL,
) -> SearchRunOut:
    pref = await db.get(Preference, user.id)
    if pref is None or not pref.target_titles:
        raise SearchNotReady("Add at least one target job title in your preferences.")
    if not pref.sources:
        raise SearchNotReady("Turn on at least one job source in your preferences.")
    current = await active_run(db, user)
    if current is not None:
        raise Conflict("A search is already running.", run_id=str(current.id))

    snapshot = {
        "kind": kind.value,
        "target_titles": pref.target_titles,
        "locations": pref.locations,
        "remote_types": pref.remote_types,
        "posted_within_days": pref.posted_within_days,
        "results_per_source": pref.results_per_source,
        "sources": pref.sources,
    }
    run = SearchRun(user_id=user.id, trigger=trigger, query_snapshot=snapshot, counts={})
    db.add(run)
    await db.flush()
    for name in pref.sources:
        db.add(SearchRunSource(run_id=run.id, source=name, status=SourceRunStatus.PENDING))
    await db.commit()
    await db.refresh(run)

    from app.tasks.search_tasks import run_search

    try:
        result = run_search.delay(str(run.id))
    except Exception as exc:
        log.error("enqueue_failed", task="run_search", error_type=type(exc).__name__)
        run.status = SearchStatus.FAILED
        run.error = "Couldn't start the search."
        await db.commit()
        raise ServiceUnavailable("Couldn't start the search. Try again in a moment.") from exc
    await db.refresh(run)
    if run.celery_root_id is None:
        run.celery_root_id = result.id
        await db.commit()
    return to_out(run, await _sources_of(db, run.id))


async def get_owned(db: AsyncSession, user: User, run_id: uuid.UUID) -> SearchRun:
    run = await db.scalar(
        select(SearchRun).where(SearchRun.id == run_id, SearchRun.user_id == user.id)
    )
    if run is None:
        raise NotFound("Search not found")
    return run


async def get(db: AsyncSession, user: User, run_id: uuid.UUID) -> SearchRunOut:
    run = await get_owned(db, user, run_id)
    return to_out(run, await _sources_of(db, run.id))


async def recent(db: AsyncSession, user: User, limit: int) -> list[SearchRunOut]:
    runs = await db.scalars(
        select(SearchRun)
        .where(SearchRun.user_id == user.id)
        .order_by(SearchRun.created_at.desc())
        .limit(limit)
    )
    return [to_out(r, await _sources_of(db, r.id)) for r in runs]


async def cancel(db: AsyncSession, user: User, run_id: uuid.UUID) -> SearchRunOut:
    run = await get_owned(db, user, run_id)
    if run.status in ACTIVE_STATUSES:
        # The worker checks this between sources and queries, then stops.
        run.status = SearchStatus.CANCELLED
        run.stage_detail = "Cancelled"
        run.finished_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(run)
    return to_out(run, await _sources_of(db, run.id))
