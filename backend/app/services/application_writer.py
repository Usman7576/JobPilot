"""Worker-side writing: contact discovery, drafts (email, cover letter, resume tweaks),
length rules, guardrails and the AI fact-check.

The subject line and the signature are built in code; the AI writes only the greeting and
the body, from the fact sheet (never the raw resume).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domain import fact_sheet as facts_mod
from app.domain import guardrails
from app.domain.fact_sheet import FactSheet
from app.domain.guardrails import Flag, Report
from app.models import Application, ApplicationDraft, Job, Resume, User
from app.models.enums import (
    ApplicationChannel,
    ApplicationStatus,
    ContactSource,
    DraftKind,
    EventActor,
    Tone,
    UsageFeature,
)
from app.prompts.registry import load_prompt, render
from app.providers.llm import LLMError
from app.schemas.application import LLMClaims, LLMTweaks, LLMWritten
from app.schemas.profile import ResumeProfile
from app.services import contact_service, llm_gateway
from app.services.application_events import record_event

log = get_logger(__name__)
JOB_TEXT_CHARS = 4000
# (min, max) words for the body; one automatic retry when outside, then trim or warn.
LIMITS: dict[DraftKind, tuple[int, int]] = {
    DraftKind.EMAIL: (60, 150),
    DraftKind.COVER_LETTER: (250, 350),
}
PROMPTS = {
    DraftKind.EMAIL: "application_email",
    DraftKind.COVER_LETTER: "cover_letter",
    DraftKind.RESUME_TWEAKS: "resume_tweaks",
}
SIGN_OFF = {Tone.FORMAL: "Best regards,", Tone.FRIENDLY: "Thanks,", Tone.CONCISE: "Best,"}


@dataclass
class Context:
    application: Application
    job: Job
    resume: Resume
    profile: ResumeProfile
    facts: FactSheet
    user: User

    @property
    def job_text(self) -> str:
        return (self.job.description_text or "")[:JOB_TEXT_CHARS]


def load_context(session: Session, application: Application) -> Context:
    job = session.get(Job, application.job_id)
    resume = session.get(Resume, application.resume_id) if application.resume_id else None
    user = session.get(User, application.user_id)
    if job is None or resume is None or resume.profile is None or user is None:
        raise LookupError("The job or resume for this application is gone.")
    profile = ResumeProfile.model_validate(resume.profile)
    years = float(resume.total_years_experience) if resume.total_years_experience else None
    return Context(application, job, resume, profile, facts_mod.build(profile, years), user)


def subject_for(job: Job, name: str) -> str:
    title = " ".join(job.title.split())[:90]
    return f"Application: {title}, {name}" if name else f"Application: {title}"


def signature_for(ctx: Context, tone: Tone) -> str:
    contact = ctx.profile.contact
    lines = [SIGN_OFF[tone], ctx.profile.name or ctx.user.full_name or ""]
    lines += [v for v in (contact.phone, contact.email or ctx.user.email) if v]
    lines += [link.url for link in contact.links[:2]]
    return "\n".join(line for line in lines if line)


def check(text: str, ctx: Context) -> Report:
    return guardrails.check_text(text, ctx.facts, f"{ctx.job.title}\n{ctx.job_text}")


def _write(
    session: Session, ctx: Context, kind: DraftKind, tone: Tone, instructions: str | None
) -> tuple[LLMWritten, str, list[Flag]]:
    spec = load_prompt(PROMPTS[kind], 1)
    low, high = LIMITS[kind]
    extra = instructions or ""
    model = ""
    for attempt in range(2):
        prompt = render(
            spec,
            fact_sheet=ctx.facts.as_prompt(),
            job_title=ctx.job.title,
            company=ctx.job.company_name,
            location=ctx.job.location_raw or "",
            job_description=ctx.job_text,
            tone=tone.value,
            instructions=extra,
        )
        written, result = llm_gateway.generate(
            session,
            user_id=ctx.user.id,
            feature=UsageFeature.GENERATE,
            prompt=prompt,
            parse=LLMWritten.model_validate,
            ref_type="application",
            ref_id=ctx.application.id,
        )
        model = result.model
        words = guardrails.word_count(written.body)
        if low <= words <= high or attempt == 1:
            break
        extra = (
            f"{instructions or ''}\nYour last draft's body had {words} words. "
            f"It must be between {low} and {high} words."
        ).strip()

    flags: list[Flag] = []
    words = guardrails.word_count(written.body)
    if words > high:
        written.body = guardrails.truncate_words(written.body, high)
        flags.append(
            Flag("", f"Shortened to {high} words. Check it still reads well.", "warn", "length")
        )
    elif words < low:
        flags.append(Flag("", f"Only {words} words; aim for {low}-{high}.", "warn", "length"))
    return written, model, flags


def write_text(
    session: Session, ctx: Context, kind: DraftKind, tone: Tone, instructions: str | None = None
) -> ApplicationDraft:
    written, model, length_flags = _write(session, ctx, kind, tone, instructions)
    greeting = written.greeting.strip()
    body = f"{greeting}\n\n{written.body.strip()}" if greeting else written.body.strip()
    report = check(body, ctx)
    report.flags = length_flags + report.flags
    content: dict[str, Any] = {
        "body": body,
        "signature": signature_for(ctx, tone),
        "refs": {
            "skills_used": written.skills_used,
            "achievement_ref": written.achievement_ref,
            "job_detail": written.job_detail,
        },
    }
    if kind == DraftKind.EMAIL:
        content["subject"] = subject_for(ctx.job, ctx.facts.name)
    return _save_draft(session, ctx.application, kind, tone, content, report, PROMPTS[kind], model)


def write_tweaks(session: Session, ctx: Context, tone: Tone) -> ApplicationDraft:
    spec = load_prompt(PROMPTS[DraftKind.RESUME_TWEAKS], 1)
    prompt = render(
        spec,
        fact_sheet=ctx.facts.as_prompt(),
        job_title=ctx.job.title,
        company=ctx.job.company_name,
        job_description=ctx.job_text,
    )
    tweaks, result = llm_gateway.generate(
        session,
        user_id=ctx.user.id,
        feature=UsageFeature.GENERATE,
        prompt=prompt,
        parse=LLMTweaks.model_validate,
        ref_type="application",
        ref_id=ctx.application.id,
    )
    items: list[dict[str, Any]] = []
    report = Report()
    for t in tweaks.tweaks[:5]:
        original = ctx.facts.bullets.get(t.bullet_id.strip())
        if original is None:
            continue  # must rewrite a real bullet
        items.append(
            {
                "bullet_id": t.bullet_id,
                "original": original,
                "suggested": t.suggested.strip(),
                "rationale": t.rationale.strip(),
                "emphasized_skills": t.emphasized_skills,
            }
        )
        report.flags += check(t.suggested, ctx).flags
    report.verified = True  # each tweak is checked against its own bullet deterministically
    return _save_draft(
        session,
        ctx.application,
        DraftKind.RESUME_TWEAKS,
        tone,
        {"tweaks": items},
        report,
        PROMPTS[DraftKind.RESUME_TWEAKS],
        result.model,
    )


def _save_draft(
    session: Session,
    application: Application,
    kind: DraftKind,
    tone: Tone,
    content: dict[str, Any],
    report: Report,
    prompt_id: str,
    model: str,
) -> ApplicationDraft:
    draft = ApplicationDraft(
        application_id=application.id,
        kind=kind,
        tone=tone,
        content=content,
        guardrail_report=report.to_json(),
        prompt_version=f"{prompt_id}/v1",
        model=model,
    )
    session.add(draft)
    session.flush()
    if kind == DraftKind.EMAIL:
        application.current_draft_id = draft.id
    if report.blocked:
        application.guardrail_flags_acknowledged_at = None
    return draft


def latest_draft(
    session: Session, application_id: uuid.UUID, kind: DraftKind
) -> ApplicationDraft | None:
    draft: ApplicationDraft | None = session.scalar(
        select(ApplicationDraft)
        .where(ApplicationDraft.application_id == application_id, ApplicationDraft.kind == kind)
        .order_by(ApplicationDraft.created_at.desc())
        .limit(1)
    )
    return draft


def verify(session: Session, ctx: Context, drafts: list[ApplicationDraft]) -> bool:
    """One AI fact-check across the email and cover letter. False if the AI didn't answer."""
    texts = {
        d.kind.value: str(d.content.get("body", ""))
        for d in drafts
        if d.kind in (DraftKind.EMAIL, DraftKind.COVER_LETTER)
    }
    if not texts:
        return True
    prompt = render(
        load_prompt("claim_verify", 1),
        fact_sheet=ctx.facts.as_prompt(),
        email=texts.get("email", ""),
        cover_letter=texts.get("cover_letter", ""),
    )
    try:
        claims, _ = llm_gateway.generate(
            session,
            user_id=ctx.user.id,
            feature=UsageFeature.VERIFY,
            prompt=prompt,
            parse=LLMClaims.model_validate,
            ref_type="application",
            ref_id=ctx.application.id,
        )
    except LLMError as exc:
        log.warning("claim_verify_failed", error_code=exc.code)
        return False
    for draft in drafts:
        if draft.kind.value not in texts:
            continue
        report = Report.from_json(draft.guardrail_report)
        report.flags = [f for f in report.flags if f.source != "verifier"]
        mine = [c.model_dump() for c in claims.claims if c.where == draft.kind.value]
        report.flags += guardrails.verifier_flags(mine, ctx.facts)
        report.verified = True
        draft.guardrail_report = report.to_json()
    session.flush()
    return True


