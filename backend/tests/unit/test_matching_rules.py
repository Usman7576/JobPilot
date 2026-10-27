from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.domain import scoring
from app.domain.filters import (
    CandidateLevel,
    FilterPrefs,
    hard_filter_reasons,
    location_matches,
)
from app.models.enums import Recommendation, RemoteType, SalaryPeriod, Seniority


@dataclass
class FakeJob:
    title: str = "Backend Engineer"
    company_name: str = "Acme Inc"
    description_text: str | None = "Python, FastAPI and PostgreSQL."
    remote_type: RemoteType = RemoteType.ONSITE
    location_raw: str | None = "Lahore, Pakistan"
    seniority: Seniority | None = None
    min_years_experience: Decimal | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    salary_period: SalaryPeriod | None = None
    posted_at: datetime | None = None


LEVEL = CandidateLevel(years=4.0, seniority=Seniority.MID)
LAHORE = FilterPrefs(locations=[{"city": "Lahore", "country": "pk"}])


def reasons(job: FakeJob, prefs: FilterPrefs = LAHORE, level: CandidateLevel = LEVEL) -> list[str]:
    return hard_filter_reasons(job, prefs, level)


def test_a_good_job_passes() -> None:
    assert reasons(FakeJob()) == []
    # Unknown data never filters: no location, no salary, no seniority.
    assert reasons(FakeJob(location_raw=None, remote_type=RemoteType.UNKNOWN)) == []


def test_company_and_keyword_filters() -> None:
    prefs = FilterPrefs(
        exclude_companies=["ACME"], exclude_keywords=["php"], include_keywords=["django"]
    )
    assert reasons(FakeJob(company_name="Acme, Inc."), prefs) == [
        "excluded_company",
        "missing_include_keyword",
    ]
    job = FakeJob(company_name="Other", description_text="We use PHP and Django")
    assert reasons(job, prefs) == ["excluded_keyword"]
    # Whole words only: "graphql" doesn't contain the keyword "php".
    assert reasons(FakeJob(company_name="Other", description_text="GraphQL Django"), prefs) == []


def test_remote_and_location_filters() -> None:
    remote_only = FilterPrefs(remote_types=["remote"], locations=LAHORE.locations)
    assert reasons(FakeJob(), remote_only) == ["remote_mismatch"]
    assert reasons(FakeJob(remote_type=RemoteType.REMOTE, location_raw="USA"), remote_only) == []
    assert reasons(FakeJob(location_raw="Berlin, Germany")) == ["location_mismatch"]
    assert reasons(FakeJob(location_raw="Karachi, Pakistan")) == ["location_mismatch"]
    by_country = FilterPrefs(locations=[{"country": "pk"}])
    assert reasons(FakeJob(location_raw="Karachi, Pakistan"), by_country) == []


def test_location_matching_understands_country_names() -> None:
    assert location_matches("Austin, TX, USA", {"country": "us"})
    assert location_matches("London, United Kingdom", {"country": "gb"})
    assert location_matches("Remote - UK", {"country": "gb"})
    assert not location_matches("Paris, France", {"country": "de"})
    assert not location_matches("Lahore", {"city": "Karachi", "country": "pk"})


def test_seniority_salary_and_stale_filters() -> None:
    junior = CandidateLevel(years=1.0, seniority=Seniority.JUNIOR)
    assert reasons(FakeJob(seniority=Seniority.STAFF), level=junior) == ["seniority_gap"]
    assert reasons(FakeJob(seniority=Seniority.SENIOR), level=junior) == []
    assert reasons(FakeJob(min_years_experience=Decimal(5)), level=junior) == ["seniority_gap"]
    # Internships never count as a gap for experienced people.
    assert reasons(FakeJob(seniority=Seniority.INTERN)) == []

    floor = FilterPrefs(salary_min=60_000, salary_currency="USD")
    assert reasons(FakeJob(location_raw=None, salary_max=50_000), floor) == ["salary_below_floor"]
    monthly = FakeJob(location_raw=None, salary_max=6_000, salary_period=SalaryPeriod.MONTH)
    assert reasons(monthly, floor) == []  # 72k a year
    other_currency = FakeJob(location_raw=None, salary_max=50_000, salary_currency="EUR")
    assert reasons(other_currency, floor) == []

    old = FakeJob(posted_at=datetime.now(UTC) - timedelta(days=40))
    assert reasons(old) == ["stale"]


