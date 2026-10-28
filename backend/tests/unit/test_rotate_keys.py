from __future__ import annotations

import base64
import os
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select, text

from app.core import crypto
from app.core.config import get_settings
from app.db.session import sync_session
from app.maintenance import rotate_keys
from app.models import Integration, User
from app.models.enums import IntegrationProvider, IntegrationStatus


def test_encrypted_columns_are_found_from_the_models() -> None:
    cols = rotate_keys.encrypted_columns()
    assert {"access_token", "refresh_token"} <= set(cols["integrations"])
    assert {"profile", "raw_text", "file_name"} <= set(cols["resumes"])
    assert {"subject", "body", "cover_letter", "notes"} <= set(cols["applications"])


@pytest.fixture
def fresh_keys() -> Iterator[None]:
    """Key changes must reach the cached MultiFernet, and not leak into other tests."""
    crypto.reset_key_cache()
    yield
    crypto.reset_key_cache()


def test_fields_are_re_encrypted_with_the_new_key(
    clean_tables: None, fresh_keys: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    old, new = settings.encryption_keys[0], Fernet.generate_key().decode()
    with sync_session() as s:
        user = User(email="rot@example.com", email_verified_at=datetime.now(UTC))
        s.add(user)
        s.flush()
        s.add(
            Integration(
                user_id=user.id,
                provider=IntegrationProvider.GMAIL,
                status=IntegrationStatus.CONNECTED,
                access_token="token-before-rotation",
            )
        )
        s.commit()

    monkeypatch.setattr(settings, "encryption_keys", [new, old])  # new first, old still readable
    crypto.reset_key_cache()
    with sync_session() as s:
        report = rotate_keys.run(s)
    assert report.fields["integrations"] == 1

    monkeypatch.setattr(settings, "encryption_keys", [new])  # the old key is gone
    crypto.reset_key_cache()
    with sync_session() as s:
        row = s.scalar(select(Integration))
        assert row is not None and row.access_token == "token-before-rotation"

    # The stored bytes really changed keys: the old key can't open them any more.
    with sync_session() as s:
        raw = s.execute(text("select access_token from integrations")).scalar_one()
    assert Fernet(new.encode()).decrypt(bytes(raw)) == b"token-before-rotation"
    with pytest.raises(InvalidToken):
        Fernet(old.encode()).decrypt(bytes(raw))


def test_files_are_re_wrapped_for_the_new_master_key(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    old = settings.file_master_key
    blob = crypto.encrypt_file(b"%PDF resume bytes")
    new = base64.b64encode(os.urandom(32)).decode()
    monkeypatch.setattr(settings, "file_master_key", new)

    rewrapped = crypto.rewrap_file(blob, old)
    assert crypto.decrypt_file(rewrapped) == b"%PDF resume bytes"
    assert rewrapped[-20:] == blob[-20:]  # the document itself wasn't re-encrypted
    with pytest.raises(Exception):  # noqa: B017 (AES-GCM raises InvalidTag)
        crypto.decrypt_file(blob)  # the old envelope no longer opens with the new key
