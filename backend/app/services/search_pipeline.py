"""Worker-side search run: query each enabled source, normalize, dedupe, store, embed.

Sources run one after another (polite, and fine for one run per user). A failing source
never fails the run: it's marked failed and the run ends as `partial`.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.extraction_rules import internship_role
from app.domain.normalize import normalize
from app.models import Job, SearchRun, SearchRunSource, UserJob
from app.models.enums import EmploymentType, SearchKind, SearchStatus, SourceRunStatus
from app.providers.embeddings import get_embeddings
from app.providers.sources import SourceError, SourceQuery, all_sources
from app.services import job_store, matching, source_guard

log = get_logger(__name__)
EMBED_BATCH = 32
ACTIVE_STATUSES = (
    SearchStatus.QUEUED,
    SearchStatus.SCRAPING,
    SearchStatus.NORMALIZING,
    SearchStatus.MATCHING_STAGE1,
    SearchStatus.SCORING,
)


def build_queries(snapshot: dict[str, Any]) -> list[SourceQuery]:
    """Target titles x locations, plus a remote-only search when remote is wanted."""
    settings = get_settings()
    internships = snapshot.get("kind") == SearchKind.INTERNSHIPS
    titles: list[str] = snapshot.get("target_titles") or []
    if internships:
        # "Senior Backend Engineer" and "Backend Engineer" are the same internship search.
        titles = list(dict.fromkeys(internship_role(t) for t in titles))
    locations: list[dict[str, Any]] = snapshot.get("locations") or []
    remote_types: list[str] = snapshot.get("remote_types") or []
    days = int(snapshot.get("posted_within_days") or 7)
    wants_onsite = not remote_types or {"onsite", "hybrid"} & set(remote_types)
    wants_remote = not remote_types or "remote" in remote_types

    places: list[tuple[str | None, str | None, bool]] = []
    if wants_onsite:
        for loc in locations or [{}]:
            label = ", ".join(p for p in (loc.get("city"), loc.get("region")) if p) or None
            country = loc.get("country")
            if label and country:
                label = f"{label}, {country.upper()}"
            elif country and not label:
                label = country.upper()
            places.append((label, country, False))
    if wants_remote:
        country = locations[0].get("country") if locations else None
        places.append((None, country, True))

    queries = [
        SourceQuery(
            search_term=title,
            location=label,
            country=country,
            remote_only=remote,
            posted_within_days=days,
            results_wanted=0,  # filled below
            internship=internships,
        )
        for title in titles
        for label, country, remote in places
    ][: settings.source_max_queries_per_run]
    per_query = max(10, int(snapshot.get("results_per_source") or 30) // max(1, len(queries)))
    return [replace(q, results_wanted=per_query) for q in queries]


def _cancelled(session: Session, run: SearchRun) -> bool:
    session.refresh(run, attribute_names=["status"])
    return run.status == SearchStatus.CANCELLED


def run_search(session: Session, run_id: uuid.UUID) -> SearchStatus | None:
    run = session.get(SearchRun, run_id)
    if run is None or run.status != SearchStatus.QUEUED:
        return None
    run.status = SearchStatus.SCRAPING
    run.started_at = datetime.now(UTC)
    run.progress = 2
    run.stage_detail = "Starting search"
    session.commit()

    queries = build_queries(run.query_snapshot)
    rows = list(
        session.scalars(
            select(SearchRunSource)
            .where(SearchRunSource.run_id == run.id)
            .order_by(SearchRunSource.created_at)
        )
    )
    registry = all_sources()
    counts = {"scraped": 0, "new": 0, "duplicates": 0, "new_for_you": 0}

    for index, row in enumerate(rows):
        if _cancelled(session, run):
            break
        source = registry.get(row.source)
        started = time.monotonic()
        if source is None:
            row.status, row.error_code = SourceRunStatus.SKIPPED, "unknown_source"
        elif not source.is_configured():
            row.status, row.error_code = SourceRunStatus.SKIPPED, "not_configured"
            row.error_message = f"Add the {source.info.label} API key to .env to use it."
        elif source_guard.is_paused(row.source):
            row.status, row.error_code = SourceRunStatus.SKIPPED, "paused"
            row.error_message = "Paused after repeated failures; it retries automatically soon."
        else:
            row.status = SourceRunStatus.RUNNING
            run.stage_detail = f"Searching {source.info.label}"
            session.commit()
            _scrape_source(session, run, row, source, queries, counts)
        row.duration_ms = int((time.monotonic() - started) * 1000)
        run.progress = 2 + int(68 * (index + 1) / max(1, len(rows)))
        run.counts = dict(counts)
        session.commit()

    if not _cancelled(session, run):
        run.status = SearchStatus.NORMALIZING
        run.stage_detail = "Preparing jobs for matching"
        session.commit()
        _embed_new_jobs(session, run)
        note = None if _cancelled(session, run) else _match(session, run, counts)
        if not _cancelled(session, run):
            run.status = _final_status(rows)
            run.progress = 100
            run.stage_detail = f"Done. {note}" if note else "Done"
    run.counts = dict(counts)
    run.finished_at = datetime.now(UTC)
    session.commit()
    log.info("search_run_finished", run_id=str(run.id), status=run.status.value, **counts)
    return run.status


def _scrape_source(
    session: Session,
    run: SearchRun,
    row: SearchRunSource,
    source: Any,
    queries: list[SourceQuery],
    counts: dict[str, int],
) -> None:
    fetched = 0
    try:
        for query in queries:
            if _cancelled(session, run):
                return
            source_guard.wait_turn(source.info)
            row.attempts += 1
            for raw in source.fetch(query):
                if not raw.title or not raw.url:
                    continue
                job = normalize(raw)
                if query.internship and job.employment_type != EmploymentType.INTERNSHIP:
                    continue  # keyword searches also return regular jobs that mention interns
                result = job_store.store(session, job, user_id=run.user_id, run_id=run.id)
                fetched += 1
                counts["scraped"] += 1
                counts["new" if result.created else "duplicates"] += 1
                counts["new_for_you"] += int(result.new_for_user)
            session.commit()
    except SourceError as exc:
        session.rollback()
        row.status, row.error_code, row.error_message = (
            SourceRunStatus.FAILED,
            exc.code,
            exc.message,
        )
        row.fetched_count = fetched
        if source_guard.record_failure(row.source):
            row.error_message += " Paused for an hour after repeated failures."
        log.warning("source_failed", source=row.source, error_code=exc.code)
        return
    except Exception as exc:
        session.rollback()
        row.status, row.error_code = SourceRunStatus.FAILED, "unexpected"
        row.error_message = "Something went wrong reading this source."
        row.fetched_count = fetched
        source_guard.record_failure(row.source)
        log.exception("source_crashed", source=row.source, error_type=type(exc).__name__)
        return
    source_guard.record_success(row.source)
    row.status = SourceRunStatus.OK
    row.fetched_count = fetched


def job_embedding_text(job: Job) -> str:
    parts = [f"{job.title} at {job.company_name}"]
    if job.required_skills:
        parts.append("Skills: " + ", ".join(job.required_skills))
    if job.description_text:
        parts.append(job.description_text[:1500])
    return "\n".join(parts)


def _embed_new_jobs(session: Session, run: SearchRun) -> None:
    jobs = list(
        session.scalars(
            select(Job)
            .join(UserJob, UserJob.job_id == Job.id)
            .where(UserJob.user_id == run.user_id, Job.embedding.is_(None))
            .limit(1000)
        )
    )
    if not jobs:
        return
    provider = get_embeddings()
    for start in range(0, len(jobs), EMBED_BATCH):
        if _cancelled(session, run):
            return
        batch = jobs[start : start + EMBED_BATCH]
        vectors = provider.embed_documents([job_embedding_text(j) for j in batch])
        for job, vector in zip(batch, vectors, strict=True):
            job.embedding = vector
            job.embedding_model = provider.model_name
        run.progress = 70 + int(10 * min(1.0, (start + len(batch)) / len(jobs)))
        run.stage_detail = f"Preparing jobs for matching ({start + len(batch)}/{len(jobs)})"
        session.commit()


def _match(session: Session, run: SearchRun, counts: dict[str, int]) -> str | None:
    """Rank the user's jobs against their resume. A matching problem never fails the run."""
    run.status = SearchStatus.MATCHING_STAGE1
    run.stage_detail = "Ranking jobs against your resume"
    run.progress = 82
    session.commit()

    def on_stage2(total: int) -> None:
        if _cancelled(session, run):
            return
        run.status = SearchStatus.SCORING
        run.stage_detail = f"Scoring your {total} best matches" if total else "Nothing new to score"
        run.progress = 85
        session.commit()

    def progress(done: int, total: int) -> None:
        run.progress = 85 + int(15 * done / total)
        run.stage_detail = f"Scoring your best matches ({done}/{total})"
        session.commit()

    try:
        stats = matching.match_for_user(
            session, run.user_id, progress=progress, on_stage2=on_stage2
        )
    except Exception as exc:
        session.rollback()
        log.exception("matching_crashed", run_id=str(run.id), error_type=type(exc).__name__)
        return "Match scores couldn't be computed this time."
    counts["filtered_out"] = stats.filtered_out
    counts["scored"] = stats.scored
    return stats.stopped


def _final_status(rows: list[SearchRunSource]) -> SearchStatus:
    attempted = [r for r in rows if r.status in (SourceRunStatus.OK, SourceRunStatus.FAILED)]
    failed = [r for r in attempted if r.status == SourceRunStatus.FAILED]
    if not attempted:
        return SearchStatus.FAILED
    if len(failed) == len(attempted):
        return SearchStatus.FAILED
    return SearchStatus.PARTIAL if failed else SearchStatus.COMPLETED
