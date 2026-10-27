from __future__ import annotations

import base64

import pytest
from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core import crypto


def test_str_round_trip() -> None:
    token = crypto.encrypt_str("résumé text")
    assert b"resume" not in token
    assert crypto.decrypt_str(token) == "résumé text"


def test_json_round_trip() -> None:
    value = {"skills": ["Python", "SQL"], "years": 3.5}
    assert crypto.decrypt_json(crypto.encrypt_json(value)) == value


def test_tampered_token_fails() -> None:
    token = bytearray(crypto.encrypt_str("secret"))
    token[-5] ^= 1
    with pytest.raises(InvalidToken):
        crypto.decrypt_str(bytes(token))


def test_old_key_still_decrypts_after_rotation(monkeypatch: pytest.MonkeyPatch) -> None:
    old = crypto.encrypt_str("hello")
    new_key = base64.urlsafe_b64encode(b"n" * 32)
    current = crypto._fernet()
    rotated = MultiFernet([Fernet(new_key), *current._fernets])
    monkeypatch.setattr(crypto, "_fernet", lambda: rotated)

    assert crypto.decrypt_str(old) == "hello"
    re_encrypted = crypto.rotate(old)
    assert Fernet(new_key).decrypt(re_encrypted) == b"hello"


def test_file_round_trip() -> None:
    data = b"%PDF-1.7 fake resume bytes" * 100
    blob = crypto.encrypt_file(data)
    assert data[:20] not in blob
    assert crypto.decrypt_file(blob) == data


def test_file_tamper_detected() -> None:
    blob = bytearray(crypto.encrypt_file(b"content"))
    blob[-1] ^= 1
    with pytest.raises(Exception):  # noqa: B017 (cryptography raises InvalidTag)
        crypto.decrypt_file(bytes(blob))
