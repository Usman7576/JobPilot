"""Which email to apply to, and which domain belongs to the company (not its job board)."""

from __future__ import annotations

from urllib.parse import urlparse

# Job boards and applicant-tracking systems: their domain isn't the employer's.
NON_COMPANY_HOSTS = (
    "greenhouse.io", "lever.co", "myworkdayjobs.com", "workday.com", "ashbyhq.com",
    "smartrecruiters.com", "bamboohr.com", "jobvite.com", "icims.com", "workable.com",
    "recruitee.com", "teamtailor.com", "personio.de", "personio.com", "join.com",
    "breezy.hr", "applytojob.com", "jazzhr.com", "pinpointhq.com", "rippling.com",
    "arbeitnow.com", "remotive.com", "indeed.com", "linkedin.com", "glassdoor.com",
    "adzuna.com", "adzuna.co.uk", "jooble.org", "google.com", "ziprecruiter.com",
    "monster.com", "stepstone.de", "rozee.pk", "wellfound.com", "angel.co",
)  # fmt: skip
_RECRUITING = ("careers", "career", "jobs", "job", "recruiting", "recruitment", "recruiter",
               "talent", "hr", "hiring", "people", "apply", "karriere", "bewerbung")  # fmt: skip
_GENERIC = ("info", "hello", "contact", "office", "team", "admin", "mail", "kontakt")


def _rank(email: str) -> int:
    local = email.split("@", 1)[0].lower()
    if any(
        local == p or local.startswith(p + ".") or local.startswith(p + "-") for p in _RECRUITING
    ):
        return 3
    if local in _GENERIC:
        return 1
    return 2  # most likely a person (e.g. jane.doe@): good, but recruiting inboxes are safer


def pick_best_email(emails: list[str]) -> str | None:
    """Prefer recruiting inboxes, then people, then generic inboxes; keep the posting order."""
    if not emails:
        return None
    return max(enumerate(emails), key=lambda pair: (_rank(pair[1]), -pair[0]))[1]


def _host(url: str | None) -> str | None:
    if not url:
        return None
    host = (urlparse(url if "//" in url else f"//{url}").hostname or "").lower()
    return host.removeprefix("www.") or None


def is_company_host(host: str) -> bool:
    return not any(host == h or host.endswith("." + h) for h in NON_COMPANY_HOSTS)


def company_domain(*urls: str | None) -> str | None:
    """The first URL whose host isn't a job board or ATS, reduced to its registrable part."""
    for url in urls:
        host = _host(url)
        if host and is_company_host(host):
            parts = host.split(".")
            # careers.acme.com -> acme.com; keep acme.co.uk whole.
            keep = 3 if len(parts) > 2 and len(parts[-1]) == 2 and len(parts[-2]) <= 3 else 2
            return ".".join(parts[-keep:])
    return None
