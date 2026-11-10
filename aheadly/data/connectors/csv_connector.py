"""File import: a bank or accounting export as CSV or Excel.

Accepts the app's own format (date, description, amount, optional category) and the
usual bank-statement shape (Date / Description / Debit / Credit / Balance, English or
Spanish headers). Amounts: + money in, - money out.
"""

from __future__ import annotations

from io import BytesIO

import pandas as pd

from aheadly.data.connectors.base import SyncPayload
from aheadly.data.seed_demo import DEMO_BUSINESS
from aheadly.domain import Transaction

# header aliases, lower-cased: bank exports rarely use our column names
ALIASES = {
    "date": {"date", "fecha", "posted date", "transaction date", "fecha de transacción"},
    "description": {"description", "descripción", "descripcion", "memo", "concepto", "details", "detalle"},
    "amount": {"amount", "monto", "valor", "importe"},
    "debit": {"debit", "débito", "debito", "withdrawal", "salida"},
    "credit": {"credit", "crédito", "credito", "deposit", "entrada"},
    "category": {"category", "categoría", "categoria"},
    "counterparty": {"counterparty", "payee", "beneficiario", "tercero", "merchant"},
}


class CsvConnector:
    """Kept under its spec name; `.xlsx` files are read the same way."""

    source = "csv"

    def __init__(
        self, content: str | bytes, balance: float, filename: str = "export.csv", business_profile=None
    ):
        self._content = content.encode() if isinstance(content, str) else content
        self._filename = filename
        self._balance = balance
        self._profile = business_profile or dict(DEMO_BUSINESS)

    def business_profile(self) -> dict:
        return dict(self._profile)

    def sync(self) -> SyncPayload:
        frame = normalise_columns(read_table(self._content, self._filename))
        transactions = [
            Transaction(
                date=pd.Timestamp(r.date).date(),
                amount=float(r.amount),
                description=str(r.description),
                category=str(r.category),
                counterparty=str(r.counterparty),
                source="csv",
                external_id=f"csv-{i}-{r.date}-{r.amount}",
            )
            for i, r in enumerate(frame.itertuples())
        ]
        return SyncPayload(account_name="Imported file", balance=self._balance, transactions=transactions)


def read_table(content: bytes, filename: str) -> pd.DataFrame:
    if filename.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(BytesIO(content))
    return pd.read_csv(BytesIO(content))


def normalise_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Map bank headers onto date / description / amount / category. LBYL: validate before any work."""
    lower = {str(c).strip().lower(): c for c in frame.columns}
    found = {field: lower[name] for field, names in ALIASES.items() for name in names if name in lower}
    missing = {"date", "description"} - set(found)
    if "amount" not in found and not {"debit", "credit"} <= set(found):
        missing.add("amount (or debit + credit)")
    if missing:
        raise ValueError(f"File is missing columns: {sorted(missing)}")
    out = pd.DataFrame({"date": frame[found["date"]], "description": frame[found["description"]]})
    if "amount" in found:
        out["amount"] = pd.to_numeric(frame[found["amount"]], errors="coerce")
    else:
        credit = pd.to_numeric(frame[found["credit"]], errors="coerce").fillna(0)
        debit = pd.to_numeric(frame[found["debit"]], errors="coerce").fillna(0)
        out["amount"] = credit - debit.abs()
    out["category"] = frame[found["category"]].fillna("other") if "category" in found else "other"
    out["counterparty"] = frame[found["counterparty"]].fillna("") if "counterparty" in found else ""
    return out.dropna(subset=["date", "amount"])
