"""'Use demo data': the connector that always works, with no keys at all."""

from __future__ import annotations

from datetime import date

from aheadly.data.connectors.base import SyncPayload
from aheadly.data.seed_demo import DEMO_BUSINESS, build_demo_dataset


class DemoConnector:
    source = "demo"

    def __init__(self, today: date | None = None):
        self.today = today

    def business_profile(self) -> dict:
        return dict(DEMO_BUSINESS)

    def sync(self) -> SyncPayload:
        dataset = build_demo_dataset(self.today)
        return SyncPayload(
            account_name="Bancolombia checking (demo)",
            balance=dataset.opening_balance,
            transactions=dataset.transactions,
            scheduled_items=dataset.scheduled_items,
        )