def prepare(
    session: Session,
    application_id: uuid.UUID,
    kinds: list[str],
    tone: Tone,
    instructions: str | None = None,
) -> bool:
    """Fill in the contact and write the requested drafts. Ends in READY either way."""
    application = session.get(Application, application_id)
    if application is None or application.status != ApplicationStatus.DRAFTING:
        return False
    try:
        ctx = load_context(session, application)
    except LookupError as exc:
        return _finish(session, application, str(exc))

    if application.email_source != ContactSource.MANUAL:
        contact = contact_service.discover(session, ctx.job)
        application.contact_email = contact.email
        application.email_source = contact.source
        application.email_confidence = contact.confidence
    application.channel = (
        ApplicationChannel.EMAIL if application.contact_email else ApplicationChannel.SITE
    )

    written: list[ApplicationDraft] = []
    try:
        for kind in (DraftKind(k) for k in kinds):
            if kind == DraftKind.RESUME_TWEAKS:
                written.append(write_tweaks(session, ctx, tone))
            else:
                written.append(write_text(session, ctx, kind, tone, instructions))
            session.commit()
    except LLMError as exc:
        session.rollback()
        application = session.get(Application, application_id)
        if application is None:
            return False
        reason = {
            "llm_quota_exhausted": "The AI's free daily limit is used up. Try again tomorrow.",
            "llm_unavailable": "The AI is overloaded right now. Try Regenerate in a few minutes.",
            "llm_rate_limited": "The AI is busy. Try Regenerate in a minute.",
            "llm_not_configured": "The AI isn't set up (check the API key).",
        }.get(exc.code, "The AI couldn't write this draft. Try Regenerate.")
        return _finish(session, application, reason)

    verified = verify(session, ctx, written)
    note = None if verified else "The AI fact-check didn't run. Use Re-check before sending."
    return _finish(session, application, note)


def _finish(session: Session, application: Application, error: str | None) -> bool:
    application.status = ApplicationStatus.READY
    application.last_error = error
    record_event(session, application, ApplicationStatus.READY, EventActor.SYSTEM, error)
    session.commit()
    return error is None


def reverify(session: Session, application_id: uuid.UUID) -> bool:
    application = session.get(Application, application_id)
    if application is None:
        return False
    ctx = load_context(session, application)
    drafts = [
        d
        for kind in (DraftKind.EMAIL, DraftKind.COVER_LETTER)
        if (d := latest_draft(session, application.id, kind)) is not None
    ]
    ok = verify(session, ctx, drafts)
    application.last_error = None if ok else "The AI fact-check didn't run. Try again later."
    application.updated_at = datetime.now(UTC)
    session.commit()
    return ok
