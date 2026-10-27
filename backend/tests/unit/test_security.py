from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.core import security
from app.core.config import get_settings
from app.core.logging import redact_text
from app.db.base import uuid7


def test_password_hash_and_verify() -> None:
    h = security.hash_password("correct horse battery")
    assert h.startswith("$argon2id$")
    assert security.verify_password("correct horse battery", h)
    assert not security.verify_password("wrong", h)
    assert not security.verify_password("x", "not-a-hash")


def test_access_token_round_trip() -> None:
    uid, sid = uuid.uuid4(), uuid.uuid4()
    claims = security.decode_access_token(security.create_access_token(uid, sid))
    assert claims is not None
    assert claims.user_id == uid
    assert claims.session_id == sid


def test_expired_and_foreign_tokens_rejected() -> None:
    key = get_settings().secret_key
    expired = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "sid": str(uuid.uuid4()),
            "typ": "access",
            "exp": datetime.now(UTC) - timedelta(seconds=1),
        },
        key,
        algorithm="HS256",
    )
    assert security.decode_access_token(expired) is None
    forged = jwt.encode({"sub": "x", "typ": "access"}, "other-key-" * 4, algorithm="HS256")
    assert security.decode_access_token(forged) is None
    # A state token must not work as an access token.
    assert security.decode_access_token(security.sign_state({"sub": "x"})) is None


def test_state_round_trip() -> None:
    token = security.sign_state({"state": "abc", "verifier": "v"})
    data = security.read_state(token)
    assert data is not None and data["state"] == "abc"
    assert security.read_state("garbage") is None


def test_uuid7_is_versioned_and_time_ordered() -> None:
    ids = [uuid7() for _ in range(50)]
    assert all(u.version == 7 for u in ids)
    assert all(u.variant == uuid.RFC_4122 for u in ids)
    assert [u.int >> 80 for u in ids] == sorted(u.int >> 80 for u in ids)


def test_log_redaction() -> None:
    assert redact_text("contact ada@example.com or +1 (555) 123-4567") == (
        "contact [email] or [phone]"
    )
