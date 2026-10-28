"""Re-encrypt everything with the current keys. Usage (from backend/):

    uv run --env-file ../.env python scripts/rotate_keys.py [--old-file-key BASE64]

Before running: put the new key FIRST in ENCRYPTION_KEYS (keep the old one after it) and,
for files, set FILE_MASTER_KEY to the new key. Afterwards remove the old keys.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import sync_session
from app.maintenance.rotate_keys import run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-file-key", help="the previous FILE_MASTER_KEY (base64)")
    args = parser.parse_args()
    with sync_session() as session:
        report = run(session, args.old_file_key)
    for table, n in report.fields.items():
        print(f"  {table}: {n} value(s) re-encrypted")
    print(f"  files re-wrapped: {report.files}")


if __name__ == "__main__":
    main()
