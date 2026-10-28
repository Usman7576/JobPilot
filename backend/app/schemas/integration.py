from __future__ import annotations

from datetime import datetime
from typing import Literal

from app.models.enums import IntegrationProvider, IntegrationStatus
from app.schemas.common import ApiModel


class IntegrationOut(ApiModel):
    provider: IntegrationProvider
    status: IntegrationStatus
    google_email: str | None
    connected_at: datetime | None = None
    last_error: str | None = None
    last_sync_at: datetime | None = None
    spreadsheet_url: str | None = None  # sheets only
    can_read: bool = False  # gmail: read-only access was granted
    reply_detection: bool = False  # gmail: on (needs can_read)
    replies_checked_at: datetime | None = None


class IntegrationsOut(ApiModel):
    gmail: IntegrationOut
    sheets: IntegrationOut
    google_configured: bool  # GOOGLE_CLIENT_ID/SECRET are set
    # smtp = local test mode: applications go to Mailpit, not to real recipients
    send_backend: Literal["gmail", "smtp"]


class ConnectOut(ApiModel):
    url: str


class ReplyDetectionIn(ApiModel):
    enabled: bool
