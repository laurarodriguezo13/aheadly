"""Connector interface (interface "Sync Transactions").

Every data source (demo, CSV, Plaid, QuickBooks) returns the same SyncPayload,
so App Core never needs to know where the numbers came from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from aheadly.domain import ScheduledItem, Transaction


@dataclass
class SyncPayload:
    account_name: str
    balance: float
    transactions: list[Transaction]
    scheduled_items: list[ScheduledItem] = field(default_factory=list)


class ConnectorNotConfigured(RuntimeError):
    """Raised when a real connector has no credentials; the UI shows 'Connect later'."""


class Connector(Protocol):
    source: str

    def business_profile(self) -> dict: ...

    def sync(self) -> SyncPayload: ...
