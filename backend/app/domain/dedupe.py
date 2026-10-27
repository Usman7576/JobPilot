"""Dedupe keys: the same job seen on two boards (or twice on one) must map to one row."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_COMPANY_SUFFIX = re.compile(
    r"\b(inc|incorporated|llc|l\.l\.c|ltd|limited|gmbh|ag|corp|corporation|co|company|plc|"
    r"pvt|private|s\.?a|sas|bv|b\.v|oy|ab|srl|the)\b\.?",
    re.I,
)
_TITLE_NOISE = [
    re.compile(r"\([^)]*\)"),  # "(m/w/d)", "(Remote)", "(REQ-123)"
    re.compile(r"\[[^\]]*\]"),
    re.compile(r"\b(req|job)\s*(id)?[#:\s-]*\w*\d\w*\b", re.I),
]
# Note: suffixes like "Engineer - Backend" are kept on purpose; dropping them would merge
# genuinely different roles at the same company and city.
_TITLE_SYNONYMS = {
    r"\bsr\.?\b": "senior",
    r"\bsnr\b": "senior",
    r"\bjr\.?\b": "junior",
    r"\bengr\b": "engineer",
    r"\bdev\b": "developer",
    r"\bswe\b": "software engineer",
    r"\bmgr\b": "manager",
}
# Query parameters that identify the posting itself; everything else is tracking.
_KEEP_PARAMS = {"jk", "currentjobid", "jobid", "job_id", "gh_jid", "id", "vjk", "jl"}


def _squash(text: str) -> str:
    text = re.sub(r"[^\w\s]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def normalize_company(name: str) -> str:
    return _squash(_COMPANY_SUFFIX.sub(" ", name or "")) or "unknown"


def normalize_title(title: str) -> str:
    text = title or ""
    for pattern in _TITLE_NOISE:
        text = pattern.sub(" ", text)
    text = text.lower()
    for alias, repl in _TITLE_SYNONYMS.items():
        text = re.sub(alias, repl, text)
    return _squash(text)


def normalize_location(location: str | None, remote: bool) -> str:
    if remote or not location:
        return "remote" if remote else "unknown"
    parts = [_squash(p) for p in location.split(",") if _squash(p)]
    return parts[0] if parts else "unknown"  # the city is the stable part


def dedupe_hash(company: str, title: str, location: str | None, remote: bool) -> str:
    key = "|".join(
        [normalize_company(company), normalize_title(title), normalize_location(location, remote)]
    )
    return hashlib.sha256(key.encode()).hexdigest()


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    params = [(k, v) for k, v in parse_qsl(parts.query) if k.lower() in _KEEP_PARAMS]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.lower() or "https", parts.netloc.lower().removeprefix("www."), path,
         urlencode(sorted(params)), "")
    )  # fmt: skip


def url_hash(url: str) -> str:
    return hashlib.sha256(canonical_url(url).encode()).hexdigest()
