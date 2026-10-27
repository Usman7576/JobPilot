from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

from app.domain import fact_sheet, guardrails
from app.domain.contacts import company_domain, pick_best_email
from app.integrations import gmail
from app.prompts.registry import load_prompt, render
from app.providers.llm import LLMUnavailable
from app.providers.llm.anthropic import API_URL, AnthropicProvider
from app.schemas.profile import ResumeProfile
from tests.fixtures import parsed_resume_json


@pytest.fixture
def facts() -> fact_sheet.FactSheet:
    profile = ResumeProfile.model_validate(parsed_resume_json())
    return fact_sheet.build(profile, years=5.6)


JOB = "Backend Engineer. We use Python, FastAPI and Kafka. Team of 12 engineers."


def test_fact_sheet_lists_facts_without_contact_details(facts: fact_sheet.FactSheet) -> None:
    text = facts.as_prompt()
    assert "[b1] (Analytical Engines Ltd) Built FastAPI services" in text
    assert "ada@example.com" not in text and "555" not in text
    assert facts.bullets["b1"].startswith("Built FastAPI services")
    assert {"2m", "5.6", "5", "6"} <= facts.numbers  # "about 5 or 6 years" are both fine
    assert facts.first_name == "Ada"


def test_numbers_must_come_from_the_resume_or_the_job(facts: fact_sheet.FactSheet) -> None:
    ok = "I built FastAPI services handling 2M requests a day, and your team of 12 sounds great."
    assert guardrails.check_text(ok, facts, JOB).flags == []
    bad = guardrails.check_text("I cut costs by 40% and handled 5 million users.", facts, JOB)
    assert bad.blocked
    assert {f.text for f in bad.flags if f.source == "numbers"} == {"40%", "5m"}


def test_skills_not_on_the_resume(facts: fact_sheet.FactSheet) -> None:
    report = guardrails.check_text("My Rust and Kafka experience is deep.", facts, JOB)
    by_skill = {f.text: f.severity for f in report.flags}
    assert by_skill == {"Rust": "block", "Kafka": "warn"}  # Kafka is from the job post


def test_degrees_and_certifications(facts: fact_sheet.FactSheet) -> None:
    report = guardrails.check_text("I hold a PhD and I am AWS certified.", facts, JOB)
    sources = {f.source: f.severity for f in report.flags}
    assert sources["degrees"] == "block"
    assert sources["certifications"] == "warn"


def test_verifier_flags_only_unsupported_claims(facts: fact_sheet.FactSheet) -> None:
    claims = [
        {"claim": "Built FastAPI services at scale", "supporting_quote": "Built FastAPI services handling 2M requests per day"},
        {"claim": "Led a team of 20", "supporting_quote": ""},
        {"claim": "Managed budgets", "supporting_quote": "Managed a $5M budget"},
    ]  # fmt: skip
    flags = guardrails.verifier_flags(claims, facts)
    assert [f.text for f in flags] == ["Led a team of 20", "Managed budgets"]
    assert all(f.severity == "warn" for f in flags)


def test_word_limits() -> None:
    text = "First sentence here. Second one too.\n\nThird paragraph sentence. Fourth."
    assert guardrails.word_count(text) == 10
    assert (
        guardrails.truncate_words(text, 9)
        == "First sentence here. Second one too.\n\nThird paragraph sentence."
    )
    assert guardrails.truncate_words("one two three four", 2) == "one two"


def test_report_round_trip() -> None:
    report = guardrails.Report([guardrails.Flag("x", "why", "block", "numbers")], verified=True)
    again = guardrails.Report.from_json(report.to_json())
    assert again.blocked and again.verified and again.flags[0].text == "x"


def test_pick_best_email_and_company_domain() -> None:
    assert (
        pick_best_email(["info@acme.com", "jane.doe@acme.com", "careers@acme.com"])
        == "careers@acme.com"
    )
    assert pick_best_email(["info@acme.com", "jane@acme.com"]) == "jane@acme.com"
    assert pick_best_email([]) is None
    assert (
        company_domain("https://boards.greenhouse.io/acme/1", "https://jobs.acme.co.uk/x")
        == "acme.co.uk"
    )
    assert company_domain("https://careers.acme.com/jobs/2") == "acme.com"
    assert company_domain("https://www.linkedin.com/jobs/view/1") is None


def test_gmail_consent_asks_only_to_send() -> None:
    url = gmail.consent_url("state123", "challenge", login_hint="ada@example.com")
    q = parse_qs(urlparse(url).query)
    assert q["scope"] == ["openid email https://www.googleapis.com/auth/gmail.send"]
    assert q["access_type"] == ["offline"] and q["prompt"] == ["consent"]
    assert q["redirect_uri"] == ["http://localhost:3000/api/v1/integrations/gmail/callback"]
    assert q["login_hint"] == ["ada@example.com"]


def _prompt() -> Any:
    return render(load_prompt("claim_verify", 1), fact_sheet="x", email="hi", cover_letter="")


@respx.mock
def test_claude_returns_the_tool_input_as_json() -> None:
    route = respx.post(API_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "content": [{"type": "tool_use", "name": "respond", "input": {"claims": []}}],
                "usage": {"input_tokens": 10, "output_tokens": 3},
            },
        )
    )
    result = AnthropicProvider("k", "claude-sonnet-5-5", "claude-haiku-5-5").generate_json(
        _prompt(), schema={"type": "object"}, tier="fast"
    )
    assert result.data == {"claims": []} and result.model == "claude-haiku-5-5"
    sent = route.calls[0].request
    assert sent.headers["x-api-key"] == "k"
    assert b'"tool_choice":{"type":"tool","name":"respond"}' in sent.content.replace(b" ", b"")


@respx.mock
def test_claude_overloaded_is_unavailable() -> None:
    respx.post(API_URL).mock(return_value=httpx.Response(529, json={}))
    with pytest.raises(LLMUnavailable):
        AnthropicProvider("k", "s", "f").generate_json(_prompt(), schema={}, tier="smart")


@pytest.mark.parametrize(
    ("text", "families"),
    [
        ("I would be glad to help", set()),
        ("eager to master Kafka", set()),
        ("strong MS Office skills", set()),
        ("I hold a B.E. in CS", {"bachelor"}),
        ("BS Computer Science", {"bachelor"}),
        ("Master of Science", {"master"}),
        ("an MSc in AI", {"master"}),
        ("a PhD and an MBA", {"phd", "mba"}),
    ],
)
def test_degree_mentions(text: str, families: set[str]) -> None:
    assert fact_sheet.degrees_in(text) == families