def test_overall_score_is_computed_in_code() -> None:
    llm = {"skills_match": 90, "experience_match": 80, "seniority_fit": 70, "domain_relevance": 60}
    result = scoring.score({**llm, "overall_score": 5}, loc_fit=100, flags=[])
    # 90*.35 + 80*.25 + 70*.15 + 60*.15 + 100*.10 = 81
    assert result.overall == 81
    assert result.recommendation == Recommendation.STRONG_APPLY
    assert result.breakdown["location_fit"] == 100
    clamped = scoring.score({k: 150 for k in llm}, loc_fit=-20, flags=[])
    assert clamped.breakdown["skills_match"] == 100 and clamped.breakdown["location_fit"] == 0


def test_red_flags_penalize_and_blockers_cap() -> None:
    llm = {"skills_match": 90, "experience_match": 90, "seniority_fit": 90, "domain_relevance": 90}
    high: scoring.RedFlag = {"code": "x", "message": "", "severity": "high"}
    many = [{**high, "code": f"f{i}"} for i in range(5)]
    assert scoring.score(llm, 90, many).overall == 90 - 15  # penalty capped
    blocker: scoring.RedFlag = {"code": "clearance_required", "message": "", "severity": "low"}
    capped = scoring.score(llm, 90, [blocker])
    assert capped.overall == 90 and capped.recommendation == Recommendation.STRETCH


@pytest.mark.parametrize(
    ("overall", "expected"),
    [
        (80, Recommendation.STRONG_APPLY),
        (79, Recommendation.APPLY),
        (65, Recommendation.APPLY),
        (64, Recommendation.STRETCH),
        (50, Recommendation.STRETCH),
        (49, Recommendation.SKIP),
    ],
)
def test_bands(overall: int, expected: Recommendation) -> None:
    assert scoring.band(overall, []) == expected


def test_deterministic_flags() -> None:
    job = FakeJob(
        min_years_experience=Decimal(8),
        seniority=Seniority.STAFF,
        description_text="Active security clearance required. We do not sponsor visas.",
    )
    codes = {f["code"]: f["severity"] for f in scoring.deterministic_flags(job, LEVEL, LAHORE)}
    assert codes == {
        "experience_gap": "high",
        "seniority_gap": "medium",
        "clearance_required": "high",
        "no_visa_sponsorship": "low",
    }


def test_merge_flags_dedupes_code_flags_first() -> None:
    mine: scoring.RedFlag = {"code": "experience_gap", "message": "code", "severity": "high"}
    llm: scoring.RedFlag = {"code": "Experience Gap", "message": "llm", "severity": "low"}
    merged = scoring.merge_flags([mine], [llm])
    assert merged == [mine]


def test_location_fit() -> None:
    prefs = FilterPrefs(remote_types=["remote", "onsite"], locations=LAHORE.locations)
    assert scoring.location_fit(FakeJob(remote_type=RemoteType.REMOTE), prefs) == 100
    assert scoring.location_fit(FakeJob(), prefs) == 100
    assert scoring.location_fit(FakeJob(location_raw="Karachi, Pakistan"), prefs) == 75
    assert scoring.location_fit(FakeJob(location_raw="Berlin, Germany"), prefs) == 30
    onsite_only = FilterPrefs(remote_types=["onsite"])
    assert scoring.location_fit(FakeJob(remote_type=RemoteType.REMOTE), onsite_only) == 50


def test_reconcile_skills_trusts_only_the_resume() -> None:
    resume = ["Python", "PostgreSQL", "FastAPI"]
    matched, missing = scoring.reconcile_skills(
        ["python", "Postgres", "Kubernetes"], ["Go", "FastAPI", "Kubernetes"], resume
    )
    assert matched == ["Python", "PostgreSQL"]
    assert missing == ["Kubernetes", "Go"]  # claimed-but-absent moves to missing, no overlap
