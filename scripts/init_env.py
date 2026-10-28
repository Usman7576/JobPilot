"""Create .env (or .env.production) from its example with freshly generated secrets.

Usage:
    python scripts/init_env.py [--force]              # .env from .env.example
    python scripts/init_env.py --production [--force] # .env.production, with a DB password
Standard library only, so it runs before any dependency is installed.
"""

from __future__ import annotations

import base64
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def fernet_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


def main() -> int:
    production = "--production" in sys.argv
    example = ROOT / (".env.production.example" if production else ".env.example")
    target = ROOT / (".env.production" if production else ".env")
    if target.exists() and "--force" not in sys.argv:
        print(f"{target.name} already exists; pass --force to overwrite it.")
        return 1

    generated = {
        "SECRET_KEY": secrets.token_urlsafe(48),
        "ENCRYPTION_KEYS": fernet_key(),
        "FILE_MASTER_KEY": base64.b64encode(os.urandom(32)).decode(),
        "POSTGRES_PASSWORD": secrets.token_urlsafe(32),
    }
    lines = []
    for line in example.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        if key in generated and value.strip() in ("", "<generated>", "<a long random password>"):
            line = f"{key}={generated[key]}"
        lines.append(line)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
