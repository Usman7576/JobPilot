"""Create .env from .env.example with freshly generated secrets.

Usage: python scripts/init_env.py [--force]
Standard library only, so it runs before any dependency is installed.
"""

from __future__ import annotations

import base64
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / ".env.example"
TARGET = ROOT / ".env"


def fernet_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


def main() -> int:
    if TARGET.exists() and "--force" not in sys.argv:
        print(".env already exists; pass --force to overwrite it.")
        return 1

    generated = {
        "SECRET_KEY": secrets.token_urlsafe(48),
        "ENCRYPTION_KEYS": fernet_key(),
        "FILE_MASTER_KEY": base64.b64encode(os.urandom(32)).decode(),
    }
    lines = []
    for line in EXAMPLE.read_text(encoding="utf-8").splitlines():
        key = line.split("=", 1)[0]
        if key in generated and line.strip() == f"{key}=":
            line = f"{key}={generated[key]}"
        lines.append(line)
    TARGET.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
