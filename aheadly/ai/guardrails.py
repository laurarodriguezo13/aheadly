"""Guardrail: the LLM never invents figures.

Every number in an answer must appear in the facts / tool outputs of that turn.
Formatting differences ($3,000 vs 3000) are ignored; a small rounding tolerance
is allowed (±1 or 1.5%, whichever is larger) so "about $3,700" can describe 3,695.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

NUMBER_PATTERN = re.compile(r"(?<![\w.])-?\$?\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?\s?(k|%)?", re.IGNORECASE)
SMALL_COUNT_LIMIT = 12  # "two cafés", "8 weeks": small counts are never treated as invented money


@dataclass
class GuardrailResult:
    passed: bool
    unverified: list[float] = field(default_factory=list)


def numbers_in_text(text: str) -> list[float]:
    values: list[float] = []
    for match in NUMBER_PATTERN.finditer(text):
        whole, decimals, suffix = match.groups()
        value = float(whole.replace(",", "") + (f".{decimals}" if decimals else ""))
        if suffix and suffix.lower() == "k":
            value *= 1000
        values.append(value)
    return values


def numbers_in_data(data: Any) -> set[float]:
    """Recursively collect every numeric value (and digits inside ISO dates) from JSON-like data."""
    found: set[float] = set()
    if isinstance(data, bool):
        return found
    if isinstance(data, (int, float)):
        found.add(abs(float(data)))
    elif isinstance(data, str):
        for part in re.findall(r"\d+(?:\.\d+)?", data):
            found.add(float(part))
    elif isinstance(data, dict):
        for value in data.values():
            found |= numbers_in_data(value)
    elif isinstance(data, (list, tuple)):
        for value in data:
            found |= numbers_in_data(value)
    return found


def _is_allowed(value: float, allowed: set[float]) -> bool:
    value = abs(value)
    if value <= SMALL_COUNT_LIMIT:
        return True
    return any(abs(value - a) <= max(1.0, 0.015 * a) for a in allowed)


def check_numbers(answer: str, sources: list[Any]) -> GuardrailResult:
    allowed: set[float] = set()
    for source in sources:
        allowed |= numbers_in_data(source)
    unverified = [v for v in numbers_in_text(answer) if not _is_allowed(v, allowed)]
    return GuardrailResult(passed=not unverified, unverified=unverified)
