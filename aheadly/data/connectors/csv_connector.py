"""File import: a bank or accounting export as CSV or Excel.

Accepts the app's own format (date, description, amount, optional category) and the
usual bank-statement shape (Date / Description / Debit / Credit / Balance, English or
Spanish headers). Amounts: + money in, - money out. An optional second file lists the
owner's upcoming one-off payments and expected income.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date
from io import BytesIO, StringIO

import pandas as pd

from aheadly.data.connectors.base import SyncPayload
from aheadly.domain import ScheduledItem, Transaction

NEW_BUSINESS = {"name": "My business", "owner_name": "", "city": "", "low_cash_line": 2000.0}

# header aliases, lower-case and without accents: bank exports rarely use our column names.
# A header also matches when its FIRST word is a one-word alias ("Fecha Movimiento", "Saldo Disponible").
ALIASES = {
    "date": {"date", "fecha", "posted date", "transaction date", "fecha de transaccion", "fecha operacion"},
    "description": {"description", "descripcion", "memo", "concepto", "details", "detalle"},
    "amount": {"amount", "monto", "valor", "importe"},
    "debit": {
        "debit",
        "debito",
        "debitos",
        "withdrawal",
        "withdrawals",
        "salida",
        "retiro",
        "retiros",
        "cargo",
        "cargos",
        "charges",
    },
    "credit": {
        "credit",
        "credito",
        "creditos",
        "deposit",
        "deposits",
        "entrada",
        "abono",
        "abonos",
        "payments",
        "pagos",
    },
    "category": {"category", "categoria"},
    "counterparty": {"counterparty", "payee", "beneficiario", "tercero", "merchant"},
    "balance": {
        "balance",
        "saldo",
        "running balance",
        "balance owed",
        "amount owed",
        "saldo adeudado",
        "saldo a pagar",
    },
}
# A credit card statement: its balance is what is owed (we store it negative), and purchases are
# its "charges". Recognised by an owed-type balance header, or English "Charges".
OWED_HEADERS = {"balance owed", "amount owed", "saldo adeudado", "saldo a pagar"}
SPANISH_MONTHS = {
    "ene": "jan",
    "abr": "apr",
    "ago": "aug",
    "sept": "sep",
    "set": "sep",
    "dic": "dec",
}
UPCOMING_COLUMNS = {
    "date": ALIASES["date"] | {"due date", "fecha de pago", "vencimiento", "fecha limite"},
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
        self.skipped_upcoming = 0  # lines of the upcoming-payments file we could not read

    def business_profile(self) -> dict:
        return dict(self._profile)

    def sync(self) -> SyncPayload:
        raw = read_table(self._content, self._filename)
        every_line = chronological(normalise_columns(raw, keep_unreadable=True))
        self.balance_breaks, self.first_break = balance_breaks(every_line)
        frame = every_line.dropna(subset=["date", "amount"]).reset_index(drop=True)
        self.skipped_rows = len(raw) - len(frame)
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
        scheduled, self.skipped_upcoming = (
            read_upcoming(self._upcoming, self._upcoming_filename) if self._upcoming else ([], 0)
        )
        return SyncPayload(
            account_name=account_label(self._filename),
            balance=balance,
            transactions=transactions,
            scheduled_items=scheduled,
            account_kind="card" if is_card_statement(raw.columns) else "bank",
        )


def account_label(filename: str) -> str:
    """'cuenta_corriente_5510.csv' → 'Cuenta corriente 5510'."""
    stem = filename.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0].replace("_", " ").strip()
    return (stem[:1].upper() + stem[1:]) if stem else "Imported file"


def is_card_statement(headers) -> bool:
    found = match_columns(headers)
    return plain(found.get("balance", "")) in OWED_HEADERS or plain(found.get("debit", "")) == "charges"


def plain(text) -> str:
    """Lower case, no accents, single spaces: 'Descripción ' → 'descripcion'."""
    decomposed = unicodedata.normalize("NFKD", str(text))
    return " ".join("".join(c for c in decomposed if not unicodedata.combining(c)).lower().split())


def match_columns(headers, aliases: dict[str, set[str]] = ALIASES) -> dict[str, object]:
    """Which header is the date, the description, the amount...: exact alias first, then first word."""
    names = {plain(h): h for h in headers}
    found = {}
    for field, options in aliases.items():
        exact = [names[n] for n in options if n in names]
        loose = [h for n, h in names.items() if n.split(" ")[0] in options] if not exact else []
        if exact or loose:
            found[field] = (exact or loose)[0]
    return found


def _looks_like_header(cells) -> bool:
    found = match_columns([c for c in cells if str(c).strip()])
    return "date" in found and ("amount" in found or {"debit", "credit"} <= set(found))


def _decode(content: bytes) -> str:
    """UTF-8 (with or without the Excel BOM), else Windows-1252, as Excel on Windows saves it."""
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("cp1252")


def read_table(content: bytes, filename: str) -> pd.DataFrame:
    """A bank export as a table, starting at its header row (banks often put the account number,
    holder and period above it). CSV: comma, semicolon or tab separated, UTF-8 or Windows-1252."""
    if filename.lower().endswith((".xlsx", ".xls")):
        sheet = pd.read_excel(BytesIO(content), header=None)
        start = next((i for i in range(min(len(sheet), 30)) if _looks_like_header(sheet.iloc[i])), 0)
        table = sheet.iloc[start + 1 :].reset_index(drop=True)
        table.columns = [str(c) for c in sheet.iloc[start]]
        return table.dropna(how="all").infer_objects()
    lines = _decode(content).splitlines()
    start = 0
    for i, line in enumerate(lines[:30]):
        if _looks_like_header(re.split(r"[;,\t]", line)):
            start = i
            break
    header = lines[start] if lines else ""
    sep = max([",", ";", "\t"], key=header.count)
    body = StringIO("\n".join(lines[start:]))
    if sep == ",":
        return pd.read_csv(body)  # numbers like 1500 or 12.5 are read as numbers, as before
    return pd.read_csv(body, sep=sep, dtype=str)  # ';' files use decimal commas: keep text, parse below


def normalise_columns(frame: pd.DataFrame, keep_unreadable: bool = False) -> pd.DataFrame:
    """Map bank headers onto date / description / amount / category. LBYL: validate before any work.
    Lines whose date or amount can't be read are dropped, unless `keep_unreadable` (the balance check
    still uses their Balance)."""
    found = match_columns(frame.columns)
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
    if "balance" in found and plain(found["balance"]) in OWED_HEADERS:
        out["balance"] = -out["balance"]  # a card's balance is money owed
    return out if keep_unreadable else out.dropna(subset=["date", "amount"])


def parse_dates(values: pd.Series) -> pd.Series:
    """ISO dates as they are; 03/11/2026 is day/month/year (Latin American banks) unless the file
    clearly uses month/day (a second number above 12). Unreadable dates become NaT."""
    if pd.api.types.is_datetime64_any_dtype(values):
        return values
    text = values.astype(str).str.strip()
    text = text.str.lower().str.replace(
        r"[a-z]+", lambda m: SPANISH_MONTHS.get(m.group(0), m.group(0)), regex=True
    )
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
    if isinstance(value, (int, float)):  # a real number (an Excel cell): nothing to guess
        return float(value)
    text = str(value).strip()
    negative = text.startswith("(") and text.endswith(")") or text.startswith("-")
    text = re.sub(r"[A-Za-z$€£\s()+\-/]", "", text)  # currency marks, signs, spaces
    if re.search(r"[^\d.,]", text):  # anything else (8#0, 1?2) means the cell is garbled
        return float("nan")
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
    dates = frame["date"].dropna()
    if len(dates) > 1 and dates.iloc[0] > dates.iloc[-1]:
        frame = frame.iloc[::-1]
    return frame.reset_index(drop=True)


def closing_balance(frame: pd.DataFrame) -> float:
    """The running balance on the newest line of the statement (needs a Balance column)."""
    rows = chronological(frame).dropna(subset=["balance", "date"])
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
    # a line whose amount can't be read is not compared (it's reported as unreadable), but its
    # Balance still carries the chain on to the next line
    expected = rows["balance"].shift(1) + rows["amount"]
    off = ((expected - rows["balance"]).abs() > 0.01) & expected.notna()
    if not off.any():
        return 0, None
    when = rows.loc[off, "date"].dropna()
    return int(off.sum()), pd.Timestamp(when.iloc[0]).date() if len(when) else None


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
    found = match_columns(frame.columns, UPCOMING_COLUMNS)
    missing = set(UPCOMING_COLUMNS) - set(found)
    if missing:
        raise ValueError(f"The upcoming payments file is missing columns: {sorted(missing)}")
    return read_upcoming(content, filename)[0]


def read_upcoming(content: bytes, filename: str) -> tuple[list[ScheduledItem], int]:
    """Like read_upcoming_payments, plus how many lines couldn't be read (date or amount). Same bank
    formats as statements: 14/11/2026, -7.500,00, semicolons, Windows encoding."""
    frame = read_table(content, filename)
    found = match_columns(frame.columns, UPCOMING_COLUMNS)
    missing = set(UPCOMING_COLUMNS) - set(found)
    if missing:
        raise ValueError(f"The upcoming payments file is missing columns: {sorted(missing)}")
    dates = parse_dates(frame[found["date"]])
    amounts = parse_amounts(frame[found["amount"]])
    items, skipped = [], 0
    for when, label, amount in zip(dates, frame[found["description"]], amounts):
        if pd.isna(when) or pd.isna(amount):
            skipped += 1
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
    return items, skipped
