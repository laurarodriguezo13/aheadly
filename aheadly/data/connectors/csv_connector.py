"""File import: a bank or accounting export as CSV or Excel.

Accepts the app's own format (date, description, amount, optional category) and the
usual bank-statement shape (Date / Description / Debit / Credit / Balance, English or
Spanish headers). Amounts: + money in, - money out. An optional second file lists the
owner's upcoming one-off payments and expected income.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
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
        # set by sync(): rows we could not read, places where the Balance column doesn't add up,
        # and the date of the statement's last transaction
        self.skipped_rows = 0
        self.balance_breaks = 0
        self.first_break: date | None = None
        self.statement_end: date | None = None

    def business_profile(self) -> dict:
        return dict(self._profile)

    def sync(self) -> SyncPayload:
        raw = read_table(self._content, self._filename)
        frame = chronological(normalise_columns(raw))
        self.skipped_rows = len(raw) - len(frame)
        self.balance_breaks, self.first_break = balance_breaks(frame)
        self.statement_end = pd.Timestamp(frame["date"].max()).date() if len(frame) else None
        transactions = [
            Transaction(
                date=pd.Timestamp(r.date).date(),
                amount=float(r.amount),
                description=str(r.description),
                category=str(r.category),
                counterparty=str(r.counterparty),
                source="csv",
                external_id=line_id,
            )
            for line_id, r in zip(transaction_ids(frame), frame.itertuples())
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
    out = pd.DataFrame(
        {"date": parse_dates(frame[found["date"]]), "description": frame[found["description"]]}
    )
    if "amount" in found:
        out["amount"] = parse_amounts(frame[found["amount"]])
    else:
        credit = _blank_as_zero(frame[found["credit"]])
        debit = _blank_as_zero(frame[found["debit"]])
        out["amount"] = credit - debit.abs()
    out["category"] = frame[found["category"]].fillna("other") if "category" in found else "other"
    out["counterparty"] = frame[found["counterparty"]].fillna("") if "counterparty" in found else ""
    out["balance"] = parse_amounts(frame[found["balance"]]) if "balance" in found else None
    return out.dropna(subset=["date", "amount"])


def parse_dates(values: pd.Series) -> pd.Series:
    """ISO dates as they are; 03/11/2026 is day/month/year (Latin American banks) unless the file
    clearly uses month/day (a second number above 12). Unreadable dates become NaT."""
    if pd.api.types.is_datetime64_any_dtype(values):
        return values
    text = values.astype(str).str.strip()
    parts = text.str.extract(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})$").astype(float)
    month_first = bool((parts[1] > 12).any()) and not bool((parts[0] > 12).any())
    iso = text.str.match(r"^\d{4}-\d{1,2}-\d{1,2}")
    parsed = pd.concat(
        [
            pd.to_datetime(text[iso], format="ISO8601", errors="coerce"),
            pd.to_datetime(text[~iso], dayfirst=not month_first, format="mixed", errors="coerce"),
        ]
    )
    return parsed.reindex(text.index)


def parse_amounts(values: pd.Series) -> pd.Series:
    """Numbers in bank formats: 1.250,00 · 1,250.00 · $ 2.000 · (900,50) for minus. Unreadable → NaN."""
    if pd.api.types.is_numeric_dtype(values):
        return values.astype(float)
    return values.map(_parse_amount)


def _parse_amount(value) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return float("nan")
    text = str(value).strip()
    negative = text.startswith("(") and text.endswith(")") or text.startswith("-")
    text = re.sub(r"[^\d.,]", "", text)
    if not text or not re.search(r"\d", text):
        return float("nan")
    if "." in text and "," in text:  # the separator that comes last is the decimal one
        decimal = "." if text.rfind(".") > text.rfind(",") else ","
        text = text.replace("," if decimal == "." else ".", "").replace(decimal, ".")
    elif "," in text or "." in text:
        sep = "," if "," in text else "."
        groups = text.split(sep)
        if len(groups) > 2 or len(groups[-1]) == 3:  # 1.250 / 12,500 / 1.250.000: thousands
            text = text.replace(sep, "")
        else:  # 850,5 / 75.25: decimals
            text = text.replace(sep, ".")
    try:
        number = float(text)
    except ValueError:
        return float("nan")
    return -number if negative else number


def _blank_as_zero(values: pd.Series) -> pd.Series:
    """Debit/credit columns: an empty cell means 0, but text we can't read stays NaN (the row is skipped)."""
    blank = values.isna() | (values.astype(str).str.strip() == "")
    return parse_amounts(values).where(~blank, 0.0)


def chronological(frame: pd.DataFrame) -> pd.DataFrame:
    """Oldest line first. Many banks list the newest first; then the whole file is turned around,
    so lines on the same day also end up in the order they happened."""
    if len(frame) > 1 and frame["date"].iloc[0] > frame["date"].iloc[-1]:
        frame = frame.iloc[::-1]
    return frame.reset_index(drop=True)


def closing_balance(frame: pd.DataFrame) -> float:
    """The running balance on the newest line of the statement (needs a Balance column)."""
    rows = chronological(frame).dropna(subset=["balance"])
    if rows.empty:
        raise ValueError("The file has no Balance column, so please type your current balance.")
    return float(rows["balance"].iloc[-1])


def balance_breaks(frame: pd.DataFrame) -> tuple[int, date | None]:
    """With a Balance column, each line's balance is the previous one plus its amount. Returns how
    many lines don't add up and the date of the first (0, None: it adds up, or nothing to check).
    A break usually means lines are missing from the file or could not be read."""
    rows = chronological(frame).dropna(subset=["balance"])
    if len(rows) < 2:
        return 0, None
    expected = rows["balance"].shift(1) + rows["amount"]
    off = ((expected - rows["balance"]).abs() > 0.01) & expected.notna()
    if not off.any():
        return 0, None
    return int(off.sum()), pd.Timestamp(rows.loc[off, "date"].iloc[0]).date()


def transaction_ids(frame: pd.DataFrame) -> list[str]:
    """The same bank line gets the same id in any file, so uploading a statement again (or two that
    overlap) never counts a transaction twice. Identical lines on one day are told apart by order."""
    seen: dict[str, int] = {}
    ids = []
    for r in frame.itertuples():
        balance = "" if pd.isna(r.balance) else f"{float(r.balance):.2f}"
        words = " ".join(str(r.description).upper().split())
        key = f"{pd.Timestamp(r.date).date()}|{float(r.amount):.2f}|{words}|{balance}"
        seen[key] = seen.get(key, 0) + 1
        ids.append("csv-" + hashlib.sha1(f"{key}|{seen[key]}".encode()).hexdigest()[:16])
    return ids


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
