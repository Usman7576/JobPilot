"""Import every model so Base.metadata is complete (Alembic, tests)."""

from app.models.application import Application, ApplicationDraft, ApplicationEvent, EmailSendLog
from app.models.audit import AuditLog, IdempotencyKey
from app.models.company import Company, CompanyContact
from app.models.integration import Integration
from app.models.job import Job, JobSourceRecord
from app.models.match import JobMatch, UserJob
from app.models.notification import Notification
from app.models.preference import Preference
from app.models.resume import Resume
from app.models.search import SearchRun, SearchRunSource
from app.models.usage import UsageEvent
from app.models.user import EmailVerification, OAuthAccount, PasswordReset, RefreshToken, User

__all__ = [
    "Application",
    "ApplicationDraft",
    "ApplicationEvent",
    "AuditLog",
    "Company",
    "CompanyContact",
    "EmailSendLog",
    "EmailVerification",
    "IdempotencyKey",
    "Integration",
    "Job",
    "JobMatch",
    "JobSourceRecord",
    "Notification",
    "OAuthAccount",
    "PasswordReset",
    "Preference",
    "RefreshToken",
    "Resume",
    "SearchRun",
    "SearchRunSource",
    "UsageEvent",
    "User",
    "UserJob",
]
