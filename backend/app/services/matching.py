"""Worker-side matching for one user's active resume version.

Stage 1 (no AI): hard filters + resume/job embedding similarity for every job the user has
that isn't matched yet for this profile version. Stage 2 (AI): the best few unscored jobs
are scored in batches (one request scores up to BATCH jobs), then the score is computed in
code. Rows are keyed by (job, resume, profile_version), so nothing is ever scored twice.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import and_, exists, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.base import uuid7
from app.domain import scoring
from app.domain.filters import CandidateLevel, FilterPrefs, hard_filter_reasons
from app.models import Job, JobMatch, Preference, Resume, UserJob
from app.models.enums import MatchStage, ResumeStatus, UsageFeature
from app.prompts.registry import load_prompt, render
from app.providers.llm import (
    LLMError,
    LLMNotConfigured,
    LLMQuotaExhausted,
    LLMRateLimited,
    LLMResult,
    LLMUnavailable,
)
from app.schemas.match import LLMJobScore, LLMScoreBatch
from app.schemas.profile import ResumeProfile
from app.services import llm_gateway

log = get_logger(__name__)
BATCH = 5
DESCRIPTION_CHARS = 3000
RATE_LIMIT_WAITS = (20, 40)  # seconds to wait for the per-minute limit, then give up

ProgressFn = Callable[[int, int], None]


@dataclass
class MatchStats:
    considered: int = 0
    filtered_out: int = 0
    scored: int = 0
    failed: int = 0
    stopped: str | None = None  # why scoring stopped early, shown to the user


def active_resume(session: Session, user_id: uuid.UUID) -> Resume | None:
    return session.scalar(
        select(Resume).where(
            Resume.user_id == user_id,
            Resume.is_active.is_(True),
            Resume.status == ResumeStatus.PARSED,
            Resume.embedding.is_not(None),
        )
    )


def filter_prefs(pref: Preference | None) -> FilterPrefs:
    if pref is None:
        return FilterPrefs()
    return FilterPrefs(
        exclude_companies=list(pref.exclude_companies),
        exclude_keywords=list(pref.exclude_keywords),
        include_keywords=list(pref.include_keywords),
        remote_types=list(pref.remote_types),
        locations=list(pref.locations),
        salary_min=pref.salary_min,
        salary_currency=pref.salary_currency,
        # Jobs already in the user's list stay matchable a bit longer than the search window.
        posted_within_days=max(pref.posted_within_days, 14),
    )


def candidate_level(resume: Resume) -> CandidateLevel:
    years = resume.total_years_experience
    return CandidateLevel(float(years) if years is not None else None, resume.seniority)


# --- stage 1 -------------------------------------------------------------------------------


def run_stage1(
    session: Session,
    user_id: uuid.UUID,
    resume: Resume,
    prefs: FilterPrefs,
    job_ids: list[uuid.UUID] | None = None,
) -> MatchStats:
    stats = MatchStats()
    already = exists().where(
        JobMatch.job_id == Job.id,
        JobMatch.resume_id == resume.id,
        JobMatch.profile_version == resume.profile_version,
    )
    similarity = (1 - Job.embedding.cosine_distance(resume.embedding)).label("similarity")
    stmt = (
        select(Job, similarity)
        .join(UserJob, UserJob.job_id == Job.id)
        .where(
            UserJob.user_id == user_id,
            UserJob.dismissed_at.is_(None),
            Job.embedding.is_not(None),
            ~already,
        )
    )
    if job_ids:
        stmt = stmt.where(Job.id.in_(job_ids))
    level = candidate_level(resume)
    rows: list[dict[str, Any]] = []
    for job, sim in session.execute(stmt.limit(2000)).all():
        reasons = hard_filter_reasons(job, prefs, level)
        stats.considered += 1
        stats.filtered_out += bool(reasons)
        rows.append(
            {
                "id": uuid7(),
                "user_id": user_id,
                "job_id": job.id,
                "resume_id": resume.id,
                "profile_version": resume.profile_version,
                "similarity": float(sim),
                "hard_filter_passed": not reasons,
                "hard_filter_reasons": reasons,
                "stage": MatchStage.STAGE1,
            }
        )
    if rows:
        session.execute(
            pg_insert(JobMatch)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["job_id", "resume_id", "profile_version"])
        )
        session.flush()
    return stats


def pick_for_scoring(
    session: Session,
    user_id: uuid.UUID,
    resume: Resume,
    top_n: int,
    job_ids: list[uuid.UUID] | None = None,
) -> list[tuple[JobMatch, Job]]:
    stmt = (
        select(JobMatch, Job)
        .join(Job, Job.id == JobMatch.job_id)
        .join(UserJob, and_(UserJob.job_id == Job.id, UserJob.user_id == user_id))
        .where(
            JobMatch.resume_id == resume.id,
            JobMatch.profile_version == resume.profile_version,
        )
    )
    if job_ids:  # explicit rescore: score these even if filtered or scored before
        stmt = stmt.where(Job.id.in_(job_ids))
    else:
        stmt = stmt.where(
            JobMatch.hard_filter_passed.is_(True),
            JobMatch.stage != MatchStage.SCORED,
            UserJob.dismissed_at.is_(None),
        )
    stmt = stmt.order_by(JobMatch.similarity.desc().nulls_last()).limit(top_n)
    return [(m, j) for m, j in session.execute(stmt).all()]


# --- stage 2 -------------------------------------------------------------------------------


def candidate_payload(resume: Resume) -> dict[str, Any]:
    """The profile without name or contact details: scoring doesn't need them."""
    profile = ResumeProfile.model_validate(resume.profile or {})
    return {
        "summary": profile.summary,
        "total_years_experience": profile.total_years_experience,
        "seniority": profile.seniority.value if profile.seniority else None,
        "preferred_roles": profile.preferred_roles,
        "skills": [{"name": s.name, "level": s.proficiency} for s in profile.skills[:40]],
        "work_history": [
            {
                "title": w.title,
                "company": w.company,
                "start": w.start,
                "end": w.end,
                "highlights": w.bullets[:4],
            }
            for w in profile.work_history[:5]
        ],
        "education": [
            {"degree": e.degree, "field": e.field, "institution": e.institution}
            for e in profile.education[:3]
        ],
    }


