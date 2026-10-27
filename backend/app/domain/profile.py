"""Post-processing shared by parsing and user edits: canonical skills, years, seniority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.domain.experience import professional_years, reconcile_years, seniority_from_years
from app.domain.skills import canonical_skill
from app.models.enums import Seniority
from app.schemas.profile import ResumeProfile, Skill

_PROFICIENCY_RANK = {"beginner": 0, "intermediate": 1, "advanced": 2, "expert": 3}


@dataclass(frozen=True)
class DerivedFields:
    skills_index: list[str]
    total_years_experience: float | None
    seniority: Seniority | None


def merge_skills(skills: list[Skill]) -> list[Skill]:
    """Canonicalize names and merge duplicates, keeping the highest proficiency."""
    merged: dict[str, Skill] = {}
    for skill in skills:
        name = canonical_skill(skill.name)
        if not name:
            continue
        candidate = skill.model_copy(update={"name": name})
        existing = merged.get(name.lower())
        if existing is None or (
            _PROFICIENCY_RANK[candidate.proficiency] > _PROFICIENCY_RANK[existing.proficiency]
        ):
            merged[name.lower()] = candidate
    return list(merged.values())


def finalize_profile(
    profile: ResumeProfile, today: date | None = None
) -> tuple[ResumeProfile, DerivedFields]:
    skills = merge_skills(profile.skills)
    years = reconcile_years(
        professional_years(profile.work_history, today), profile.total_years_experience
    )
    seniority = profile.seniority or seniority_from_years(years)
    final = profile.model_copy(
        update={"skills": skills, "total_years_experience": years, "seniority": seniority}
    )
    return final, DerivedFields(
        skills_index=[s.name for s in skills],
        total_years_experience=years,
        seniority=seniority,
    )


def embedding_text(profile: ResumeProfile) -> str:
    """What the resume embedding represents: target roles, summary, skills, recent work."""
    parts: list[str] = []
    if profile.preferred_roles:
        parts.append("Target roles: " + ", ".join(profile.preferred_roles))
    if profile.summary:
        parts.append(profile.summary)
    if profile.skills:
        parts.append("Skills: " + ", ".join(s.name for s in profile.skills[:30]))
    for job in profile.work_history[:3]:
        parts.append(f"{job.title} at {job.company}. " + " ".join(job.bullets[:6]))
    return "\n".join(parts)[:6000]
