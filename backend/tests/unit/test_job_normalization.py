from __future__ import annotations

from app.domain import dedupe, extraction_rules
from app.domain.html_text import clean_description
from app.domain.normalize import normalize
from app.models.enums import EmploymentType, RemoteType, SalaryPeriod, Seniority
from app.providers.sources import RawJob

DASH = chr(0x2013)


def test_company_and_title_normalization() -> None:
    assert dedupe.normalize_company("Acme, Inc.") == "acme"
    assert dedupe.normalize_company("ACME GmbH") == "acme"
    assert dedupe.normalize_company("The Acme Company Ltd") == "acme"
    assert (
        dedupe.normalize_title("Sr. Software Engr (Remote) [REQ-1234]")
        == "senior software engineer"
    )
    assert dedupe.normalize_title("Python Dev (m/w/d)") == "python developer"
    # Distinct specialisations stay distinct.
    assert dedupe.normalize_title("Engineer - Backend") != dedupe.normalize_title(
        "Engineer - Frontend"
    )


def test_same_job_on_two_boards_shares_a_dedupe_hash() -> None:
    a = dedupe.dedupe_hash("Acme Inc", "Sr. Python Developer", "Berlin, Germany", False)
    b = dedupe.dedupe_hash("ACME", "Senior Python Developer (m/w/d)", "Berlin", False)
    c = dedupe.dedupe_hash("Acme", "Senior Python Developer", "Munich, Germany", False)
    assert a == b
    assert a != c


def test_canonical_url_drops_tracking() -> None:
    a = dedupe.canonical_url("https://www.Indeed.com/viewjob?jk=abc123&utm_source=x&from=serp")
    b = dedupe.canonical_url("https://indeed.com/viewjob/?from=other&jk=abc123")
    assert a == b == "https://indeed.com/viewjob?jk=abc123"


def test_salary_parsing() -> None:
    s = extraction_rules.parse_salary(f"Salary: $120,000 {DASH} $150,000 per year")
    assert s is not None and (s.min, s.max, s.currency, s.period) == (
        120000,
        150000,
        "USD",
        SalaryPeriod.YEAR,
    )
    s = extraction_rules.parse_salary("€55k-70k")
    assert s is not None and (s.min, s.max, s.currency) == (55000, 70000, "EUR")
    s = extraction_rules.parse_salary("$40 - $55 per hour")
    assert s is not None and s.period == SalaryPeriod.HOUR
    # Not salaries.
    assert extraction_rules.parse_salary("3-5 years of experience") is None
    assert extraction_rules.parse_salary("teams of 10-20 people") is None


def test_years_seniority_remote_employment() -> None:
    assert extraction_rules.extract_min_years("At least 5+ years of Python experience") == 5.0
    assert extraction_rules.extract_min_years(f"3{DASH}5 years professional experience") == 3.0
    assert extraction_rules.extract_min_years("We were founded 12 years ago") is None
    assert extraction_rules.seniority_from_title("Sr. Backend Engineer") == Seniority.SENIOR
    assert extraction_rules.seniority_from_title("Junior Data Analyst") == Seniority.JUNIOR
    assert extraction_rules.seniority_from_title("Head of Engineering") == Seniority.DIRECTOR
    assert extraction_rules.seniority_from_title("Software Engineer") is None
    detect = extraction_rules.detect_remote
    assert detect("Engineer (Remote)", None, "", None) == RemoteType.REMOTE
    assert (
        detect("Engineer", "London", "Hybrid: 3 days a week in the office", None)
        == RemoteType.HYBRID
    )
    assert detect("Engineer", "London", "This is an on-site role", None) == RemoteType.ONSITE
    assert detect("Engineer", "London", "", None) == RemoteType.UNKNOWN
    assert extraction_rules.detect_employment("fulltime", "Dev") == EmploymentType.FULL_TIME
    assert extraction_rules.detect_employment(None, "Data Intern") == EmploymentType.INTERNSHIP


def test_emails_and_skills() -> None:
    text = "Send CV to Jobs@Acme.example or noreply@acme.example. Logo: x@2x.png"
    assert extraction_rules.extract_emails(text) == ["jobs@acme.example"]
    skills = extraction_rules.extract_skills(
        "We build with Python, FastAPI, k8s and PostgreSQL. Ready to go? Our REST team ships."
    )
    assert {"Python", "FastAPI", "Kubernetes", "PostgreSQL"} <= set(skills)
    assert "Go" not in skills  # plain word "go" isn't a skill
    assert "REST APIs" not in skills


def test_clean_description_strips_markup_and_scripts() -> None:
    html = "<h2>About</h2><p>We use <b>Python</b>&nbsp;daily.</p><ul><li>AWS</li></ul><script>x()</script>"
    text = clean_description(html, True)
    assert text is not None
    assert "x()" not in text and "<" not in text
    assert "We use Python daily." in text and "- AWS" in text
    assert clean_description("**Bold** and [link](http://x)", False) == "Bold and link"
    assert clean_description(None, True) is None
    # Some feeds escape their HTML twice.
    double = "&lt;p&gt;Join us.&lt;/p&gt;&lt;p&gt;&amp;nbsp;&lt;/p&gt;&lt;p&gt;Python &amp;amp; Go&lt;/p&gt;"
    assert clean_description(double, True) == "Join us.\n\nPython & Go"


def test_normalize_end_to_end() -> None:
    raw = RawJob(
        source="adzuna",
        source_job_id="42",
        url="https://adzuna.example/jobs/42?utm=1",
        title="  Senior   Python Developer (Remote) ",
        company="Acme Inc.",
        location="Berlin, Germany",
        description="<p>5+ years of experience with Python and Django. €70k-90k</p>",
        description_is_html=True,
        tags=["fastapi"],
        emails=["HR@Acme.example"],
    )
    job = normalize(raw)
    assert job.title == "Senior Python Developer (Remote)"
    assert job.remote_type == RemoteType.REMOTE
    assert job.seniority == Seniority.SENIOR
    assert float(job.min_years_experience or 0) == 5.0
    assert (job.salary_min, job.salary_max, job.salary_currency) == (70000, 90000, "EUR")
    assert {"Python", "Django", "FastAPI"} <= set(job.required_skills)
    assert job.contact_emails == ["hr@acme.example"]
    assert job.location == {"city": "Berlin", "country": "Germany"}
    assert job.normalized_company == "acme"
