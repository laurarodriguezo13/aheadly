"""Download / Load my data (roadmap 5.1): one file with everything a visit knows about a business.

Each visit starts empty and nothing is kept on the server (DECISIONS #17), so this file is how an
owner comes back next month, or after an update to the site cleared their visit (issue 34). It's a
zip with one `data.json`: every table's rows as plain values, the database's schema version and the
code that wrote it. Loading reads it as data only (JSON, never code), checks all of it before
anything changes, and refuses a file from a newer version of the app instead of guessing.
"""

from __future__ import annotations

import io
import json
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timezone

FORMAT = "aheadly-data"
MEMBER = "data.json"
SUFFIX = ".aheadly"
MAX_BYTES = 25_000_000  # data.json unpacked; a year of statements is about 1 MB

# every table that belongs to the business, parents first (loaded in this order)
TABLES = (
    "businesses",
    "business_profile",
    "accounts",
    "transactions",
    "scheduled_items",
    "forecast_runs",
    "forecast_points",
    "alerts",
    "insights",
    "scenarios",
    "chat_messages",
    "payee_rules",
    "uploaded_files",
)
LEFT_OUT = {"accounts": ("access_token_enc",)}  # a bank connection's token never leaves the session
SCALARS = (str, int, float, bool, type(None))


class DataFileError(ValueError):
    """Why a file can't be loaded, as a key the page turns into words (`copy.LOAD_ERRORS`)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class Loaded:
    business_name: str
    exported_at: str
    tables: dict[str, list[dict]]


def file_name(business_name: str, day: date) -> str:
    """aheadly-panaderia-la-esquina-2026-11-17.aheadly (accents as plain letters)"""
    plain = unicodedata.normalize("NFKD", business_name).encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", plain).strip("-") or "business"
    return f"aheadly-{slug[:40]}-{day.isoformat()}{SUFFIX}"


def pack(tables: dict[str, list[dict]], schema_version: int, app_version: str, business_name: str) -> bytes:
    payload = {
        "format": FORMAT,
        "schema_version": schema_version,
        "app_version": app_version,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "business_name": business_name,
        "tables": tables,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MEMBER, json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return buffer.getvalue()


def unpack(content: bytes, schema_version: int, columns: dict[str, set[str]]) -> Loaded:
    """Read and check a file; raise DataFileError before anything is changed.

    `schema_version` is this app's; `columns` each table's columns here. An older file is fine: the
    columns it doesn't have get their defaults, as the database's own upgrades would give them."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
        info = archive.getinfo(MEMBER)
    except (zipfile.BadZipFile, KeyError):
        raise DataFileError("not_ours") from None
    if info.file_size > MAX_BYTES:
        raise DataFileError("too_big")
    try:
        with archive.open(info) as member:  # the size in the zip's own header can't be trusted
            raw = member.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise DataFileError("too_big")
        payload = json.loads(raw.decode("utf-8"))
    except (zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError, OSError, EOFError):
        raise DataFileError("broken") from None
    if not isinstance(payload, dict) or payload.get("format") != FORMAT:
        raise DataFileError("not_ours")
    version = payload.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 0:
        raise DataFileError("broken")
    if version > schema_version:
        raise DataFileError("newer")
    tables = payload.get("tables")
    if not isinstance(tables, dict) or set(tables) - set(TABLES):
        raise DataFileError("broken")
    for table, rows in tables.items():
        if not isinstance(rows, list):
            raise DataFileError("broken")
        for row in rows:
            if (
                not isinstance(row, dict)
                or set(row) - columns[table]
                or not all(isinstance(v, SCALARS) for v in row.values())
            ):
                raise DataFileError("broken")
    businesses = tables.get("businesses") or []
    if len(businesses) != 1 or not isinstance(businesses[0].get("id"), int):
        raise DataFileError("broken")
    business_id = businesses[0]["id"]
    for table, rows in tables.items():  # one business per file: every row must be its own
        if any("business_id" in row and row["business_id"] != business_id for row in rows):
            raise DataFileError("broken")
    if version < 2:  # what migration 2 does for a database: a planned payment's first due date
        for row in tables.get("scheduled_items", []):
            row.setdefault("first_due_date", row.get("due_date"))
    return Loaded(
        business_name=str(businesses[0].get("name") or ""),
        exported_at=str(payload.get("exported_at") or ""),
        tables={t: tables.get(t, []) for t in TABLES},
    )
