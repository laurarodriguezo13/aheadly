"""File import: a bank or accounting export as CSV or Excel.

Accepts the app's own format (date, description, amount, optional category) and the
usual bank-statement shape (Date / Description / Debit / Credit / Balance, English or
Spanish headers). Amounts: + money in, - money out. An optional second file lists the
owner's upcoming one-off payments and expected income.
"""

from __future__ import annotations

from io import BytesIO

import pandas as pd

from aheadly.data.connectors.base import SyncPayload
from aheadly.domain import ScheduledItem, Transaction

NEW_BUSINESS = {"name": "My business", "owner_name": "", "city": "", "low_cash_line": 2000.0}

# header aliases, lower-cased: bank exports rarely use our column names
ALIASES = {
    "date": {"date", "fecha", "posted date", "transaction date", "fecha de transacción"},
    "description": {"description", "descripción", "descripcion", "memo", "concepto", "details", "detalle"},
    "amount": {"amount", "monto", "valor", "importe"},
    "debit": {"debit", "débito", "debito", "withdrawal", "salida"},
    "credit": {"credit", "crédito", "credito", "deposit", "entrada"},
    "category": {"category", "categoría", "categoria"},
    "counterparty": {"counterparty", "payee", "beneficiario", "tercero", "merchant"},
    "balance": {"balance", "saldo", "running balance"},
}
UPCOMING_COLUMNS = {
    "date": ALIASES["date"] | {"due date", "fecha de pago"},
    "description": ALIASES["description"],
    "amount": ALIASES["amount"],
}


class CsvConnector:
    """Kept under its spec name; `.xlsx` files are read the same way."""

    source = "csv"

    def __init__(
        self,
        content: str | bytes,
        balance: float | None,
        filename: str = "export.csv",
        business_profile=None,
        upcoming: bytes | None = None,
        upcoming_filename: str = "upcoming.csv",
    ):
        """`balance` None = read the closing balance from the statement's Balance column.
        `upcoming` = the owner's own file of one-off payments and expected income (optional)."""
        self._content = content.encode() if isinstance(content, str) else content
        self._filename = filename
        self._balance = balance
        self._profile = business_profile or dict(NEW_BUSINESS)
        self._upcoming = upcoming
        self._upcoming_filename = upcoming_filename

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
        balance = self._balance if self._balance is not None else closing_balance(frame)
        scheduled = read_upcoming_payments(self._upcoming, self._upcoming_filename) if self._upcoming else []
        return SyncPayload(
            account_name="Imported file",
            balance=balance,
            transactions=transactions,
            scheduled_items=scheduled,
        )


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
    out["balance"] = pd.to_numeric(frame[found["balance"]], errors="coerce") if "balance" in found else None
    return out.dropna(subset=["date", "amount"])


def closing_balance(frame: pd.DataFrame) -> float:
    """The running balance on the newest row of the statement (needs a Balance column)."""
    rows = frame.dropna(subset=["balance"])
    if rows.empty:
        raise ValueError("The file has no Balance column, so please type your current balance.")
    rows = rows.assign(when=pd.to_datetime(rows["date"])).sort_values("when", kind="stable")
    return float(rows["balance"].iloc[-1])


def read_upcoming_payments(content: bytes, filename: str) -> list[ScheduledItem]:
    """The owner's own list of one-off payments and expected income: Date, Description, Amount (+ in, - out)."""
    frame = read_table(content, filename)
    lower = {str(c).strip().lower(): c for c in frame.columns}
    found = {
        field: lower[name] for field, names in UPCOMING_COLUMNS.items() for name in names if name in lower
    }
    missing = set(UPCOMING_COLUMNS) - set(found)
    if missing:
        raise ValueError(f"The upcoming payments file is missing columns: {sorted(missing)}")
    amounts = pd.to_numeric(frame[found["amount"]], errors="coerce")
    items = []
    for when, label, amount in zip(frame[found["date"]], frame[found["description"]], amounts):
        if pd.isna(when) or pd.isna(amount):
            continue
        items.append(
            ScheduledItem(
                label=str(label),
                amount=float(amount),
                due_date=pd.Timestamp(when).date(),
                kind="receivable" if amount > 0 else "bill",
                source="csv",
            )
        )
    return items
