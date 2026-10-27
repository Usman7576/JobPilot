"""Column types that encrypt on write and decrypt on read (stored as bytea)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import LargeBinary
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from app.core import crypto


class EncryptedText(TypeDecorator[str]):
    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Dialect) -> bytes | None:
        return None if value is None else crypto.encrypt_str(value)

    def process_result_value(self, value: bytes | None, dialect: Dialect) -> str | None:
        return None if value is None else crypto.decrypt_str(bytes(value))


class EncryptedJSON(TypeDecorator[Any]):
    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> bytes | None:
        return None if value is None else crypto.encrypt_json(value)

    def process_result_value(self, value: bytes | None, dialect: Dialect) -> Any:
        return None if value is None else crypto.decrypt_json(bytes(value))
