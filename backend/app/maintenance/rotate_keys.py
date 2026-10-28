"""Re-encrypt stored secrets with the current keys (after adding a new key).

Fields (MultiFernet): put the NEW key first in ENCRYPTION_KEYS and keep the old one after it,
run this, then drop the old key. Files (AES-GCM envelope): set FILE_MASTER_KEY to the new
key and pass the old one with --old-file-key; only each file's wrapped data key changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import LargeBinary, bindparam, select, text
from sqlalchemy.orm import Session

from app.core import crypto
from app.db.base import Base
from app.db.types import EncryptedJSON, EncryptedText
from app.models import Resume
from app.providers.storage import get_storage

BATCH = 500


@dataclass
class RotationReport:
    fields: dict[str, int]
    files: int


def encrypted_columns() -> dict[str, list[str]]:
    """table -> encrypted column names, read from the models (nothing hard-coded)."""
    out: dict[str, list[str]] = {}
    for table in Base.metadata.sorted_tables:
        cols = [c.name for c in table.columns if isinstance(c.type, (EncryptedText, EncryptedJSON))]
        if cols:
            out[table.name] = cols
    return out


def rotate_fields(session: Session) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table, cols in encrypted_columns().items():
        done = 0
        for col in cols:
            # Raw bytes in, raw bytes out: the values are never decoded to text here.
            rows = session.execute(
                text(f'select id, "{col}" from "{table}" where "{col}" is not null')  # noqa: S608
            ).all()
            stmt = text(f'update "{table}" set "{col}" = :value where id = :id').bindparams(  # noqa: S608
                bindparam("value", type_=LargeBinary)
            )
            for start in range(0, len(rows), BATCH):
                chunk = rows[start : start + BATCH]
                session.execute(
                    stmt,
                    [{"id": rid, "value": crypto.rotate(bytes(raw))} for rid, raw in chunk],
                )
                done += len(chunk)
            session.commit()
        counts[table] = done
    return counts


def rewrap_files(session: Session, old_master_key: str) -> int:
    storage = get_storage()
    count = 0
    for key in session.scalars(select(Resume.file_key)):
        try:
            blob = storage.get(key)
        except FileNotFoundError:
            continue
        storage.put(key, crypto.rewrap_file(blob, old_master_key))
        count += 1
    return count


def run(session: Session, old_file_key: str | None = None) -> RotationReport:
    fields = rotate_fields(session)
    files = rewrap_files(session, old_file_key) if old_file_key else 0
    return RotationReport(fields=fields, files=files)


__all__ = ["RotationReport", "encrypted_columns", "run"]
