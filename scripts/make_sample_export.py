"""Write a realistic bank export of Panadería La Esquina (CSV + Excel) into data/samples/.

The client can upload these on the Accounts page while the Plaid connection is pending.
Run:  uv run python -m scripts.make_sample_export
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from aheadly.data.seed_demo import DEMO_OPENING_BALANCE, build_demo_dataset

OUT = Path(__file__).resolve().parents[1] / "data" / "samples"
BASENAME = "bancolombia_export_panaderia_la_esquina"


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


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    frame = bank_export()
    frame.to_csv(OUT / f"{BASENAME}.csv", index=False)
    with pd.ExcelWriter(OUT / f"{BASENAME}.xlsx") as writer:
        frame.to_excel(writer, index=False, sheet_name="Movimientos")
        sheet = writer.sheets["Movimientos"]
        for column, width in zip("ABCDEFG", (12, 28, 24, 14, 12, 12, 12)):
            sheet.column_dimensions[column].width = width
    print(f"{len(frame)} rows -> {OUT}")


if __name__ == "__main__":
    main()
