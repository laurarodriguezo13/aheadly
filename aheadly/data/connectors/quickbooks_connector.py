"""QuickBooks Online sandbox connector (open bills → scheduled bills, open invoices → receivables).

Milestone 2 status: scaffold. OAuth 2.0 with the Intuit sandbox company is the
next task; without credentials the Accounts page shows "Connect later".
"""

from __future__ import annotations

import os

from aheadly.data.connectors.base import ConnectorNotConfigured, SyncPayload


class QuickBooksConnector:
    source = "quickbooks"

    def __init__(self, client_id: str | None = None, client_secret: str | None = None):
        self.client_id = client_id or os.getenv("QBO_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("QBO_CLIENT_SECRET", "")

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def business_profile(self) -> dict:
        return {"name": "My business", "owner_name": "Owner", "city": ""}

    def sync(self) -> SyncPayload:
        if not self.configured:
            raise ConnectorNotConfigured(
                "Add QBO_CLIENT_ID and QBO_CLIENT_SECRET to .env to connect QuickBooks."
            )
        raise NotImplementedError(
            "QuickBooks sandbox sync is planned for the final milestone (see PROGRESS.md)."
        )
