"""Rule-based field extraction from job text. Cheap, deterministic, and runs before any LLM."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.skills import _ALIASES, canonical_skill
from app.models.enums import EmploymentType, PayStatus, RemoteType, SalaryPeriod, Seniority

# --- Emails -------------------------------------------------------------------------------

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_IGNORED_EMAIL_PREFIXES = ("noreply", "no-reply", "donotreply", "privacy", "accommodation",
                           "accessibility", "eeo", "legal", "abuse", "support")  # fmt: skip


def extract_emails(text: str) -> list[str]:
    found: dict[str, None] = {}
    for match in _EMAIL.findall(text or ""):
        email = match.strip(".").lower()
        local = email.split("@")[0]
        if email.endswith((".png", ".jpg", ".gif")) or local.startswith(_IGNORED_EMAIL_PREFIXES):
            continue
        found[email] = None
    return list(found)[:5]


# --- Years of experience ------------------------------------------------------------------

# Hyphen or en dash between numbers ("3-5"); chr() keeps this source file ASCII.
_RANGE = f"(?:-|{chr(0x2013)}|to)"

_YEARS = re.compile(
    rf"(\d{{1,2}})\s*(?:\+|plus)?\s*(?:{_RANGE}\s*(\d{{1,2}})\s*)?\+?\s*(?:years?|yrs?)"
    r"(?:\s+of)?(?:\s+\w+){0,4}?\s+(?:experience|exp\b)",
    re.I,
)


def extract_min_years(text: str) -> float | None:
    values = [int(m.group(1)) for m in _YEARS.finditer(text or "") if 0 < int(m.group(1)) <= 20]
    return float(min(values)) if values else None


# --- Seniority from the title ---------------------------------------------------------------

_SENIORITY_PATTERNS: list[tuple[re.Pattern[str], Seniority]] = [
    (re.compile(r"\b(intern|internship|trainee|werkstudent|praktikum)\b", re.I), Seniority.INTERN),
    (re.compile(r"\b(director|vp|vice president|head of)\b", re.I), Seniority.DIRECTOR),
    (re.compile(r"\bprincipal\b", re.I), Seniority.PRINCIPAL),
    (re.compile(r"\b(staff|architect)\b", re.I), Seniority.STAFF),
    (re.compile(r"\b(manager|lead)\b", re.I), Seniority.MANAGER),
    (re.compile(r"\b(senior|sr\.?|snr)\b", re.I), Seniority.SENIOR),
    (re.compile(r"\b(junior|jr\.?|entry[- ]level|graduate|associate)\b", re.I), Seniority.JUNIOR),
    (re.compile(r"\b(mid[- ]level|intermediate)\b", re.I), Seniority.MID),
]


def seniority_from_title(title: str) -> Seniority | None:
    for pattern, level in _SENIORITY_PATTERNS:
        if pattern.search(title or ""):
            return level
    return None


_LEVEL_WORDS = re.compile(
    r"\b(?:senior|sr|junior|jr|lead|principal|staff|head\s+of|mid[- ]level|entry[- ]level)\b\.?",
    re.I,
)


def internship_role(title: str) -> str:
    """'Senior Backend Engineer' -> 'Backend Engineer': the role to look for as an intern."""
    role = " ".join(_LEVEL_WORDS.sub(" ", title).split())
    return role or title.strip()


# --- Remote type ---------------------------------------------------------------------------

_HYBRID = re.compile(
    r"\bhybrid\b|\d\s*days?\s*(?:a|per)\s*week\s*(?:in|on)[- ]?(?:the\s+)?office", re.I
)
_REMOTE = re.compile(
    r"\b(fully\s+remote|100%\s*remote|remote[- ]first|work\s+from\s+home|remote)\b", re.I
)
_ONSITE = re.compile(r"\b(on[- ]?site|in[- ]office|office[- ]based)\b", re.I)


def detect_remote(title: str, location: str | None, text: str, flag: bool | None) -> RemoteType:
    head = f"{title} {location or ''}"
    if _HYBRID.search(head) or _HYBRID.search(text[:3000]):
        return RemoteType.HYBRID
    if flag or _REMOTE.search(head):
        return RemoteType.REMOTE
    if _ONSITE.search(head) or _ONSITE.search(text[:3000]):
        return RemoteType.ONSITE
    if _REMOTE.search(text[:1500]):
        return RemoteType.REMOTE
    return RemoteType.UNKNOWN


# --- Employment type -----------------------------------------------------------------------

_EMPLOYMENT: list[tuple[re.Pattern[str], EmploymentType]] = [
    (re.compile(r"\bintern(ship)?\b|\bpraktikum\b", re.I), EmploymentType.INTERNSHIP),
    (
        re.compile(r"\b(contract|contractor|freelance|fixed[- ]term|befristet)\b", re.I),
        EmploymentType.CONTRACT,
    ),
    (re.compile(r"\b(part[- ]?time|teilzeit)\b", re.I), EmploymentType.PART_TIME),
    (re.compile(r"\btemporary\b", re.I), EmploymentType.TEMPORARY),
    (
        re.compile(r"\b(full[- ]?time|fulltime|permanent|vollzeit|unbefristet)\b", re.I),
        EmploymentType.FULL_TIME,
    ),
]


def detect_employment(job_type: str | None, title: str) -> EmploymentType:
    for text in (job_type or "", title):
        for pattern, kind in _EMPLOYMENT:
            if pattern.search(text):
                return kind
    return EmploymentType.UNKNOWN


# --- Pay (paid / unpaid) -------------------------------------------------------------------

_UNPAID = re.compile(
    r"\bunpaid\b(?!\s+(?:leave|time|vacation|holiday|break|overtime))"
    r"|\bnon[- ]paid\b|\bnot\s+paid\b|\bno\s+(?:stipend|salary|pay|compensation)\b"
    r"|\bwithout\s+(?:pay|compensation|stipend|remuneration)\b|\bvolunteer\s+(?:position|role"
    r"|internship|opportunity|basis)\b|\bfor\s+(?:academic\s+)?credit\s+only\b"
    r"|\bunverg(?:ü|ue)tet",
    re.I,
)
_PAID = re.compile(
    r"\bpaid\s+(?:internship|intern|position|role|opportunity|traineeship)\b|\bstipend\b"
    r"|\ballowance\b|\bremuneration\b|\bcompensat(?:ion|ed)\b|\bsalary\b|\bhourly\s+rate\b"
    r"|\bper\s+hour\b|/\s*(?:hr|hour)\b|\bverg(?:ü|ue)tung\b|\bverg(?:ü|ue)tet",
    re.I,
)


def detect_pay(title: str, text: str, has_salary: bool) -> PayStatus:
    """Unpaid wording wins (it's explicit); then a salary or paid wording; else unknown."""
    head = title + " " + text[:6000]
    if _UNPAID.search(head):
        return PayStatus.UNPAID
    if has_salary or _PAID.search(head):
        return PayStatus.PAID
    return PayStatus.UNKNOWN


# --- Salary --------------------------------------------------------------------------------

_CURRENCY = {"$": "USD", "£": "GBP", "€": "EUR", "₹": "INR", "usd": "USD", "gbp": "GBP",
             "eur": "EUR", "inr": "INR", "pkr": "PKR", "cad": "CAD", "aud": "AUD"}  # fmt: skip
_SALARY = re.compile(
    r"(?P<cur>[$£€₹]|\b(?:usd|gbp|eur|inr|pkr|cad|aud)\b)?\s*"
    r"(?P<lo>\d{1,3}(?:[,.]\d{3})+|\d+(?:\.\d+)?)\s*(?P<lok>k)?\s*"
    rf"{_RANGE}\s*"
    r"(?P<cur2>[$£€₹])?\s*(?P<hi>\d{1,3}(?:[,.]\d{3})+|\d+(?:\.\d+)?)\s*(?P<hik>k)?"
    r"(?:\s*(?P<cur3>usd|gbp|eur|inr|pkr|cad|aud))?"
    r"(?:\s*(?:per|/|a)\s*(?P<per>year|annum|yr|month|mo|hour|hr))?",
    re.I,
)


@dataclass(frozen=True)
class Salary:
    min: int
    max: int
    currency: str | None
    period: SalaryPeriod


def _amount(raw: str, k: bool) -> float:
    value = float(re.sub(r"[,.](?=\d{3}\b)", "", raw))
    return value * 1000 if k else value


def parse_salary(text: str) -> Salary | None:
    for m in _SALARY.finditer(text or ""):
        currency_token = (m.group("cur") or m.group("cur2") or m.group("cur3") or "").lower()
        has_k = bool(m.group("lok") or m.group("hik"))
        if not currency_token and not has_k and not m.group("per"):
            continue  # "3-5 years", "10-20 people": not a salary
        lo = _amount(m.group("lo"), bool(m.group("lok") or m.group("hik")))
        hi = _amount(m.group("hi"), bool(m.group("hik")))
        if hi < lo:
            lo, hi = hi, lo
        per = (m.group("per") or "").lower()
        if per in ("hour", "hr"):
            period = SalaryPeriod.HOUR
        elif per in ("month", "mo"):
            period = SalaryPeriod.MONTH
        else:
            period = SalaryPeriod.HOUR if hi < 500 else SalaryPeriod.YEAR
        if period == SalaryPeriod.YEAR and hi < 5000:
            continue
        return Salary(int(lo), int(hi), _CURRENCY.get(currency_token), period)
    return None


# --- Skills --------------------------------------------------------------------------------

_EXTRA_SKILLS = [
    "java", "kotlin", "swift", "rust", "php", "ruby", "ruby on rails", "rails", "laravel",
    "scala", "r", "matlab", "bash", "powershell", "sql server", "oracle", "sqlite",
    "elasticsearch", "kafka", "rabbitmq", "airflow", "spark", "hadoop", "snowflake", "dbt",
    "bigquery", "tableau", "power bi", "excel", "figma", "jira", "agile", "scrum",
    "microservices", "serverless", "lambda", "ansible", "jenkins", "github actions",
    "gitlab", "nginx", "celery", "selenium", "playwright", "cypress", "jest", "pytest",
    "flutter", "react native", "android", "ios", "unity", "solidity", "opencv", "langchain",
    "data analysis", "data engineering", "etl", "computer vision", "keras", "svelte",
    "jquery", "bootstrap", "sass", "webpack", "vite", "redux", "prisma", "supabase",
    "firebase", "dynamodb", "cassandra", "neo4j", "openai", "hugging face", "mlops",
    "devops", "sre", "linux", "unix", "networking", "security", "penetration testing",
    "salesforce", "sap", "seo", "accessibility", "ux", "ui design",
]  # fmt: skip
# Too ambiguous as plain words to count as skills unless spelled out (e.g. "golang").
_AMBIGUOUS = {"go", "rest", "next", "node", "express", "r", "ml", "dl", "js", "ts", "py",
              "ios", "ui design", "ux", "security", "networking", "lambda"}  # fmt: skip
_SKILL_TERMS = sorted(
    {k for k in _ALIASES if k not in _AMBIGUOUS}
    | {s for s in _EXTRA_SKILLS if s not in _AMBIGUOUS},
    key=len,
    reverse=True,
)
_SKILL_RE = re.compile(
    r"(?<![\w+#.])(" + "|".join(re.escape(t) for t in _SKILL_TERMS) + r")(?![\w+#])", re.I
)


def extract_skills(text: str, limit: int = 25) -> list[str]:
    found: dict[str, str] = {}
    for match in _SKILL_RE.finditer(text or ""):
        canon = canonical_skill(match.group(1))
        found.setdefault(canon.lower(), canon)
        if len(found) >= limit:
            break
    return list(found.values())