def preferences_payload(pref: Preference | None) -> dict[str, Any]:
    if pref is None:
        return {}
    return {
        "target_titles": pref.target_titles,
        "work_arrangements": pref.remote_types,
        "locations": [
            ", ".join(str(v) for k, v in loc.items() if k in ("city", "country") and v)
            for loc in pref.locations
        ],
        "experience_levels": pref.experience_levels,
    }


def job_payload(job: Job) -> dict[str, Any]:
    salary = None
    if job.salary_min or job.salary_max:
        salary = f"{job.salary_min}-{job.salary_max} {job.salary_currency or ''} per " + (
            job.salary_period.value if job.salary_period else "year"
        )
    return {
        "title": job.title,
        "company": job.company_name,
        "location": job.location_raw,
        "work_arrangement": job.remote_type.value,
        "employment_type": job.employment_type.value,
        "seniority": job.seniority.value if job.seniority else None,
        "min_years_experience": (
            float(job.min_years_experience) if job.min_years_experience is not None else None
        ),
        "salary": salary,
        "skills_detected": job.required_skills[:25],
        "description": (job.description_text or "")[:DESCRIPTION_CHARS],
    }


def _generate(session: Session, user_id: uuid.UUID, prompt: Any) -> tuple[LLMScoreBatch, LLMResult]:
    for wait in (*RATE_LIMIT_WAITS, None):
        try:
            return llm_gateway.generate(
                session,
                user_id=user_id,
                feature=UsageFeature.SCORE,
                prompt=prompt,
                parse=LLMScoreBatch.model_validate,
                ref_type="job_match_batch",
            )
        except LLMRateLimited:
            if wait is None:
                raise
            time.sleep(wait)
    raise AssertionError("unreachable")  # pragma: no cover


def apply_score(
    match: JobMatch,
    job: Job,
    result: LLMJobScore,
    resume: Resume,
    prefs: FilterPrefs,
    *,
    prompt_ref: str,
    model: str,
) -> None:
    matched, missing = scoring.reconcile_skills(
        result.matched_skills, result.missing_skills, list(resume.skills_index)
    )
    llm_flags = [cast(scoring.RedFlag, f.model_dump()) for f in result.red_flags]
    flags = scoring.merge_flags(
        scoring.deterministic_flags(job, candidate_level(resume), prefs), llm_flags
    )
    outcome = scoring.score(
        result.model_dump(include=set(scoring.LLM_SUBSCORES)),
        scoring.location_fit(job, prefs),
        flags,
    )
    match.breakdown = outcome.breakdown
    match.overall_score = outcome.overall
    match.recommendation = outcome.recommendation
    match.weights_version = scoring.WEIGHTS_VERSION
    match.llm_recommendation = result.apply_recommendation
    match.red_flags = [dict(f) for f in outcome.red_flags]
    match.matched_skills = matched
    match.missing_skills = missing
    match.why_good_fit = result.why_good_fit.strip() or None
    match.prompt_version = prompt_ref
    match.model = model
    match.stage = MatchStage.SCORED
    match.failure_reason = None
    match.scored_at = datetime.now(UTC)


