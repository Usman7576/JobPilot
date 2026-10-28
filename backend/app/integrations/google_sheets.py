"""Google Sheets: the tracker spreadsheet the app creates and keeps in sync (one-way).

Scope drive.file only: the app can open the files it created itself, nothing else in Drive.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import get_settings
from app.integrations import google_oauth
from app.integrations.gmail import Tokens, parse_tokens

FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"
SCOPES = ("openid", "email", FILE_SCOPE)
API = "https://sheets.googleapis.com/v4/spreadsheets"
TITLE = "JobPilot AI Tracker"
TABS = ("Jobs", "Applications")


class SheetsAuthError(Exception):
    """Access is missing or revoked: reconnect."""


class SheetsError(Exception):
    def __init__(self, message: str, *, gone: bool = False) -> None:
        super().__init__(message)
        self.gone = gone  # the spreadsheet was deleted: make a new one next time


@dataclass(frozen=True)
class Spreadsheet:
    id: str
    url: str


def consent_url(state: str, code_challenge: str, login_hint: str | None = None) -> str:
    extra = {"access_type": "offline", "prompt": "consent", "include_granted_scopes": "true"}
    if login_hint:
        extra["login_hint"] = login_hint
    return google_oauth.authorization_url(
        redirect_uri=get_settings().google_sheets_redirect_uri,
        state=state,
        code_challenge=code_challenge,
        scopes=SCOPES,
        extra=extra,
    )


async def exchange(code: str, code_verifier: str) -> Tokens:
    payload = await google_oauth.exchange_code(
        code=code,
        redirect_uri=get_settings().google_sheets_redirect_uri,
        code_verifier=code_verifier,
    )
    tokens = parse_tokens(payload)
    if FILE_SCOPE not in tokens.scopes:
        raise SheetsAuthError("Permission to create the tracker sheet wasn't granted.")
    return tokens


def _request(method: str, url: str, token: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        resp = httpx.request(
            method, url, json=body, headers={"Authorization": f"Bearer {token}"}, timeout=30
        )
    except httpx.TransportError as exc:
        raise SheetsError("Couldn't reach Google Sheets.") from exc
    if resp.status_code in (401, 403):
        raise SheetsAuthError("Google Sheets access was rejected. Reconnect Sheets.")
    if resp.status_code == 404:
        raise SheetsError("The tracker sheet no longer exists.", gone=True)
    if resp.status_code != 200:
        raise SheetsError(f"Google Sheets failed ({resp.status_code}).")
    data: dict[str, Any] = resp.json()
    return data


def create(token: str) -> Spreadsheet:
    data = _request(
        "POST",
        API,
        token,
        {
            "properties": {"title": TITLE},
            "sheets": [
                {"properties": {"title": t, "gridProperties": {"frozenRowCount": 1}}} for t in TABS
            ],
        },
    )
    return Spreadsheet(id=str(data["spreadsheetId"]), url=str(data["spreadsheetUrl"]))


def write(token: str, spreadsheet_id: str, tabs: dict[str, list[list[Any]]]) -> None:
    """Replace each tab's contents (header row first). Two API calls in total."""
    _request("POST", f"{API}/{spreadsheet_id}/values:batchClear", token, {"ranges": list(tabs)})
    _request(
        "POST",
        f"{API}/{spreadsheet_id}/values:batchUpdate",
        token,
        {
            "valueInputOption": "RAW",
            "data": [{"range": f"{name}!A1", "values": rows} for name, rows in tabs.items()],
        },
    )
