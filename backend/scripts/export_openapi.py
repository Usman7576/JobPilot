"""Write the OpenAPI schema to frontend/openapi.json (input for the orval client generator).

Usage (from backend/): uv run python scripts/export_openapi.py
"""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

# Importing the app needs settings, but no real secrets or services.
os.environ.setdefault("SECRET_KEY", "openapi-export-" + "x" * 32)
os.environ.setdefault("ENCRYPTION_KEYS", base64.urlsafe_b64encode(b"e" * 32).decode())
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/db")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

from app.main import app  # noqa: E402

target = BACKEND.parent / "frontend" / "openapi.json"
target.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
print(f"Wrote {target}")
