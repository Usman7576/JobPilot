"""Application-level encryption.

- Fields and OAuth tokens: MultiFernet. The first key in ENCRYPTION_KEYS encrypts;
  every key can decrypt, so keys can be rotated without downtime.
- Files: AES-256-GCM with a random per-file data key, wrapped by FILE_MASTER_KEY.
"""

from __future__ import annotations

import base64
import json
import os
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, MultiFernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

_NONCE = 12
_FILE_MAGIC = b"JPF1"


@lru_cache
def _fernet() -> MultiFernet:
    keys = get_settings().encryption_keys
    return MultiFernet([Fernet(k.encode()) for k in keys])


def reset_key_cache() -> None:
    """Forget the cached keys (after ENCRYPTION_KEYS changes inside a running process)."""
    _fernet.cache_clear()


def encrypt_bytes(data: bytes) -> bytes:
    return _fernet().encrypt(data)


def decrypt_bytes(token: bytes) -> bytes:
    return _fernet().decrypt(token)


def encrypt_str(value: str) -> bytes:
    return encrypt_bytes(value.encode("utf-8"))


def decrypt_str(token: bytes) -> str:
    return decrypt_bytes(token).decode("utf-8")


def encrypt_json(value: Any) -> bytes:
    return encrypt_bytes(json.dumps(value, separators=(",", ":")).encode("utf-8"))


def decrypt_json(token: bytes) -> Any:
    return json.loads(decrypt_bytes(token))


def rotate(token: bytes) -> bytes:
    """Re-encrypt a token with the current primary key."""
    return _fernet().rotate(token)


def _master_key() -> bytes:
    raw = get_settings().file_master_key
    if not raw:
        raise RuntimeError("FILE_MASTER_KEY is not set")
    key = base64.b64decode(raw)
    if len(key) != 32:
        raise RuntimeError("FILE_MASTER_KEY must be 32 bytes, base64-encoded")
    return key


def encrypt_file(plaintext: bytes) -> bytes:
    """Layout: magic | wrap_nonce | wrapped_dek(48) | data_nonce | ciphertext."""
    dek = AESGCM.generate_key(bit_length=256)
    wrap_nonce, data_nonce = os.urandom(_NONCE), os.urandom(_NONCE)
    wrapped = AESGCM(_master_key()).encrypt(wrap_nonce, dek, _FILE_MAGIC)
    ciphertext = AESGCM(dek).encrypt(data_nonce, plaintext, None)
    return _FILE_MAGIC + wrap_nonce + wrapped + data_nonce + ciphertext


def decrypt_file(blob: bytes) -> bytes:
    if not blob.startswith(_FILE_MAGIC):
        raise ValueError("not an encrypted JobPilot file")
    pos = len(_FILE_MAGIC)
    wrap_nonce = blob[pos : pos + _NONCE]
    pos += _NONCE
    wrapped = blob[pos : pos + 48]
    pos += 48
    data_nonce = blob[pos : pos + _NONCE]
    pos += _NONCE
    dek = AESGCM(_master_key()).decrypt(wrap_nonce, wrapped, _FILE_MAGIC)
    return AESGCM(dek).decrypt(data_nonce, blob[pos:], None)


def rewrap_file(blob: bytes, old_master_key: str) -> bytes:
    """Re-wrap a file's data key from an old FILE_MASTER_KEY to the current one.

    Only the 48-byte wrapped key changes; the file's ciphertext is kept as it is.
    """
    if not blob.startswith(_FILE_MAGIC):
        raise ValueError("not an encrypted JobPilot file")
    old = base64.b64decode(old_master_key)
    head = len(_FILE_MAGIC)
    wrap_nonce = blob[head : head + _NONCE]
    wrapped = blob[head + _NONCE : head + _NONCE + 48]
    rest = blob[head + _NONCE + 48 :]
    dek = AESGCM(old).decrypt(wrap_nonce, wrapped, _FILE_MAGIC)
    new_nonce = os.urandom(_NONCE)
    rewrapped = AESGCM(_master_key()).encrypt(new_nonce, dek, _FILE_MAGIC)
    return _FILE_MAGIC + new_nonce + rewrapped + rest
