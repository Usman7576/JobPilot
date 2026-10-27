from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import Preference, User
from app.models.enums import OnboardingStep
from app.providers.sources import all_sources, default_source_names
from app.schemas.preference import PreferencesIn, PreferencesOut, SourceOut
from app.services import source_guard


class UnknownSource(AppError):
    status_code, code, title = 422, "unknown_source", "Unknown job source"


def _to_out(pref: Preference | None, defaults: dict[str, Any]) -> PreferencesOut:
    if pref is None:
        return PreferencesOut(**defaults, is_saved=False)
    return PreferencesOut(
        target_titles=pref.target_titles,
        locations=pref.locations,
        remote_types=pref.remote_types,
        experience_levels=pref.experience_levels,
        salary_min=pref.salary_min,
        salary_currency=pref.salary_currency,
        include_keywords=pref.include_keywords,
        exclude_keywords=pref.exclude_keywords,
        exclude_companies=pref.exclude_companies,
        sources=pref.sources,
        posted_within_days=pref.posted_within_days,
        results_per_source=pref.results_per_source,
        daily_search_enabled=pref.daily_search_enabled,
        daily_search_hour=pref.daily_search_hour,
        digest_enabled=pref.digest_enabled,
        digest_min_score=pref.digest_min_score,
        is_saved=True,
    )


def default_preferences(preferred_roles: list[str]) -> dict[str, Any]:
    """Sensible first-time defaults; target titles come from the parsed resume."""
    return {
        "target_titles": preferred_roles[:5],
        "remote_types": ["remote", "hybrid", "onsite"],
        "sources": default_source_names(),
    }


async def get(db: AsyncSession, user: User, preferred_roles: list[str]) -> PreferencesOut:
    pref = await db.get(Preference, user.id)
    return _to_out(pref, default_preferences(preferred_roles))


async def save(db: AsyncSession, user: User, data: PreferencesIn) -> PreferencesOut:
    known = all_sources()
    unknown = [s for s in data.sources if s not in known]
    if unknown:
        raise UnknownSource(f"Unknown source(s): {', '.join(unknown)}")

    values = data.model_dump(mode="json")
    pref = await db.get(Preference, user.id)
    if pref is None:
        pref = Preference(user_id=user.id, **values)
        db.add(pref)
    else:
        for field, value in values.items():
            setattr(pref, field, value)
    # Gmail/Sheets connection is optional and arrives in later phases.
    if user.onboarding_step in (
        OnboardingStep.RESUME,
        OnboardingStep.PROFILE,
        OnboardingStep.PREFERENCES,
    ):
        user.onboarding_step = OnboardingStep.DONE
    await db.commit()
    await db.refresh(pref)
    return _to_out(pref, {})


def list_sources() -> list[SourceOut]:
    return [
        SourceOut(
            name=name,
            label=src.info.label,
            kind=src.info.kind,
            default_on=src.info.default_on,
            requires_key=src.info.requires_key,
            configured=src.is_configured(),
            paused_seconds=source_guard.paused_for(name),
            note=src.info.note,
        )
        for name, src in all_sources().items()
    ]
