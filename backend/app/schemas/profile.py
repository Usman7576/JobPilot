"""The structured resume profile: what the parser produces and what the user edits."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.models.enums import Seniority

Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Medium = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]
Long = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]

SkillCategory = Literal[
    "language", "framework", "tool", "cloud", "database", "soft", "domain", "other"
]
Proficiency = Literal["beginner", "intermediate", "advanced", "expert"]

_YEAR_MONTH = re.compile(r"^\d{4}(-(0[1-9]|1[0-2]))?$")


def _clean_date(value: str | None, allow_present: bool) -> str | None:
    if value is None:
        return None
    v = value.strip().lower()
    if not v:
        return None
    if allow_present and v in {"present", "current", "now"}:
        return "present"
    return v if _YEAR_MONTH.match(v) else None


class ProfileModel(BaseModel):
    # Ignore unknown keys so older/newer parser outputs still load.
    model_config = ConfigDict(extra="ignore")


class Link(ProfileModel):
    label: Short = ""
    url: Short


class Contact(ProfileModel):
    email: Short | None = None
    phone: Short | None = None
    location: Short | None = None
    links: list[Link] = Field(default_factory=list, max_length=10)


class Skill(ProfileModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    category: SkillCategory = "other"
    proficiency: Proficiency = "intermediate"
    evidence: Short | None = None


class WorkEntry(ProfileModel):
    title: Short
    company: Short
    location: Short | None = None
    start: str | None = None  # YYYY-MM or YYYY
    end: str | None = None  # YYYY-MM, YYYY or "present"
    bullets: list[Medium] = Field(default_factory=list, max_length=30)

    @field_validator("start", mode="before")
    @classmethod
    def _start(cls, v: str | None) -> str | None:
        return _clean_date(v, allow_present=False)

    @field_validator("end", mode="before")
    @classmethod
    def _end(cls, v: str | None) -> str | None:
        return _clean_date(v, allow_present=True)


class EducationEntry(ProfileModel):
    institution: Short
    degree: Short | None = None
    field: Short | None = None
    start: Short | None = None
    end: Short | None = None
    gpa: Short | None = None


class Project(ProfileModel):
    name: Short
    description: Long | None = None
    technologies: list[Short] = Field(default_factory=list, max_length=30)
    url: Short | None = None
    bullets: list[Medium] = Field(default_factory=list, max_length=20)


class Certification(ProfileModel):
    name: Short
    issuer: Short | None = None
    date: Short | None = None


class ResumeProfile(ProfileModel):
    name: Short = ""
    contact: Contact = Field(default_factory=Contact)
    summary: Long = ""
    total_years_experience: float | None = Field(default=None, ge=0, le=60)
    skills: list[Skill] = Field(default_factory=list, max_length=150)
    work_history: list[WorkEntry] = Field(default_factory=list, max_length=40)
    education: list[EducationEntry] = Field(default_factory=list, max_length=20)
    projects: list[Project] = Field(default_factory=list, max_length=40)
    certifications: list[Certification] = Field(default_factory=list, max_length=40)
    preferred_roles: list[Short] = Field(default_factory=list, max_length=15)
    seniority: Seniority | None = None

    @field_validator("seniority", mode="before")
    @classmethod
    def _seniority(cls, v: object) -> object:
        valid = {s.value for s in Seniority}
        return v if isinstance(v, str) and v in valid else None
