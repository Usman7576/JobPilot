"""Stage-2 scoring rules. The LLM rates sub-scores; the overall score, location fit, red
flags and the final recommendation are all decided here, deterministically."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal, TypedDict

from app.domain.filters import SENIORITY_RANK, CandidateLevel, FilterPrefs, JobLike
from app.domain.filters import location_matches as _location_matches
from app.domain.skills import canonical_skill
from app.models.enums import Recommendation, RemoteType

WEIGHTS_VERSION = "w1"
WEIGHTS: dict[str, float] = {
    "skills_match": 0.35,
    "experience_match": 0.25,
    "seniority_fit": 0.15,
    "domain_relevance": 0.15,
    "location_fit": 0.10,
}
LLM_SUBSCORES = ("skills_match", "experience_match", "seniority_fit", "domain_relevance")
SEVERITY_PENALTY = {"high": 5, "medium": 2, "low": 0}
MAX_PENALTY = 15
# Flags that make a job a long shot whatever the score: at best "stretch".
BLOCKERS = {"clearance_required", "citizenship_required"}

Severity = Literal["low", "medium", "high"]


class RedFlag(TypedDict):
    code: str
    message: str
    severity: Severity


@dataclass(frozen=True)
class ScoreResult:
    breakdown: dict[str, int]
    overall: int
    recommendation: Recommendation
    red_flags: list[RedFlag]


def clamp(value: float, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, round(value)))


def location_fit(job: JobLike, prefs: FilterPrefs) -> int:
    """How well the job's place suits the user, from preferences (never from the LLM)."""
    wants = set(prefs.remote_types)
    if job.remote_type == RemoteType.REMOTE:
        return 100 if not wants or "remote" in wants else 50
    if not prefs.locations or not job.location_raw:
        return 70  # unknown: neutral-ish
    for loc in prefs.locations:
        if (loc.get("city") or loc.get("region")) and _location_matches(job.location_raw, loc):
            return 100
    country_only = [{"country": loc["country"]} for loc in prefs.locations if loc.get("country")]
    if any(_location_matches(job.location_raw, loc) for loc in country_only):
        return 75
    return 30


_CLEARANCE = re.compile(r"\bsecurity clearance\b|\b(?:ts/sci|top secret)\b", re.I)
_CITIZEN = re.compile(
    r"\bmust be an? (?:u\.?s\.? |us |eu |uk )?citizens?\b|\bcitizenship (?:is )?required\b", re.I
)
_NO_SPONSOR = re.compile(
    r"\b(?:no|not|unable to|cannot|can't|won't|will not) (?:provide |offer )?"
    r"(?:visa )?sponsor(?:ship)?\b",
    re.I,
)


def deterministic_flags(job: JobLike, level: CandidateLevel, prefs: FilterPrefs) -> list[RedFlag]:
    flags: list[RedFlag] = []
    text = f"{job.title}\n{job.description_text or ''}"
    if job.min_years_experience is not None and level.years is not None:
        gap = float(job.min_years_experience) - level.years
        if gap >= 2:
            flags.append(
                {
                    "code": "experience_gap",
                    "message": f"Asks for {job.min_years_experience:g}+ years; "
                    f"you have about {level.years:g}.",
                    "severity": "high" if gap >= 4 else "medium",
                }
            )
    if (
        job.seniority
        and level.seniority
        and SENIORITY_RANK[job.seniority] - SENIORITY_RANK[level.seniority] >= 2
    ):
        flags.append(
            {
                "code": "seniority_gap",
                "message": f"A {job.seniority.value} role; your level is {level.seniority.value}.",
                "severity": "medium",
            }
        )
    if prefs.salary_min and job.salary_max and job.salary_max < prefs.salary_min:
        flags.append(
            {
                "code": "salary_below_floor",
                "message": "Listed pay is below your minimum.",
                "severity": "medium",
            }
        )
    if _CLEARANCE.search(text):
        flags.append(
            {
                "code": "clearance_required",
                "message": "Requires a security clearance.",
                "severity": "high",
            }
        )
    if _CITIZEN.search(text):
        flags.append(
            {
                "code": "citizenship_required",
                "message": "Requires a specific citizenship.",
                "severity": "high",
            }
        )
    if _NO_SPONSOR.search(text):
        flags.append(
            {
                "code": "no_visa_sponsorship",
                "message": "No visa sponsorship offered.",
                "severity": "low",
            }
        )
    return flags


def merge_flags(*groups: list[RedFlag]) -> list[RedFlag]:
    """Code flags come first and win over LLM flags with the same code."""
    merged: dict[str, RedFlag] = {}
    for group in groups:
        for flag in group:
            code = re.sub(r"[^a-z0-9_]", "_", flag["code"].lower())[:40] or "other"
            merged.setdefault(code, {**flag, "code": code})
    return list(merged.values())[:8]


def band(overall: int, flags: list[RedFlag]) -> Recommendation:
    if overall >= 80:
        rec = Recommendation.STRONG_APPLY
    elif overall >= 65:
        rec = Recommendation.APPLY
    elif overall >= 50:
        rec = Recommendation.STRETCH
    else:
        rec = Recommendation.SKIP
    if any(f["code"] in BLOCKERS for f in flags) and rec in (
        Recommendation.STRONG_APPLY,
        Recommendation.APPLY,
    ):
        rec = Recommendation.STRETCH
    return rec


def overall_score(breakdown: dict[str, int], flags: list[RedFlag]) -> int:
    base = sum(breakdown.get(k, 0) * w for k, w in WEIGHTS.items())
    penalty = min(MAX_PENALTY, sum(SEVERITY_PENALTY[f["severity"]] for f in flags))
    return clamp(base - penalty)


def score(llm_subscores: dict[str, float], loc_fit: int, flags: list[RedFlag]) -> ScoreResult:
    breakdown = {k: clamp(llm_subscores.get(k, 0)) for k in LLM_SUBSCORES}
    breakdown["location_fit"] = clamp(loc_fit)
    overall = overall_score(breakdown, flags)
    return ScoreResult(breakdown, overall, band(overall, flags), flags)


def _same_skill(a: str, b: str) -> bool:
    ca, cb = canonical_skill(a).lower(), canonical_skill(b).lower()
    return ca == cb or SequenceMatcher(None, ca, cb).ratio() >= 0.9


def reconcile_skills(
    matched: list[str], missing: list[str], resume_skills: list[str]
) -> tuple[list[str], list[str]]:
    """Matched skills must really be on the resume (else they're missing); no overlap."""
    real: list[str] = []
    gaps: list[str] = []
    for skill in matched:
        owned = next((s for s in resume_skills if _same_skill(skill, s)), None)
        (real if owned else gaps).append(owned or canonical_skill(skill))
    for skill in missing:
        if not any(_same_skill(skill, s) for s in resume_skills):
            gaps.append(canonical_skill(skill))
    real = list(dict.fromkeys(real))[:20]
    gaps = [g for g in dict.fromkeys(gaps) if not any(_same_skill(g, r) for r in real)][:20]
    return real, gaps