def run_stage2(
    session: Session,
    user_id: uuid.UUID,
    resume: Resume,
    pref: Preference | None,
    pairs: list[tuple[JobMatch, Job]],
    progress: ProgressFn | None = None,
) -> MatchStats:
    stats = MatchStats()
    if not pairs:
        return stats
    spec = load_prompt("match_score", 1)
    prefs = filter_prefs(pref)
    candidate = json.dumps(candidate_payload(resume), ensure_ascii=False)
    preferences = json.dumps(preferences_payload(pref), ensure_ascii=False)

    for start in range(0, len(pairs), BATCH):
        chunk = pairs[start : start + BATCH]
        refs = {f"j{i + 1}": pair for i, pair in enumerate(chunk)}
        prompt = render(
            spec,
            candidate_json=candidate,
            preferences_json=preferences,
            jobs=[
                {"ref": ref, "json": json.dumps(job_payload(job), ensure_ascii=False)}
                for ref, (_, job) in refs.items()
            ],
        )
        try:
            batch, result = _generate(session, user_id, prompt)
        except (LLMQuotaExhausted, LLMNotConfigured, LLMRateLimited, LLMUnavailable) as exc:
            # The provider can't take more work right now: stop, and leave the rest ranked by
            # similarity. They're picked up again on the next search or rescore.
            if isinstance(exc, LLMQuotaExhausted):
                reason = "The AI's free daily limit is used up. Scores resume tomorrow."
            elif isinstance(exc, LLMNotConfigured):
                reason = "The AI isn't set up (GEMINI_API_KEY)."
            elif isinstance(exc, LLMUnavailable):
                reason = "The AI is overloaded right now. Unscored jobs get scored next search."
            else:
                reason = "The AI is busy. Unscored jobs get scored on the next search."
            for match, _ in pairs[start:]:
                match.failure_reason = reason
            stats.stopped = reason
            session.commit()
            log.warning("scoring_stopped", error_code=exc.code)
            return stats
        except LLMError as exc:
            for match, _ in chunk:
                match.stage = MatchStage.SCORE_FAILED
                match.failure_reason = "The AI couldn't score this job. Try again."
            stats.failed += len(chunk)
            session.commit()
            log.warning("scoring_batch_failed", error_code=exc.code, jobs=len(chunk))
            continue

        by_ref = {r.job_ref.strip(): r for r in batch.results}
        for ref, (match, job) in refs.items():
            scored = by_ref.get(ref)
            if scored is None:
                match.stage = MatchStage.SCORE_FAILED
                match.failure_reason = "The AI skipped this job. Try again."
                stats.failed += 1
                continue
            apply_score(match, job, scored, resume, prefs, prompt_ref=spec.ref, model=result.model)
            stats.scored += 1
        session.commit()
        if progress:
            progress(min(start + BATCH, len(pairs)), len(pairs))
    return stats


def refresh_weights(session: Session, user_id: uuid.UUID) -> int:
    """After a weights change, recompute scores from stored breakdowns (no AI calls)."""
    rows = session.scalars(
        select(JobMatch).where(
            JobMatch.user_id == user_id,
            JobMatch.stage == MatchStage.SCORED,
            JobMatch.weights_version != scoring.WEIGHTS_VERSION,
        )
    ).all()
    for match in rows:
        flags = cast(list[scoring.RedFlag], match.red_flags)
        match.overall_score = scoring.overall_score(match.breakdown or {}, flags)
        match.recommendation = scoring.band(match.overall_score, flags)
        match.weights_version = scoring.WEIGHTS_VERSION
    return len(rows)


def match_for_user(
    session: Session,
    user_id: uuid.UUID,
    *,
    job_ids: list[uuid.UUID] | None = None,
    progress: ProgressFn | None = None,
    on_stage2: Callable[[int], None] | None = None,
) -> MatchStats:
    """Stage 1 for every unmatched job, then stage 2 for the best unscored ones."""
    resume = active_resume(session, user_id)
    if resume is None:
        return MatchStats(stopped="Upload a resume to get match scores.")
    refresh_weights(session, user_id)
    pref = session.get(Preference, user_id)
    stats = run_stage1(session, user_id, resume, filter_prefs(pref), job_ids)
    session.commit()

    top_n = (
        pref.stage1_top_n if pref and pref.stage1_top_n else None
    ) or get_settings().stage1_top_n
    pairs = pick_for_scoring(session, user_id, resume, len(job_ids) if job_ids else top_n, job_ids)
    if on_stage2:
        on_stage2(len(pairs))
    scored = run_stage2(session, user_id, resume, pref, pairs, progress)
    stats.scored, stats.failed, stats.stopped = scored.scored, scored.failed, scored.stopped
    log.info(
        "matching_done",
        considered=stats.considered,
        filtered_out=stats.filtered_out,
        scored=stats.scored,
        failed=stats.failed,
    )
    return stats
