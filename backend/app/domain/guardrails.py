"""Checks generated (or edited) application text against the fact sheet.

Deterministic checks run on every generation and every save (fast, no AI):
- numbers must come from the resume (or be quoted from the job posting),
- skills/technologies must be on the resume (job skills only as a warning: it may be fine
  to mention them, but not to claim them),
- degrees must exist on the resume.
The AI claim verifier adds "warn" flags for claims it can't trace to a fact-sheet line.

severity "block" = likely fabricated: Send/Copy needs it fixed or explicitly confirmed.
severity "warn" = worth a look.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from rapidfuzz import fuzz

from app.domain.extraction_rules import extract_skills
from app.domain.fact_sheet import FactSheet, degrees_in, numbers_in
from app.domain.skills import canonical_skill

Severity = Literal["block", "warn"]
SUPPORT_THRESHOLD = 85
_CERT = re.compile(r"\bcertifi(?:ed|cation)\b", re.I)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_PARAGRAPH = re.compile(r"\n\s*\n")
# Counts "don't" as one word, with a straight or a curly apostrophe (chr keeps this ASCII).
_WORD = re.compile(r"\b[\w'" + chr(0x2019) + r"-]+\b")
# Fact-sheet ids a model may copy into the text: " (b1)", "[role2]", "(b1, b3)".
_FACT_ID = re.compile(
    r"\s?[(\[]\s*(?:b|role|project|edu|cert)\d+(?:\s*,\s*(?:b|role|project|edu|cert)\d+)*\s*[)\]]"
)


def strip_fact_ids(text: str) -> str:
    return _FACT_ID.sub("", text)


@dataclass
class Flag:
    text: str  # the offending snippet, for inline highlighting
    reason: str
    severity: Severity
    source: str  # numbers | skills | degrees | certifications | verifier | length


@dataclass
class Report:
    flags: list[Flag] = field(default_factory=list)
    verified: bool = False  # the AI fact-check ran on this exact text

    @property
    def blocked(self) -> bool:
        return any(f.severity == "block" for f in self.flags)

    def to_json(self) -> dict[str, Any]:
        return {
            "claims": [asdict(f) for f in self.flags],
            "blocked": self.blocked,
            "verified": self.verified,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any] | None) -> Report:
        data = data or {}
        return cls([Flag(**c) for c in data.get("claims", [])], bool(data.get("verified")))


def _same_skill(a: str, b: str) -> bool:
    return canonical_skill(a).lower() == canonical_skill(b).lower()


def check_text(text: str, facts: FactSheet, job_text: str = "") -> Report:
    report = Report()
    allowed_numbers = facts.numbers | numbers_in(job_text)
    for number in sorted(numbers_in(text) - allowed_numbers):
        report.flags.append(
            Flag(number, f"The number {number} isn't on your resume.", "block", "numbers")
        )

    job_skills = extract_skills(job_text)
    for skill in extract_skills(text):
        if any(_same_skill(skill, own) for own in facts.skills):
            continue
        if any(_same_skill(skill, js) for js in job_skills):
            report.flags.append(
                Flag(
                    skill,
                    f"{skill} is from the job post, not your resume. "
                    "Mention it only as something you'd learn, not as experience.",
                    "warn",
                    "skills",
                )
            )
        else:
            report.flags.append(Flag(skill, f"{skill} isn't on your resume.", "block", "skills"))

    for degree in sorted(degrees_in(text) - facts.degrees):
        report.flags.append(Flag(degree, "This degree isn't on your resume.", "block", "degrees"))
    if not facts.certifications and (m := _CERT.search(text)):
        report.flags.append(
            Flag(m.group(), "Your resume lists no certifications.", "warn", "certifications")
        )
    return report


def is_supported(quote: str, facts: FactSheet) -> bool:
    quote = quote.strip().lower()
    if len(quote) < 4:
        return False
    return any(fuzz.partial_ratio(quote, line.lower()) >= SUPPORT_THRESHOLD for line in facts.lines)


def verifier_flags(claims: list[dict[str, str]], facts: FactSheet) -> list[Flag]:
    """Claims the AI verifier found, minus the ones a fact-sheet line supports."""
    return [
        Flag(
            c.get("claim", "")[:200],
            "Couldn't find this in your resume. Check it's accurate.",
            "warn",
            "verifier",
        )
        for c in claims
        if c.get("claim") and not is_supported(c.get("supporting_quote", ""), facts)
    ]


def word_count(text: str) -> int:
    return len(_WORD.findall(text))


def truncate_words(text: str, max_words: int) -> str:
    """Cut at the last sentence end that fits, keeping paragraphs; whole words as a fallback."""
    paragraphs: list[str] = []
    used = 0
    for paragraph in _PARAGRAPH.split(text.strip()):
        kept: list[str] = []
        full = True
        for sentence in _SENTENCE_END.split(paragraph.strip()):
            n = word_count(sentence)
            if used + n > max_words:
                full = False
                break
            kept.append(sentence)
            used += n
        if kept:
            paragraphs.append(" ".join(kept))
        if not full:
            break
    if paragraphs:
        return "\n\n".join(paragraphs)
    return " ".join(text.split()[:max_words])
