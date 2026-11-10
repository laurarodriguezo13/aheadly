"""Plaid sandbox connector (bank feed).

Milestone 2 status: scaffold. The sign-convention mapping is implemented and
tested (Plaid: positive = money out; Aheadly: positive = money in). The API
calls (sandbox public token → access token → /transactions/sync) are the next
task; without PLAID_CLIENT_ID / PLAID_SECRET the connector reports
"not configured" and the UI offers demo data instead.
"""

from __future__ import annotations

import os
from datetime import date

from aheadly.data.connectors.base import ConnectorNotConfigured, SyncPayload
from aheadly.domain import Transaction


def plaid_to_transaction(raw: dict) -> Transaction:
    """Map one Plaid transaction dict to our domain object (flip the sign)."""
    return Transaction(
        date=date.fromisoformat(raw["date"]),
        amount=-float(raw["amount"]),
        description=raw.get("name", ""),
        category=(raw.get("personal_finance_category") or {}).get("primary", "other").lower(),
        counterparty=raw.get("merchant_name") or "",
        source="plaid",
        external_id=raw.get("transaction_id"),
    )


class PlaidConnector:
    source = "plaid"

    def __init__(self, client_id: str | None = None, secret: str | None = None):
        self.client_id = client_id or os.getenv("PLAID_CLIENT_ID", "")
        self.secret = secret or os.getenv("PLAID_SECRET", "")

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.secret)

    def business_profile(self) -> dict:
        return {"name": "My business", "owner_name": "Owner", "city": ""}

    def sync(self) -> SyncPayload:
        if not self.configured:
            raise ConnectorNotConfigured(
                "Add PLAID_CLIENT_ID and PLAID_SECRET to .env to connect a sandbox bank."
            )
        raise NotImplementedError("Plaid sandbox sync is planned for the final milestone (see PROGRESS.md).")
