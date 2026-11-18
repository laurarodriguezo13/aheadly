"""Roadmap 2.5: read the files an owner keeps, whatever their layout.

An owner's Excel or CSV file is one of five kinds, told apart by its column headers (Spanish or
English), never by guessing from the values:

    upcoming_payments  payments (and income) still to come: a date and an amount
    receivables money customers owe: a due date, an amount and a customer, invoice or claim number
    employees  the staff list: names and pay (weekly, every two weeks or monthly)
    ledger     an accounting ledger: an account code, a date and an amount
    inventory  stock: an item, a quantity and a unit cost

`read_owner_file` finds the header row (titles above it are skipped), picks the kind whose columns
are all there, and reads the rows. It saves nothing: App Core shows a preview and the owner
confirms (DECISIONS #32). Only upcoming payments and receivables add money to the forecast; the
other kinds are summaries (an employee list is checked against the payroll found in the statement,
so it never counts twice).
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from io import BytesIO, StringIO

import pandas as pd

from aheadly.data.connectors.csv_connector import _decode, parse_amounts, parse_dates, plain
from aheadly.domain import ScheduledItem

KINDS = ("upcoming_payments", "receivables", "employees", "ledger", "inventory")

# role → words in a header (plain: lower case, no accents); matched as whole words
ROLES = {
    "date": ("fecha de pago", "fecha", "date", "payment date", "when", "dia"),
    "due": ("vence", "vencimiento", "due", "due date", "fecha pago esperada", "fecha esperada", "expected",
            "fecha limite", "fecha de vencimiento"),  # fmt: skip
    "issued": ("fecha factura", "issued", "fecha radicacion", "fecha de emision", "invoice date", "emitida"),
    "label": (
        "concepto",
        "item",
        "description",
        "descripcion",
        "detalle",
        "what",
        "concept",
        "motivo",
        "que",
    ),
    "payee": ("proveedor", "supplier", "vendor", "beneficiario", "acreedor", "a quien", "para quien", "pagar a",
              "pay to", "to whom", "recipient"),  # fmt: skip
    # receivables: what's still owed, what was paid, when it was paid; any file: a status column
    # ("PAGADO") that marks rows already done (DECISIONS #62)
    "remaining": ("saldo", "saldo pendiente", "pendiente", "por cobrar", "balance due", "amount due",
                  "outstanding", "remaining", "falta", "debe"),  # fmt: skip
    "paid": ("abonado", "abono", "abonos", "amount paid", "cobrado", "pagado"),
    "paid_on": (
        "pago el",
        "pagado el",
        "fecha pago real",
        "paid on",
        "date paid",
        "cobrado el",
        "fecha de cobro",
    ),
    "status": ("estado", "status", "situacion"),
    "customer": ("cliente", "client", "customer", "deudor", "aseguradora", "insurer"),
    "invoice": (
        "factura",
        "invoice",
        "siniestro",
        "claim",
        "no. siniestro",
        "documento",
        "numero de factura",
    ),
    "amount": ("monto", "valor", "amount", "importe", "total", "value", "saldo", "balance", "owed"),
    "type": ("tipo", "type", "in/out", "movimiento"),
    "name": ("nombre", "name", "empleado", "employee", "nombre completo", "trabajador"),
    "pay": ("salario", "sueldo", "pay", "salary", "wage", "pago semanal", "pago mensual", "pago quincenal",
            "monthly pay", "weekly pay"),  # fmt: skip
    "position": ("cargo", "position", "role", "puesto"),
    "account": ("cuenta", "account", "codigo cuenta", "puc"),
    "item": ("articulo", "producto", "product", "referencia", "sku", "item"),
    "quantity": ("cantidad", "quantity", "stock", "existencias", "qty", "unidades", "units"),
    "unit_cost": ("costo unitario", "unit cost", "costo", "cost", "precio unitario", "unit price"),
    "reorder": ("nivel de reorden", "reorder", "reorden", "minimo", "min stock", "punto de pedido"),
}
# kind → (roles that must all be there, roles that help)
KIND_ROLES = {
    "receivables": (("due", "amount"), ("customer", "invoice", "issued")),
    "upcoming_payments": (("date", "amount"), ("label", "payee", "type")),
    "employees": (("name", "pay"), ("position",)),
    "ledger": (("account", "date", "amount"), ("label",)),
    "inventory": (("item", "quantity", "unit_cost"), ("reorder", "payee")),
}
ROLE_NAMES = {
    "date": "date", "due": "due date", "issued": "issue date", "label": "description", "payee": "supplier",
    "customer": "customer", "invoice": "invoice number", "amount": "amount", "type": "in/out type",
    "name": "name", "pay": "pay", "position": "position", "account": "account code", "item": "item",
    "quantity": "quantity", "unit_cost": "unit cost", "reorder": "reorder level", "remaining": "amount still owed",
    "paid": "amount paid", "paid_on": "date paid", "status": "status",
}  # fmt: skip
# A budget or cash-flow sheet laid out by month (the months as columns) isn't one of the five kinds;
# it's named, not mapped column by column (DECISIONS #62; reading it is a Nice to have)
MONTH_WORDS = {
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "setiembre",
    "octubre", "noviembre", "diciembre", "ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep",
    "sept", "set", "oct", "nov", "dic", "january", "february", "march", "april", "june", "july", "august",
    "september", "october", "november", "december", "jan", "apr", "aug", "dec",
}  # fmt: skip
BUDGET_PROBLEM = (
    "This looks like a budget or cash-flow plan laid out by month (the months are the columns). Aheadly "
    "doesn't use this kind of file yet: your statement already shows the months gone by. Skip it, and put "
    "the payments still to come in an upcoming-payments file or under Just say it."
)
PAID_WORDS = (
    "pagado",
    "pagada",
    "paid",
    "cancelado",
    "cancelada",
    "cobrado",
    "cobrada",
    "listo",
    "hecho",
    "done",
)
MONTH_NUMBERS = {
    "ene": 1, "enero": 1, "jan": 1, "january": 1, "feb": 2, "febrero": 2, "february": 2, "mar": 3, "marzo": 3,
    "march": 3, "abr": 4, "abril": 4, "apr": 4, "april": 4, "may": 5, "mayo": 5, "jun": 6, "junio": 6,
    "june": 6, "jul": 7, "julio": 7, "july": 7, "ago": 8, "agosto": 8, "aug": 8, "august": 8, "sep": 9,
    "sept": 9, "set": 9, "septiembre": 9, "setiembre": 9, "september": 9, "oct": 10, "octubre": 10,
    "october": 10, "nov": 11, "noviembre": 11, "november": 11, "dic": 12, "diciembre": 12, "dec": 12,
    "december": 12,
}  # fmt: skip
ROUGHLY = re.compile(
    r"^(~|aprox\.?|approx\.?|aproximadamente|around|about|como el|como|alrededor del?|c\.)\s*"
)
IN_TYPES = ("ingreso", "income", "in", "cobro", "entrada", "credito", "abono", "recibo")
DOUBTFUL_DAYS = 60  # an invoice this late is listed but not counted on
LATE_PAYMENT_DAYS = 14  # an overdue invoice is expected this long from today, as a maybe


@dataclass
class OwnerFile:
    name: str
    kind: str | None  # None: the columns didn't say (the owner picks)
    rows: int = 0
    total: float = 0.0  # upcoming: net (in − out); receivables: owed; employees: pay per period;
    # ledger: balance; inventory: stock value at cost
    overdue_rows: int = 0
    columns: dict[str, str] = field(default_factory=dict)  # role → the file's header
    headers: list[str] = field(default_factory=list)
    items: list[ScheduledItem] = field(default_factory=list)  # what it adds to the forecast
    details: dict = field(default_factory=dict)
    problem: str | None = None


# ------------------------------------------------------------- the table
def read_grids(content: bytes, filename: str) -> list[pd.DataFrame]:
    """Every sheet of an Excel file (a cover sheet often comes first), or the one grid of a CSV."""
    if filename.lower().endswith((".xlsx", ".xls")):
        sheets = pd.read_excel(BytesIO(content), header=None, sheet_name=None)
        return [grid.dropna(how="all") for grid in sheets.values()]
    return [read_grid(content, filename)]


def read_grid(content: bytes, filename: str) -> pd.DataFrame:
    """The file as a grid of cells, no header assumed (CSV: comma, semicolon or tab)."""
    if filename.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(BytesIO(content), header=None)
    text = _decode(content)
    first_lines = text.splitlines()[:30]
    sep = max((",", ";", "\t"), key=lambda s: sum(line.count(s) for line in first_lines))
    # rows of different lengths (a title line above the header): pad them instead of failing
    rows = [
        [cell if cell.strip() else None for cell in row] for row in csv.reader(StringIO(text), delimiter=sep)
    ]
    width = max((len(r) for r in rows), default=0)
    return pd.DataFrame([r + [None] * (width - len(r)) for r in rows if any(c for c in r)], dtype=object)


def _has(header: str, words: tuple[str, ...]) -> bool:
    text = f" {plain(header)} "
    return any(f" {w} " in text or text.strip() == w for w in words)


def match_roles(headers: list[str]) -> dict[str, str]:
    """Each role → the first header that names it (a header serves one role; specific roles first)."""
    order = ["due", "issued", "paid_on", "pay", "unit_cost", "reorder", "invoice", "customer", "payee", "name",
             "item", "quantity", "account", "type", "position", "status", "date", "label", "paid", "amount",
             "remaining"]  # fmt: skip
    found: dict[str, str] = {}
    for role in order:
        for header in headers:
            if header not in found.values() and _has(header, ROLES[role]):
                found[role] = header
                break
    if "amount" not in found and "remaining" in found:  # a file whose only amount is what's owed
        found["amount"] = found.pop("remaining")
    return found


def _role_words(row) -> int:
    cells = [str(c) for c in row if pd.notna(c) and str(c).strip()]
    return sum(1 for c in cells if any(_has(c, words) for words in ROLES.values()))


def _header_row(grid: pd.DataFrame) -> int | None:
    """The first of the top rows with at least two cells that name a role; else the first row with
    two or more filled cells (titles we don't know: the owner or the assistant says what they are)."""
    filled = [i for i in range(min(15, len(grid))) if grid.iloc[i].notna().sum() >= 2]
    for i in filled:
        if _role_words(grid.iloc[i]) >= 2:
            return i
    return filled[0] if filled else None


def _looks_like_data(row) -> bool:
    """A first row that holds amounts or dates, not titles: the file has no title row."""

    def is_value(cell) -> bool:
        if not isinstance(cell, str):
            return True  # a number or a date cell
        text = cell.strip()
        if not any(ch.isdigit() for ch in text):
            return False
        return pd.notna(parse_amounts(pd.Series([text]))[0]) or pd.notna(parse_dates(pd.Series([text]))[0])

    cells = [c for c in row if pd.notna(c) and str(c).strip()]
    return _role_words(row) == 0 and any(is_value(c) for c in cells)


def _best_sheet(grids: list[pd.DataFrame]) -> tuple[pd.DataFrame, int | None]:
    """The sheet whose title row names the most roles (ties: the first)."""
    best, best_start, best_score = None, None, -1
    for grid in grids:
        start = _header_row(grid)
        score = _role_words(grid.iloc[start]) if start is not None else -1
        if score > best_score:
            best, best_start, best_score = grid, start, score
    return best if best is not None else pd.DataFrame(), best_start


TOTAL_WORDS = ("total", "totales", "subtotal", "sub total", "suma", "gran total", "grand total", "sum")


def _total_rows(table: pd.DataFrame) -> pd.Series:
    """Rows that add up the others ("TOTAL", "Subtotal", "Suma"): never an item or a person."""

    def is_total(row) -> bool:
        texts = [plain(str(c)).strip(" :") for c in row if isinstance(c, str) and c.strip()]
        return any(t in TOTAL_WORDS or t.startswith(("total ", "subtotal ")) for t in texts)

    return table.apply(is_total, axis=1) if len(table) else pd.Series([], dtype=bool)


def pick_kind(columns: dict[str, str]) -> str | None:
    """The kind whose required columns are all there; ties go to the one with more helpful columns."""
    scores = {}
    for kind, (required, helpful) in KIND_ROLES.items():
        if all(role in columns for role in required):
            scores[kind] = len(required) * 2 + sum(1 for role in helpful if role in columns)
    if "receivables" in scores and not ({"customer", "invoice"} & set(columns)):
        scores.pop("receivables")
    return max(scores, key=scores.get) if scores else None


# ------------------------------------------------------------- reading
def read_owner_file(
    content: bytes, filename: str, today: date, kind: str | None = None, columns_hint: dict | None = None
) -> OwnerFile:
    """Read an owner's file. `kind` forces a kind the owner picked; otherwise the headers decide.
    `columns_hint` (role → header, from the assistant) fills roles the header words didn't."""
    try:
        grid, start = _best_sheet(read_grids(content, filename))
    except Exception as exc:  # a file pandas can't open at all
        return OwnerFile(filename, None, problem=f"We couldn't open this file ({exc.__class__.__name__}).")
    if start is None:
        return OwnerFile(filename, None, problem="We couldn't find anything to read in this file.")
    first = grid.iloc[start]
    if _looks_like_data(first):  # no title row: name the columns by position and keep that row
        headers = [f"Column {j + 1}" for j in range(len(first))]
        table = grid.iloc[start:].copy()
    else:
        headers = [str(c).strip() if pd.notna(c) else f"Column {j + 1}" for j, c in enumerate(first)]
        table = grid.iloc[start + 1 :].copy()
    if kind is None and months_as_columns(headers):
        return OwnerFile(
            filename, None, headers=headers, problem=BUDGET_PROBLEM, details={"looks_like": "budget_by_month"}
        )
    table.columns = headers
    table = table.dropna(how="all")
    totals = _total_rows(table)
    table = table[~totals]
    columns = match_roles(headers)
    for role, header in (columns_hint or {}).items():
        if role in ROLES and header in headers and header not in columns.values():
            columns.setdefault(role, header)
    chosen = kind or pick_kind(columns)
    result = OwnerFile(filename, chosen, columns=columns, headers=headers)
    result.details["samples"] = {h: _sample(table[h]) for h in headers}
    result.details["total_rows"] = int(totals.sum())
    if chosen is None:
        result.problem = "We're not sure what this file is. Pick what it is below."
        return result
    required = KIND_ROLES[chosen][0]
    missing = [role for role in required if role not in columns]
    if missing:
        result.details["missing_roles"] = missing
        names = ", ".join(ROLE_NAMES[r] for r in missing)
        result.problem = f"Which column has the {names}? Pick it below."
        return result
    READERS[chosen](table, columns, today, result)
    if chosen == "upcoming_payments" and result.rows and not result.items:
        balance = [h for h in headers if h != columns.get("amount") and _has(h, ("saldo", "balance"))]
        if balance or result.rows >= 20:
            result.problem = (
                "This looks like a bank statement (a balance column, and every date has passed). "
                "Add it with your bank statements instead."
            )
    return result


def months_as_columns(headers: list[str]) -> bool:
    """Three or more column titles that are months ("Enero", "Feb 2026", "2026-03")."""
    months = 0
    for header in headers:
        words = plain(header).replace("-", " ").replace("/", " ").split()
        if words and (words[0] in MONTH_WORDS or (len(words) == 2 and words[1] in MONTH_WORDS)):
            months += 1
    return months >= 3


def _sample(values: pd.Series) -> str:
    """A value from the column, to help the owner tell columns apart in the picker."""
    filled = [str(v) for v in values if pd.notna(v) and str(v).strip()]
    return filled[0][:20] if filled else ""


def _amounts(table: pd.DataFrame, header: str) -> pd.Series:
    return parse_amounts(table[header])


def _dates(table: pd.DataFrame, header: str) -> pd.Series:
    return parse_dates(table[header]).dt.date


def loose_date(text: str, today: date) -> tuple[date | None, bool]:
    """A date written by hand: "~10 dic", "aprox. 22 de diciembre", "Dec 3", or a month alone ("ene":
    the 15th, and only roughly). The year is the one that puts it ahead (or at most two months back).
    Returns (date, month_only); (None, False) when it can't be read."""
    words = plain(text)
    words = re.sub(r"[,./-]", " ", ROUGHLY.sub("", words)).strip()
    found = re.fullmatch(r"(\d{1,2})\s*(?:de\s+)?([a-z]+)(?:\s+(\d{4}))?", words) or re.fullmatch(
        r"([a-z]+)\s+(\d{1,2})(?:\s+(\d{4}))?", words
    )
    month_only = False
    if found:
        first, second, year = found.groups()
        day_, month = (int(first), MONTH_NUMBERS.get(second)) if first.isdigit() else (
            int(second), MONTH_NUMBERS.get(first))  # fmt: skip
    elif words in MONTH_NUMBERS:
        day_, month, year, month_only = 15, MONTH_NUMBERS[words], None, True
    else:
        return None, False
    if month is None:
        return None, False
    try:
        when = date(int(year) if year else today.year, month, day_)
    except ValueError:
        return None, False
    if not year and when < today - timedelta(days=62):
        when = when.replace(year=when.year + 1)
    return when, month_only


def _hand_dates(table: pd.DataFrame, header: str, today: date) -> tuple[pd.Series, pd.Series]:
    """Dates, with the ones written by hand read too; and which of them were only a month."""
    dates = _dates(table, header)
    month_only = pd.Series(False, index=table.index)
    for i in table.index:
        raw = table.at[i, header]
        # text with a month's name ("~10 dic", "ene"): read by hand, never as Jan 1 of this year
        if isinstance(raw, str) and re.search(r"[a-zA-Z]", raw) and not re.search(r"\d{4}", raw):
            when, rough = loose_date(raw, today)
            if when:
                dates.at[i] = when
                month_only.at[i] = rough
    sensible = dates.map(lambda d: d is not None and not pd.isna(d) and d.year >= 1990)
    return dates.where(sensible), month_only  # "30-nov" once came out as a date 2,000 years ago


def _done(table: pd.DataFrame, columns: dict) -> pd.Series:
    """Rows a status column marks as paid or done."""
    status = _text(table, columns.get("status")).map(plain)
    return status.map(lambda s: any(s.startswith(w) for w in PAID_WORDS))


def _text(table: pd.DataFrame, header: str | None) -> pd.Series:
    if header is None:
        return pd.Series([""] * len(table), index=table.index)
    return table[header].fillna("").astype(str).str.strip()


def _read_upcoming(table, columns, today, result: OwnerFile) -> None:
    amounts = _amounts(table, columns["amount"])
    dates, month_only = _hand_dates(table, columns["date"], today)
    done = _done(table, columns)
    ok = amounts.notna() & dates.notna() & ~done
    types = _text(table, columns.get("type")).map(plain)
    labels = _text(table, columns.get("label") or columns.get("item"))
    payees = _text(table, columns.get("payee"))
    mixed_signs = (amounts[ok] < 0).any() and (amounts[ok] > 0).any()
    for i in table.index[ok]:
        amount = float(amounts[i])
        if columns.get("type"):
            sign = 1 if types[i].startswith(IN_TYPES) else -1
            amount = sign * abs(amount)
        elif not mixed_signs:
            amount = -abs(amount)  # a list of what's due: every row is a payment
        label = " – ".join(x for x in (payees[i], labels[i]) if x) or "Upcoming payment"
        certainty = "maybe" if month_only[i] else "confirmed"
        result.items.append(_item(label, amount, dates[i], today, result.name, certainty=certainty))
    result.rows = int(ok.sum())
    result.total = round(sum(i.amount for i in result.items), 2)
    result.details["skipped"] = int((~ok & ~done).sum())
    result.details["done"] = int(done.sum())
    result.items = [i for i in result.items if i.due_date >= today]
    result.details["already_past"] = result.rows - len(result.items)


def _read_receivables(table, columns, today, result: OwnerFile) -> None:
    amounts = _amounts(table, columns["amount"]).abs()
    if columns.get("remaining"):  # what's still owed, when the file says
        amounts = _amounts(table, columns["remaining"]).fillna(0).abs()
    elif columns.get("paid"):
        amounts = amounts - _amounts(table, columns["paid"]).fillna(0).abs()
    paid_off = _done(table, columns) | (amounts.round(2) <= 0)
    if columns.get("paid_on") and not columns.get("remaining") and not columns.get("paid"):
        paid_off |= _text(table, columns["paid_on"]) != ""  # a paid date and nothing else to go by
    dues, _ = _hand_dates(table, columns["due"], today)
    ok = amounts.notna() & dues.notna() & ~paid_off
    who = _text(table, columns.get("customer"))
    numbers = _text(table, columns.get("invoice"))
    doubtful = []
    for i in table.index[ok]:
        amount, due = abs(float(amounts[i])), dues[i]
        label = " – ".join(x for x in (who[i], numbers[i]) if x) or "Invoice"
        late = (today - due).days
        if late > DOUBTFUL_DAYS:
            doubtful.append({"label": label, "amount": amount, "days_late": late})
            result.overdue_rows += 1
            continue
        if late > 0:
            result.overdue_rows += 1
            result.items.append(
                _item(f"{label} (overdue)", amount, today + timedelta(days=LATE_PAYMENT_DAYS), today, result.name,
                      certainty="maybe")
            )  # fmt: skip
        else:
            result.items.append(_item(label, amount, due, today, result.name))
    result.rows = int(ok.sum())
    result.total = round(float(amounts[ok].abs().sum()), 2)
    result.details["doubtful"] = doubtful
    result.details["skipped"] = int((~ok & ~paid_off).sum())
    result.details["paid_off"] = int(paid_off.sum())


def _read_employees(table, columns, today, result: OwnerFile) -> None:
    pay = _amounts(table, columns["pay"])
    names = _text(table, columns["name"])
    ok = pay.notna() & (names != "")
    header = plain(columns["pay"])
    period = (
        "weekly" if any(w in header for w in ("semanal", "weekly", "week", "semana"))
        else "every two weeks" if any(w in header for w in ("quincenal", "biweekly", "two weeks"))
        else "monthly"
    )  # fmt: skip
    result.rows = int(ok.sum())
    result.total = round(float(pay[ok].sum()), 2)
    result.details["skipped"] = int((~ok).sum())
    result.details["period"] = period
    result.details["per_month"] = round(result.total * PER_MONTH[period], 2)


def _read_ledger(table, columns, today, result: OwnerFile) -> None:
    amounts = _amounts(table, columns["amount"])
    ok = amounts.notna()
    result.rows = int(ok.sum())
    result.total = round(float(amounts[ok].sum()), 2)
    result.details["skipped"] = int((~ok).sum())


def _read_inventory(table, columns, today, result: OwnerFile) -> None:
    quantity = _amounts(table, columns["quantity"])
    cost = _amounts(table, columns["unit_cost"])
    ok = quantity.notna() & cost.notna()
    result.rows = int(ok.sum())
    result.details["skipped"] = int((~ok).sum())
    result.total = round(float((quantity[ok] * cost[ok]).sum()), 2)
    if columns.get("reorder"):
        reorder = _amounts(table, columns["reorder"])
        low = ok & reorder.notna() & (quantity < reorder)
        items = _text(table, columns["item"])
        result.details["below_reorder"] = [items[i] for i in table.index[low]]


def _item(label, amount, due, today, filename, certainty="confirmed") -> ScheduledItem:
    from aheadly.ai.categorizer import by_keywords  # (here: categorizer reads this package)

    return ScheduledItem(
        label=label[:80],
        amount=round(float(amount), 2),
        due_date=due,
        kind="receivable" if amount > 0 else "bill",
        source=f"file:{filename}"[:60],
        status="user",
        certainty=certainty,
        # what the name says (DECISIONS #63): a tax or payroll line from a file is never offered to move
        category=by_keywords(label, amount),
    )


PER_MONTH = {"weekly": 52 / 12, "every two weeks": 26 / 12, "monthly": 1.0}
READERS = {
    "upcoming_payments": _read_upcoming,
    "receivables": _read_receivables,
    "employees": _read_employees,
    "ledger": _read_ledger,
    "inventory": _read_inventory,
}
