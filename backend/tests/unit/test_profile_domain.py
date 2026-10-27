from __future__ import annotations

from datetime import date

from app.domain.experience import professional_years, seniority_from_years
from app.domain.profile import embedding_text, finalize_profile
from app.domain.skills import canonical_skill, unique_skills
from app.models.enums import Seniority
from app.schemas.profile import ResumeProfile, WorkEntry
from tests.fixtures import parsed_resume_json

TODAY = date(2026, 10, 1)


def job(title: str, start: str | None, end: str | None) -> WorkEntry:
    return WorkEntry(title=title, company="X", start=start, end=end)


def test_canonical_skills() -> None:
    assert canonical_skill("js") == "JavaScript"
    assert canonical_skill(" postgres ") == "PostgreSQL"
    assert canonical_skill("K8S") == "Kubernetes"
    assert canonical_skill("prompt engineering") == "Prompt engineering"
    assert canonical_skill("SvelteKit") == "SvelteKit"
    assert unique_skills(["React", "reactjs", "React.js", "Vue"]) == ["React", "Vue.js"]


def test_years_merge_overlaps_and_skip_internships() -> None:
    work = [
        job("Engineer", "2020-01", "2021-12"),  # 24 months
        job("Freelance Dev", "2021-06", "2022-05"),  # overlaps; adds 5 months
        job("Software Intern", "2018-01", "2019-12"),  # ignored
    ]
    assert professional_years(work, TODAY) == round(29 / 12, 1)


def test_years_present_and_bare_years() -> None:
    assert professional_years([job("Dev", "2024", "present")], TODAY) == round(34 / 12, 1)
    assert professional_years([job("Dev", None, None)], TODAY) is None
    assert professional_years([], TODAY) is None


def test_seniority_bands() -> None:
    assert seniority_from_years(0.5) == Seniority.JUNIOR
    assert seniority_from_years(4) == Seniority.MID
    assert seniority_from_years(7) == Seniority.SENIOR
    assert seniority_from_years(12) == Seniority.STAFF
    assert seniority_from_years(None) is None


def test_finalize_profile_trusts_dates_over_llm_and_merges_skills() -> None:
    profile = ResumeProfile.model_validate(parsed_resume_json())
    final, derived = finalize_profile(profile, TODAY)

    # 2018-06..2026-10 continuous (intern excluded) = 101 months, not the LLM's 9 years.
    assert derived.total_years_experience == round(101 / 12, 1)
    names = [s.name for s in final.skills]
    assert names.count("Python") == 1
    assert {"Kubernetes", "JavaScript", "PostgreSQL"} <= set(names)
    python = next(s for s in final.skills if s.name == "Python")
    assert python.proficiency == "expert"  # highest of the duplicates wins
    assert derived.seniority == Seniority.SENIOR  # from the parser


def test_profile_schema_tolerates_messy_llm_output() -> None:
    profile = ResumeProfile.model_validate(
        parsed_resume_json(
            seniority="unknown",
            work_history=[
                {"title": "Dev", "company": "Y", "start": "March 2020", "end": "Current"}
            ],
            unexpected_field="ignored",
        )
    )
    assert profile.seniority is None
    assert profile.work_history[0].start is None  # not YYYY-MM
    assert profile.work_history[0].end == "present"


def test_embedding_text_mentions_roles_skills_and_recent_work() -> None:
    text = embedding_text(ResumeProfile.model_validate(parsed_resume_json()))
    assert "Backend Engineer" in text
    assert "FastAPI" in text
    assert "Analytical Engines Ltd" in text
    assert "ada@example.com" not in text  # contact details aren't embedded
