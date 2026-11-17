"""Write the two demo upload files for Panadería La Esquina (CSV + Excel) into data/samples/.

1. A realistic bank statement (past): Date / Description / Counterparty / Category / Debit / Credit / Balance.
2. An upcoming-payments file (future): Date / Description / Amount, one-off items only, so the forecast
   does not count payroll and rent twice (those are learned from the statement).

Both are dated relative to today, so regenerate them on demo day:
    uv run python -m scripts.make_sample_export
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from aheadly.data.seed_demo import DEMO_OPENING_BALANCE, build_demo_dataset

OUT = Path(__file__).resolve().parents[1] / "data" / "samples"
STATEMENT_BASENAME = "bancolombia_export_panaderia_la_esquina"
UPCOMING_BASENAME = "upcoming_payments_panaderia_la_esquina"


def bank_export(today: date | None = None) -> pd.DataFrame:
    """Newest first, Debit / Credit split and a running Balance that ends at today's balance."""
    rows = sorted(build_demo_dataset(today).transactions, key=lambda t: (t.date, t.external_id))
    frame = pd.DataFrame(
        {
            "Date": [t.date for t in rows],
            "Description": [t.description for t in rows],
            "Counterparty": [t.counterparty for t in rows],
            "Category": [t.category for t in rows],
            "Debit": [-t.amount if t.amount < 0 else None for t in rows],
            "Credit": [t.amount if t.amount > 0 else None for t in rows],
        }
    )
    net = frame["Credit"].fillna(0) - frame["Debit"].fillna(0)
    frame["Balance"] = (DEMO_OPENING_BALANCE - net[::-1].cumsum()[::-1] + net).round(2)
    return frame.iloc[::-1].reset_index(drop=True)


def upcoming_payments(today: date | None = None) -> pd.DataFrame:
    """The owner's one-off plans: minus = money going out, plus = money coming in. Recurring items are left out."""
    items = [i for i in build_demo_dataset(today).scheduled_items if i.recurrence is None]
    items.sort(key=lambda i: i.due_date)
    return pd.DataFrame(
        {
            "Date": [i.due_date for i in items],
            "Description": [i.label for i in items],
            "Amount": [float(i.amount) for i in items],
        }
    )


def _write(frame: pd.DataFrame, basename: str, sheet: str, widths: tuple[int, ...]) -> None:
    frame.to_csv(OUT / f"{basename}.csv", index=False)
    with pd.ExcelWriter(OUT / f"{basename}.xlsx") as writer:
        frame.to_excel(writer, index=False, sheet_name=sheet)
        for column, width in zip("ABCDEFG", widths):
            writer.sheets[sheet].column_dimensions[column].width = width


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    statement = bank_export()
    _write(statement, STATEMENT_BASENAME, "Movimientos", (12, 28, 24, 14, 12, 12, 12))
    upcoming = upcoming_payments()
    _write(upcoming, UPCOMING_BASENAME, "Pagos", (12, 40, 12))
    print(f"{len(statement)} statement rows + {len(upcoming)} upcoming payments -> {OUT}")


if __name__ == "__main__":
    main()
