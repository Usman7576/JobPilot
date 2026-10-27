"""The fact sheet: an allowlist of what the resume says, built in code.

It's the only resume content the writing prompts see, and the guardrails check generated
text against it (numbers, skills, degrees, employers). Contact details are left out: the
signature is added in code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.domain.extraction_rules import extract_skills
from app.schemas.profile import ResumeProfile

# 40%, $2M, 2,000, 3.5, 2 million ... Years count too (they're facts as well).
NUMBER = re.compile(
    r"(?<![\w.])[$£€₹]?\d[\d,]*(?:\.\d+)?\s*"
    r"(?:%|percent\b|million\b|thousand\b|billion\b|[kKmMbB]\b|x\b)?",
    re.I,
)
_SCALE_WORDS = {"million": "m", "thousand": "k", "billion": "b", "percent": "%"}
# Degree mentions grouped into families, so "Master of Science" matches "MSc" on the resume.
# Plain words must not look like degrees: "be" isn't a B.E., "master new tools" isn't a
# master's, and "MS Office" isn't an MS.
_DEGREE_FAMILIES: list[tuple[str, re.Pattern[str]]] = [
    ("mba", re.compile(r"\bmba\b", re.I)),
    ("phd", re.compile(r"\bph\.?\s?d\b|\bdoctorate\b", re.I)),
    (
        "master",
        re.compile(
            r"\bmaster(?:'s|s)\b|\bmaster of\b|\bm\.?\s?sc?\b(?!\s+office)|\bm\.?\s?tech\b",
            re.I,
        ),
    ),
    (
        "bachelor",
        re.compile(r"\bbachelor'?s?\b|\bb\.?\s?sc?\b|\bb\.?\s?tech\b|\bb\.\s?e\.", re.I),
    ),
    ("associate", re.compile(r"\bassociate'?s? degree\b", re.I)),
]


def normalize_number(raw: str) -> str:
    """'40 percent' -> '40%', '$2,000' -> '2000', '2 million'/'2M' -> '2m', '3.50' -> '3.5'.

    Scale matters: "5 million users" is not the same fact as "5 years".
    """
    text = raw.strip().lower()
    for word, short in _SCALE_WORDS.items():
        text = text.replace(word, short)
    text = text.replace(" ", "")
    text = re.sub(r"[$£€₹,]", "", text)
    match = re.match(r"(\d+(?:\.\d+)?)(.*)", text)
    if not match:
        return text
    value, suffix = match.groups()
    if "." in value:
        value = value.rstrip("0").rstrip(".")
    return value + suffix


def numbers_in(text: str) -> set[str]:
    return {normalize_number(m.group()) for m in NUMBER.finditer(text)}


def degrees_in(text: str) -> set[str]:
    """Degree families mentioned: bachelor, master, mba, phd, associate."""
    return {family for family, pattern in _DEGREE_FAMILIES if pattern.search(text)}


@dataclass
class FactSheet:
    name: str
    lines: list[str]  # "[b3] Built FastAPI services ..." — every fact, with an id
    skills: list[str]
    companies: list[str]
    titles: list[str]
    numbers: set[str] = field(default_factory=set)
    degrees: set[str] = field(default_factory=set)
    certifications: list[str] = field(default_factory=list)
    bullets: dict[str, str] = field(default_factory=dict)  # id -> verbatim bullet

    def as_prompt(self) -> str:
        return "\n".join(self.lines)

    @property
    def first_name(self) -> str:
        return self.name.split()[0] if self.name.strip() else ""


def build(profile: ResumeProfile, years: float | None = None) -> FactSheet:
    lines: list[str] = []
    bullets: dict[str, str] = {}
    if profile.summary:
        lines.append(f"[summary] {profile.summary}")
    if years is not None:
        lines.append(f"[years] About {years:g} years of professional experience")
    if profile.seniority:
        lines.append(f"[level] {profile.seniority.value}")

    n = 0
    for i, job in enumerate(profile.work_history, start=1):
        dates = " - ".join(d for d in (job.start, job.end) if d)
        lines.append(f"[role{i}] {job.title} at {job.company}" + (f" ({dates})" if dates else ""))
        for bullet in job.bullets:
            n += 1
            bullets[f"b{n}"] = bullet
            lines.append(f"[b{n}] ({job.company}) {bullet}")
    for i, project in enumerate(profile.projects, start=1):
        desc = f": {project.description}" if project.description else ""
        tech = f" (tech: {', '.join(project.technologies)})" if project.technologies else ""
        lines.append(f"[project{i}] {project.name}{desc}{tech}")
        for bullet in project.bullets:
            n += 1
            bullets[f"b{n}"] = bullet
            lines.append(f"[b{n}] ({project.name}) {bullet}")
    for i, edu in enumerate(profile.education, start=1):
        parts = [p for p in (edu.degree, edu.field, edu.institution, edu.end) if p]
        lines.append(f"[edu{i}] " + ", ".join(parts))
    certs = [c.name for c in profile.certifications]
    for i, cert in enumerate(certs, start=1):
        lines.append(f"[cert{i}] {cert}")
    skills = [s.name for s in profile.skills]
    if skills:
        lines.append("[skills] " + ", ".join(skills))

    text = "\n".join(lines)
    numbers = numbers_in(text)
    if years is not None:  # "5 years" / "over 5 years" for 5.3
        numbers |= {str(int(years)), str(round(years))}
    # Tools named in bullets count too ("... on AWS"), even if the skills list omits them.
    evidenced = list(dict.fromkeys([*skills, *extract_skills(text)]))
    return FactSheet(
        name=profile.name.strip(),
        lines=lines,
        skills=evidenced,
        companies=[j.company for j in profile.work_history],
        titles=[j.title for j in profile.work_history],
        numbers=numbers,
        degrees=degrees_in(text),
        certifications=certs,
        bullets=bullets,
    )
