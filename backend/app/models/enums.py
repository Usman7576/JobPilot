from __future__ import annotations

from enum import StrEnum

from sqlalchemy.dialects.postgresql import ENUM

# name -> enum class, filled by pg_enum(). Migrations create these types up front.
PG_ENUMS: dict[str, type[StrEnum]] = {}


def pg_enum(enum_cls: type[StrEnum], name: str) -> ENUM:
    """Native Postgres enum that stores the member *values* (lowercase strings).

    `create_type=False` because several tables share a type (e.g. `seniority`);
    the migration creates every type in PG_ENUMS once instead.
    """
    PG_ENUMS[name] = enum_cls
    return ENUM(
        enum_cls,
        name=name,
        values_callable=lambda e: [m.value for m in e],
        create_type=False,
    )


class OnboardingStep(StrEnum):
    RESUME = "resume"
    PROFILE = "profile"
    PREFERENCES = "preferences"
    INTEGRATIONS = "integrations"
    DONE = "done"


class OAuthProvider(StrEnum):
    GOOGLE = "google"


class ResumeStatus(StrEnum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    FAILED = "failed"


class Seniority(StrEnum):
    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"
    PRINCIPAL = "principal"
    MANAGER = "manager"
    DIRECTOR = "director"


class RemoteType(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class EmploymentType(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    TEMPORARY = "temporary"
    UNKNOWN = "unknown"


class PayStatus(StrEnum):
    """Whether a posting (mostly relevant for internships) pays, from salary or wording."""

    PAID = "paid"
    UNPAID = "unpaid"
    UNKNOWN = "unknown"


class SearchKind(StrEnum):
    JOBS = "jobs"
    INTERNSHIPS = "internships"


class SalaryPeriod(StrEnum):
    YEAR = "year"
    MONTH = "month"
    HOUR = "hour"


class NormalizationStatus(StrEnum):
    PENDING = "pending"
    RULES_ONLY = "rules_only"
    LLM = "llm"
    FAILED = "failed"


class ContactSource(StrEnum):
    JOB_DESCRIPTION = "job_description"
    HUNTER_DOMAIN = "hunter_domain"
    HUNTER_FINDER = "hunter_finder"
    MANUAL = "manual"
    NONE = "none"


class SearchTrigger(StrEnum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"


class SearchStatus(StrEnum):
    QUEUED = "queued"
    SCRAPING = "scraping"
    NORMALIZING = "normalizing"
    MATCHING_STAGE1 = "matching_stage1"
    SCORING = "scoring"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SourceRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"


class MatchStage(StrEnum):
    STAGE1 = "stage1"
    SCORED = "scored"
    SCORE_FAILED = "score_failed"


class Recommendation(StrEnum):
    STRONG_APPLY = "strong_apply"
    APPLY = "apply"
    STRETCH = "stretch"
    SKIP = "skip"


class ApplicationChannel(StrEnum):
    EMAIL = "email"
    SITE = "site"
    NONE = "none"


class ApplicationStatus(StrEnum):
    SAVED = "saved"
    DRAFTING = "drafting"
    READY = "ready"
    QUEUED = "queued"
    APPLIED = "applied"
    REPLIED = "replied"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class Tone(StrEnum):
    FORMAL = "formal"
    FRIENDLY = "friendly"
    CONCISE = "concise"


class ReplyClassification(StrEnum):
    POSITIVE = "positive"
    INTERVIEW = "interview"
    REJECTION = "rejection"
    AUTO_REPLY = "auto_reply"
    OTHER = "other"


class DraftKind(StrEnum):
    EMAIL = "email"
    COVER_LETTER = "cover_letter"
    RESUME_TWEAKS = "resume_tweaks"
    FOLLOW_UP = "follow_up"
    INTERVIEW_PREP = "interview_prep"


class EventActor(StrEnum):
    USER = "user"
    SYSTEM = "system"
    GMAIL = "gmail"


class SendStatus(StrEnum):
    SENT = "sent"
    FAILED = "failed"


class IntegrationProvider(StrEnum):
    GMAIL = "gmail"
    SHEETS = "sheets"


class IntegrationStatus(StrEnum):
    CONNECTED = "connected"
    NEEDS_REAUTH = "needs_reauth"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class UsageFeature(StrEnum):
    RESUME_PARSE = "resume_parse"
    NORMALIZE = "normalize"
    SCORE = "score"
    GENERATE = "generate"
    VERIFY = "verify"
    CLASSIFY = "classify"
    EMBED = "embed"


class NotificationKind(StrEnum):
    SEARCH_DONE = "search_done"
    STRONG_MATCHES = "strong_matches"
    REPLY_DETECTED = "reply_detected"
    FOLLOW_UP_DUE = "follow_up_due"
    SEND_FAILED = "send_failed"
    INTEGRATION_ERROR = "integration_error"
    BUDGET_WARNING = "budget_warning"
