"""Times are stored in UTC and shown in the visitor's own time zone (the browser's)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


def format_local(value: str | datetime, zone: str | None) -> str:
    """'2026-11-11T15:03:00+00:00' in 'America/New_York' → 'Nov 11, 2026, 10:03'. An unknown or
    missing zone falls back to the server's; a time stored without a zone counts as the server's."""
    moment = datetime.fromisoformat(value) if isinstance(value, str) else value
    if moment.tzinfo is None:
        moment = moment.astimezone()
    try:
        target = ZoneInfo(zone) if zone else None
    except (KeyError, ValueError, OSError):
        target = None
    local = moment.astimezone(target)
    return f"{local:%b} {local.day}, {local.year}, {local:%H:%M}"
