"""Data Repository: the only module that speaks SQL.

Every other component asks the repository for domain objects or pandas frames
and never sees a cursor. One business per database for the MVP.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from typing import Iterable

import pandas as pd

from aheadly.domain import (
    Alert,
    Business,
    ForecastPoint,
    ForecastResult,
    ScheduledItem,
    Transaction,
)

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# Numbered upgrades on top of schema.sql. A database remembers how many it has (PRAGMA user_version),
# so an older file (a local database, or a saved file loaded later) upgrades itself when opened.
# Never edit or reorder a step that has shipped: add a new one at the end.
MIGRATIONS: list[list[str]] = [
    # 1 · roadmap 1.4: groundwork for understanding a business from its own files
    [
        "CREATE TABLE business_profile (business_id INTEGER PRIMARY KEY, "
        "profile_json TEXT NOT NULL DEFAULT '{}', updated_at TEXT)",
        "ALTER TABLE scheduled_items ADD COLUMN status TEXT DEFAULT 'user'",
        "ALTER TABLE scheduled_items ADD COLUMN certainty TEXT DEFAULT 'confirmed'",
        "ALTER TABLE scheduled_items ADD COLUMN likelihood REAL DEFAULT 1.0",
        "ALTER TABLE scheduled_items ADD COLUMN category TEXT",
        "ALTER TABLE scheduled_items ADD COLUMN match_key TEXT",
        "ALTER TABLE scheduled_items ADD COLUMN end_date TEXT",
        "ALTER TABLE scheduled_items ADD COLUMN user_edited INTEGER DEFAULT 0",
        "ALTER TABLE scheduled_items ADD COLUMN paused INTEGER DEFAULT 0",
        "ALTER TABLE transactions ADD COLUMN scheduled_item_id INTEGER",
        "ALTER TABLE transactions ADD COLUMN category_source TEXT DEFAULT 'bank'",
        "ALTER TABLE transactions ADD COLUMN is_internal_transfer INTEGER DEFAULT 0",
        "ALTER TABLE accounts ADD COLUMN kind TEXT DEFAULT 'bank'",
        "ALTER TABLE accounts ADD COLUMN currency TEXT DEFAULT 'USD'",
        "ALTER TABLE forecast_runs ADD COLUMN chance_below_line REAL",
        "CREATE TABLE payee_rules (id INTEGER PRIMARY KEY, business_id INTEGER, match_key TEXT, "
        "category TEXT, label TEXT, created_at TEXT, UNIQUE (business_id, match_key))",
        "CREATE TABLE insights (id INTEGER PRIMARY KEY, business_id INTEGER, run_id INTEGER, type TEXT, "
        "severity TEXT, facts_json TEXT, title TEXT, body TEXT, actions_json TEXT, created_at TEXT, "
        "dismissed INTEGER DEFAULT 0, resolved INTEGER DEFAULT 0)",
        "CREATE TABLE uploaded_files (id INTEGER PRIMARY KEY, business_id INTEGER, name TEXT, "
        "detected_type TEXT, mapping_json TEXT, confirmed INTEGER DEFAULT 0, uploaded_at TEXT)",
    ],
]


def _now() -> str:
    """Stored in UTC; the UI shows it in the visitor's own time zone."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Repository:
    """Thin, explicit data-access layer over SQLite (standard library only)."""

    def __init__(self, db_path: Path | str = ":memory:"):
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA_PATH.read_text())
        self._migrate()

    def schema_version(self) -> int:
        return int(self._conn.execute("PRAGMA user_version").fetchone()[0])

    def _migrate(self) -> None:
        """Apply the upgrades this database doesn't have yet, each one all-or-nothing."""
        current = self.schema_version()
        for number, steps in enumerate(MIGRATIONS[current:], start=current + 1):
            with self._conn:
                for statement in steps:
                    self._conn.execute(statement)
                self._conn.execute(f"PRAGMA user_version = {int(number)}")

    # ---------------------------------------------------------------- profile
    def get_profile(self, business_id: int) -> dict:
        """What the owner told us about the business (type, payment terms, time zone...)."""
        row = self._conn.execute(
            "SELECT profile_json FROM business_profile WHERE business_id=?", (business_id,)
        ).fetchone()
        return json.loads(row["profile_json"]) if row else {}

    def save_profile(self, business_id: int, changes: dict) -> dict:
        """Merge `changes` into the profile and return the result."""
        profile = {**self.get_profile(business_id), **changes}
        self._conn.execute(
            "INSERT INTO business_profile (business_id, profile_json, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(business_id) DO UPDATE SET profile_json=excluded.profile_json, "
            "updated_at=excluded.updated_at",
            (business_id, json.dumps(profile), _now()),
        )
        self._conn.commit()
        return profile

    # ---------------------------------------------------------------- business
    def get_business(self) -> Business | None:
        row = self._conn.execute("SELECT * FROM businesses ORDER BY id LIMIT 1").fetchone()
        return self._row_to_business(row) if row else None

    def create_business(self, name: str, owner_name: str, city: str, low_cash_line: float) -> Business:
        cur = self._conn.execute(
            "INSERT INTO businesses (name, owner_name, city, low_cash_line) VALUES (?,?,?,?)",
            (name, owner_name, city, low_cash_line),
        )
        self._conn.commit()
        return Business(cur.lastrowid, name, owner_name, city, low_cash_line=low_cash_line)

    def update_low_cash_line(self, business_id: int, value: float) -> None:
        self._conn.execute("UPDATE businesses SET low_cash_line=? WHERE id=?", (value, business_id))
        self._conn.commit()

    @staticmethod
    def _row_to_business(row: sqlite3.Row) -> Business:
        return Business(
            id=row["id"],
            name=row["name"],
            owner_name=row["owner_name"],
            city=row["city"],
            currency=row["currency"],
            low_cash_line=row["low_cash_line"],
        )

    # ---------------------------------------------------------------- accounts
    def add_account(
        self, business_id: int, source: str, name: str, balance: float, kind: str = "bank"
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO accounts (business_id, source, name, balance, last_synced_at, kind) VALUES (?,?,?,?,?,?)",
            (business_id, source, name, balance, _now(), kind),
        )
        self._conn.commit()
        return cur.lastrowid

    def list_accounts(self, business_id: int) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM accounts WHERE business_id=?", (business_id,)).fetchall()
        return [dict(r) for r in rows]

    def current_balance(self, business_id: int) -> float:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(balance), 0) AS total FROM accounts "
            "WHERE business_id=? AND COALESCE(kind, 'bank')='bank'",
            (business_id,),
        ).fetchone()
        return float(row["total"])  # cash in the bank; a card's balance is debt, not cash

    def set_account_balance(self, account_id: int, balance: float) -> None:
        self._conn.execute(
            "UPDATE accounts SET balance=?, last_synced_at=? WHERE id=?", (balance, _now(), account_id)
        )
        self._conn.commit()

    def account_last_date(self, account_id: int) -> date | None:
        row = self._conn.execute(
            "SELECT MAX(date) AS last FROM transactions WHERE account_id=?", (account_id,)
        ).fetchone()
        return date.fromisoformat(row["last"]) if row["last"] else None

    def account_with_any(self, business_id: int, external_ids: list[str]) -> int | None:
        """The account that already has some of these transactions (an overlapping statement of it)."""
        for start in range(0, len(external_ids), 500):
            chunk = external_ids[start : start + 500]
            row = self._conn.execute(
                f"SELECT account_id, COUNT(*) AS n FROM transactions WHERE business_id=? "
                f"AND external_id IN ({','.join('?' * len(chunk))}) GROUP BY account_id ORDER BY n DESC LIMIT 1",
                (business_id, *chunk),
            ).fetchone()
            if row:
                return int(row["account_id"])
        return None

    def transfer_candidates(self, business_id: int) -> list[tuple]:
        """(id, account_id, account kind, date, amount) of every line not yet marked as a transfer."""
        rows = self._conn.execute(
            "SELECT t.id, t.account_id, COALESCE(a.kind, 'bank') AS kind, t.date, t.amount "
            "FROM transactions t JOIN accounts a ON a.id = t.account_id "
            "WHERE t.business_id=? AND COALESCE(t.is_internal_transfer, 0)=0",
            (business_id,),
        ).fetchall()
        return [
            (r["id"], r["account_id"], r["kind"], date.fromisoformat(r["date"]), r["amount"]) for r in rows
        ]

    def internal_transfer_counts(self, business_id: int) -> dict[str, int]:
        """How many transfers between the owner's own accounts (pairs), and card payments (pairs)."""
        row = self._conn.execute(
            "SELECT COALESCE(SUM(CASE WHEN COALESCE(category, '') != 'card_payment' THEN 1 END), 0) AS transfers, "
            "COALESCE(SUM(CASE WHEN category = 'card_payment' THEN 1 END), 0) AS card "
            "FROM transactions WHERE business_id=? AND is_internal_transfer=1",
            (business_id,),
        ).fetchone()
        return {"transfers": int(row["transfers"]) // 2, "card_payments": int(row["card"]) // 2}

    def mark_internal_transfers(self, transfer_ids: list[int], card_payment_ids: list[int]) -> None:
        """Both sides of a move between the owner's own accounts; card payments also get their category."""
        self._conn.executemany(
            "UPDATE transactions SET is_internal_transfer=1 WHERE id=?", [(i,) for i in transfer_ids]
        )
        self._conn.executemany(
            "UPDATE transactions SET category='card_payment', category_source='rule' WHERE id=?",
            [(i,) for i in card_payment_ids],
        )
        self._conn.commit()

    # ------------------------------------------------------------ categories (roadmap 2.2)
    def categorization_lines(self, business_id: int) -> list[tuple]:
        """(id, description, amount, category, category_source, is_internal_transfer) for every line."""
        return [
            tuple(r)
            for r in self._conn.execute(
                "SELECT id, description, amount, category, category_source, "
                "COALESCE(is_internal_transfer, 0) FROM transactions WHERE business_id=?",
                (business_id,),
            )
        ]

    def set_categories(self, updates: list[tuple[str, str, int]]) -> None:
        """(category, source, transaction id) for each line whose category changed."""
        self._conn.executemany("UPDATE transactions SET category=?, category_source=? WHERE id=?", updates)
        self._conn.commit()

    def payee_rules(self, business_id: int) -> list[tuple[str, str]]:
        """(match_key, category) for each answer the owner gave, newest first."""
        return [
            (r["match_key"], r["category"])
            for r in self._conn.execute(
                "SELECT match_key, category FROM payee_rules WHERE business_id=? ORDER BY id DESC",
                (business_id,),
            )
        ]

    def record_uploaded_file(self, business_id: int, name: str, kind: str, mapping: dict) -> None:
        """An owner's file they confirmed (roadmap 2.5): its name, kind and which column was what."""
        self._conn.execute(
            "INSERT INTO uploaded_files (business_id, name, detected_type, mapping_json, confirmed, uploaded_at) "
            "VALUES (?,?,?,?,1,?)",
            (business_id, name, kind, json.dumps(mapping, ensure_ascii=False), _now()),
        )
        self._conn.commit()

    def uploaded_files(self, business_id: int) -> list[dict]:
        return [
            {"name": r["name"], "kind": r["detected_type"], "uploaded_at": r["uploaded_at"]}
            for r in self._conn.execute(
                "SELECT name, detected_type, uploaded_at FROM uploaded_files WHERE business_id=? ORDER BY id",
                (business_id,),
            )
        ]

    def save_payee_rule(self, business_id: int, match_key: str, category: str, label: str = "") -> None:
        self._conn.execute(
            "INSERT INTO payee_rules (business_id, match_key, category, label, created_at) VALUES (?,?,?,?,?) "
            "ON CONFLICT(business_id, match_key) DO UPDATE SET category=excluded.category, "
            "label=excluded.label, created_at=excluded.created_at",
            (business_id, match_key, category, label, _now()),
        )
        self._conn.commit()

    def monthly_category_totals(self, business_id: int) -> dict[str, dict[str, float]]:
        """{'2026-10': {'sales': 16373.67, 'payroll': -6656.0, ...}}: signed sums per month. For a move
        between the owner's own accounts only the sending side counts (the money left once)."""
        totals: dict[str, dict[str, float]] = {}
        for r in self._conn.execute(
            "SELECT substr(date, 1, 7) AS month, COALESCE(category, 'other') AS category, "
            "SUM(amount) AS total FROM transactions WHERE business_id=? "
            "AND NOT (COALESCE(is_internal_transfer, 0)=1 AND amount > 0) "
            "GROUP BY month, category ORDER BY month",
            (business_id,),
        ):
            totals.setdefault(r["month"], {})[r["category"]] = round(r["total"], 2)
        return totals

    def category_total(self, business_id: int, category: str, start: date, end: date) -> float:
        """Signed sum of one category from `start` up to (not including) `end`."""
        row = self._conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM transactions WHERE business_id=? "
            "AND category=? AND date >= ? AND date < ? AND COALESCE(is_internal_transfer, 0)=0",
            (business_id, category, start.isoformat(), end.isoformat()),
        ).fetchone()
        return float(row["total"])

    # ------------------------------------------------------------ transactions
    def add_transactions(self, business_id: int, account_id: int, transactions: list[Transaction]) -> int:
        rows = [
            (
                business_id,
                account_id,
                t.external_id,
                t.date.isoformat(),
                t.amount,
                t.description,
                t.category,
                t.counterparty,
                t.source,
            )
            for t in transactions
        ]
        cur = self._conn.executemany(
            "INSERT OR IGNORE INTO transactions (business_id, account_id, external_id, date, amount, "
            "description, category, counterparty, source) VALUES (?,?,?,?,?,?,?,?,?)",
            rows,
        )
        self._conn.commit()
        return cur.rowcount

    def last_transaction_date(self, business_id: int) -> date | None:
        row = self._conn.execute(
            "SELECT MAX(date) AS last FROM transactions WHERE business_id=?", (business_id,)
        ).fetchone()
        return date.fromisoformat(row["last"]) if row["last"] else None

    def list_transactions(
        self, business_id: int, since: date | None = None, category: str | None = None, limit: int = 50
    ) -> pd.DataFrame:
        query = (
            "SELECT date, description, category, counterparty, amount FROM transactions WHERE business_id=?"
        )
        params: list = [business_id]
        if since is not None:
            query += " AND date >= ?"
            params.append(since.isoformat())
        if category:
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY date DESC, id DESC LIMIT ?"
        params.append(limit)
        return pd.read_sql_query(query, self._conn, params=params)

    def daily_net_flow(
        self, business_id: int, exclude_categories: Iterable[str] = (), exclude_linked: bool = False
    ) -> pd.DataFrame:
        """Daily sum of transactions as a continuous series (missing days = 0).

        With `exclude_linked`, lines linked to a scheduled item (a recurring payment found in the
        statement, roadmap 2.3) are left out: the forecast puts them back on their own dates, so they are never counted
        twice. `exclude_categories` does the same by category for the demo data's items.
        """
        query = (
            "SELECT date, SUM(amount) AS net_flow FROM transactions "
            "WHERE business_id=? AND COALESCE(is_internal_transfer, 0)=0"
        )
        if exclude_linked:
            query += " AND scheduled_item_id IS NULL"
        params: list = [business_id]
        excluded = sorted(set(exclude_categories))
        if excluded:
            query += f" AND category NOT IN ({','.join('?' * len(excluded))})"
            params.extend(excluded)
        query += " GROUP BY date ORDER BY date"
        df = pd.read_sql_query(query, self._conn, params=params, parse_dates=["date"])
        span = self._conn.execute(
            "SELECT MIN(date) AS first, MAX(date) AS last FROM transactions WHERE business_id=?",
            (business_id,),
        ).fetchone()
        if span["first"] is None:
            return df
        # the whole statement period, so days whose lines are all forecast elsewhere count as 0
        full_index = pd.date_range(span["first"], span["last"], freq="D")
        if df.empty:
            return pd.DataFrame({"date": full_index, "net_flow": 0.0})
        return df.set_index("date").reindex(full_index, fill_value=0.0).rename_axis("date").reset_index()

    def flow_totals(self, business_id: int, since: date) -> dict[str, float]:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(CASE WHEN amount > 0 THEN amount END), 0) AS money_in, "
            "COALESCE(SUM(CASE WHEN amount < 0 THEN -amount END), 0) AS money_out "
            "FROM transactions WHERE business_id=? AND date >= ? AND COALESCE(is_internal_transfer, 0)=0",
            (business_id, since.isoformat()),
        ).fetchone()
        return {"money_in": float(row["money_in"]), "money_out": float(row["money_out"])}

    # --------------------------------------------------------- scheduled items
    def add_scheduled_items(self, business_id: int, items: list[ScheduledItem]) -> None:
        self._conn.executemany(
            "INSERT INTO scheduled_items (business_id, kind, label, amount, due_date, recurrence, source, "
            "active, status, certainty, likelihood, category, match_key, end_date, user_edited, paused) "
            "VALUES (?,?,?,?,?,?,?,1,?,?,?,?,?,?,?,?)",
            [
                (
                    business_id,
                    i.kind,
                    i.label,
                    i.amount,
                    i.due_date.isoformat(),
                    i.recurrence,
                    i.source,
                    i.status,
                    i.certainty,
                    i.likelihood,
                    i.category,
                    i.match_key,
                    i.end_date.isoformat() if i.end_date else None,
                    int(i.user_edited),
                    int(i.paused),
                )
                for i in items
            ],
        )
        self._conn.commit()

    def list_scheduled_items(self, business_id: int) -> list[ScheduledItem]:
        rows = self._conn.execute(
            "SELECT * FROM scheduled_items WHERE business_id=? AND active=1 ORDER BY due_date", (business_id,)
        ).fetchall()
        return [self._scheduled_from_row(r) for r in rows]

    @staticmethod
    def _scheduled_from_row(r) -> ScheduledItem:
        return ScheduledItem(
            id=r["id"],
            label=r["label"],
            amount=r["amount"],
            due_date=date.fromisoformat(r["due_date"]),
            kind=r["kind"],
            recurrence=r["recurrence"],
            source=r["source"],
            active=bool(r["active"]),
            status=r["status"] or "user",
            certainty=r["certainty"] or "confirmed",
            likelihood=1.0 if r["likelihood"] is None else float(r["likelihood"]),
            category=r["category"],
            match_key=r["match_key"],
            end_date=date.fromisoformat(r["end_date"]) if r["end_date"] else None,
            user_edited=bool(r["user_edited"]),
            paused=bool(r["paused"]),
        )

    def replace_scheduled_items(self, business_id: int, items: list[ScheduledItem]) -> None:
        """Used when a scenario is saved as the plan. Statement lines linked to an item stay linked
        to its new copy. An item the plan removes is kept, switched off: its lines stay out of the
        history, so removing rent from the plan really removes it."""
        self._conn.execute("UPDATE scheduled_items SET active=0 WHERE business_id=?", (business_id,))
        for item in items:
            new_id = self._insert_scheduled_item(business_id, item)
            if item.id is not None:
                self._conn.execute(
                    "UPDATE transactions SET scheduled_item_id=? WHERE scheduled_item_id=?", (new_id, item.id)
                )
        self._conn.commit()

    def _insert_scheduled_item(self, business_id: int, i: ScheduledItem) -> int:
        cur = self._conn.execute(
            "INSERT INTO scheduled_items (business_id, kind, label, amount, due_date, recurrence, source, "
            "active, status, certainty, likelihood, category, match_key, end_date, user_edited, paused) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                business_id,
                i.kind,
                i.label,
                i.amount,
                i.due_date.isoformat(),
                i.recurrence,
                i.source,
                int(i.active),
                i.status,
                i.certainty,
                i.likelihood,
                i.category,
                i.match_key,
                i.end_date.isoformat() if i.end_date else None,
                int(i.user_edited),
                int(i.paused),
            ),
        )
        return cur.lastrowid

    # ------------------------------------------------------- the forecast's basis (roadmap 2.6)
    def scheduled_item(self, item_id: int) -> ScheduledItem | None:
        row = self._conn.execute("SELECT * FROM scheduled_items WHERE id=?", (item_id,)).fetchone()
        return self._scheduled_from_row(row) if row else None

    def update_scheduled_item(self, item_id: int, **fields) -> None:
        """Change an item the owner edited (label, amount, due_date, end_date, paused, active,
        status, user_edited)."""
        allowed = {"label", "amount", "due_date", "end_date", "paused", "active", "status", "user_edited"}
        bad = set(fields) - allowed
        if bad:
            raise ValueError(f"Can't change {', '.join(sorted(bad))}")
        values = {
            k: (v.isoformat() if hasattr(v, "isoformat") else int(v) if isinstance(v, bool) else v)
            for k, v in fields.items()
        }
        sets = ", ".join(f"{k}=?" for k in values)
        self._conn.execute(f"UPDATE scheduled_items SET {sets} WHERE id=?", (*values.values(), item_id))
        self._conn.commit()

    def inactive_items(self, business_id: int) -> list[ScheduledItem]:
        """Items switched off on purpose: removed by the owner, or invoices too old to count."""
        rows = self._conn.execute(
            "SELECT * FROM scheduled_items WHERE business_id=? AND active=0 "
            "AND (user_edited=1 OR status='doubtful') ORDER BY due_date",
            (business_id,),
        )
        return [self._scheduled_from_row(r) for r in rows]

    def statement_summary(self, business_id: int) -> dict:
        """How much history there is and how much of it the app could identify."""
        row = self._conn.execute(
            "SELECT COUNT(*) AS n, MIN(date) AS first, MAX(date) AS last, "
            "SUM(CASE WHEN COALESCE(category, 'other')='other' AND COALESCE(is_internal_transfer, 0)=0 "
            "THEN 1 ELSE 0 END) AS unidentified FROM transactions WHERE business_id=?",
            (business_id,),
        ).fetchone()
        return {"transactions": row["n"], "first": row["first"], "last": row["last"],
                "unidentified": row["unidentified"] or 0}  # fmt: skip

    def daily_in_out(self, business_id: int) -> pd.DataFrame:
        """Money in and money out per day, leaving out own-account moves and the lines a scheduled
        item forecasts on its own dates: the business's normal day-to-day rhythm."""
        return pd.read_sql_query(
            "SELECT date, SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS money_in, "
            "SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END) AS money_out FROM transactions "
            "WHERE business_id=? AND COALESCE(is_internal_transfer, 0)=0 AND scheduled_item_id IS NULL "
            "GROUP BY date ORDER BY date",
            self._conn,
            params=(business_id,),
            parse_dates=["date"],
        )

    def uncategorized_payees(self, business_id: int, since: date) -> list[dict]:
        """Payees still in "other" since `since` (not moves between own accounts), biggest first:
        what the onboarding questions ask about (roadmap 2.7)."""
        rows = self._conn.execute(
            "SELECT description, COUNT(*) AS n, SUM(amount) AS total FROM transactions "
            "WHERE business_id=? AND COALESCE(is_internal_transfer, 0)=0 AND category='other' AND date>=? "
            "GROUP BY description ORDER BY ABS(SUM(amount)) DESC",
            (business_id, since.isoformat()),
        ).fetchall()
        return [
            {"description": r["description"], "count": r["n"], "total": round(r["total"], 2)} for r in rows
        ]

    # ------------------------------------------------------- recurring (roadmap 2.3)
    def recurring_lines(self, business_id: int) -> list[tuple]:
        """(id, date, amount, description, category, is_internal) of the owner's own statements."""
        return [
            tuple(r)
            for r in self._conn.execute(
                "SELECT id, date, amount, description, category, COALESCE(is_internal_transfer, 0) "
                "FROM transactions WHERE business_id=? AND COALESCE(source, '') != 'demo' ORDER BY date, id",
                (business_id,),
            )
        ]

    def edited_items_by_key(self, business_id: int) -> dict[str, int]:
        """match_key → id of an item the owner changed (moved, removed in a plan, edited): detection
        leaves those alone."""
        rows = self._conn.execute(
            "SELECT match_key, MAX(id) AS id FROM scheduled_items WHERE business_id=? AND user_edited=1 "
            "AND match_key IS NOT NULL GROUP BY match_key",
            (business_id,),
        )
        return {r["match_key"]: r["id"] for r in rows}

    def replace_detected_items(
        self, business_id: int, items: list[tuple[ScheduledItem, list[int]]], keep_links: dict[int, list[int]]
    ) -> None:
        """Swap the items found in the statement for a fresh set, and link each statement line to
        the item that now forecasts it. items: (item, its statement lines). keep_links: an edited
        item's id → its lines."""
        self._conn.execute(
            "DELETE FROM scheduled_items WHERE business_id=? AND status='detected' AND COALESCE(user_edited, 0)=0",
            (business_id,),
        )
        self._conn.execute(
            "UPDATE transactions SET scheduled_item_id=NULL WHERE business_id=?", (business_id,)
        )
        links: list[tuple[int, int]] = []
        for item, line_ids in items:
            new_id = self._insert_scheduled_item(business_id, item)
            links.extend((new_id, line_id) for line_id in line_ids)
        for item_id, line_ids in keep_links.items():
            links.extend((item_id, line_id) for line_id in line_ids)
        self._conn.executemany("UPDATE transactions SET scheduled_item_id=? WHERE id=?", links)
        self._conn.commit()

    # ----------------------------------------------------------- forecast runs
    def save_forecast(self, business_id: int, result: ForecastResult, horizon_days: int) -> int:
        lowest = result.lowest
        cur = self._conn.execute(
            "INSERT INTO forecast_runs (business_id, run_at, horizon_days, model, opening_balance, "
            "min_p50, min_p50_date, min_p10, min_p90) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                business_id,
                _now(),
                horizon_days,
                result.model,
                result.opening_balance,
                lowest.balance_p50,
                lowest.date.isoformat(),
                result.min_p10,
                result.min_p90,
            ),
        )
        run_id = cur.lastrowid
        self._conn.executemany(
            "INSERT INTO forecast_points VALUES (?,?,?,?,?,?)",
            [
                (run_id, p.date.isoformat(), p.balance_p10, p.balance_p50, p.balance_p90, p.net_flow_p50)
                for p in result.points
            ],
        )
        self._conn.commit()
        return run_id

    def latest_forecast(self, business_id: int) -> ForecastResult | None:
        run = self._conn.execute(
            "SELECT * FROM forecast_runs WHERE business_id=? ORDER BY id DESC LIMIT 1", (business_id,)
        ).fetchone()
        if run is None:
            return None
        rows = self._conn.execute(
            "SELECT * FROM forecast_points WHERE run_id=? ORDER BY date", (run["id"],)
        ).fetchall()
        points = [
            ForecastPoint(
                date.fromisoformat(r["date"]),
                r["balance_p10"],
                r["balance_p50"],
                r["balance_p90"],
                r["net_flow_p50"],
            )
            for r in rows
        ]
        return ForecastResult(
            opening_balance=run["opening_balance"], points=points, model=run["model"], run_id=run["id"]
        )

    def last_run_at(self, business_id: int) -> datetime | None:
        row = self._conn.execute(
            "SELECT run_at FROM forecast_runs WHERE business_id=? ORDER BY id DESC LIMIT 1", (business_id,)
        ).fetchone()
        if not row:
            return None
        run_at = datetime.fromisoformat(row["run_at"])
        return run_at if run_at.tzinfo else run_at.astimezone()  # older files: server local time

    # ------------------------------------------------------------------ alerts
    def add_alert(
        self,
        business_id: int,
        run_id: int | None,
        alert_type: str,
        severity: str,
        weeks_ahead: int,
        facts: dict,
        title: str,
        body: str,
        actions: list[dict],
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO alerts (business_id, run_id, type, severity, weeks_ahead, facts_json, title, body, "
            "actions_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                business_id,
                run_id,
                alert_type,
                severity,
                weeks_ahead,
                json.dumps(facts),
                title,
                body,
                json.dumps(actions),
                _now(),
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def update_alert(
        self,
        alert_id: int,
        severity: str,
        weeks_ahead: int,
        facts: dict,
        title: str,
        body: str,
        actions: list[dict],
    ) -> None:
        self._conn.execute(
            "UPDATE alerts SET severity=?, weeks_ahead=?, facts_json=?, title=?, body=?, actions_json=? WHERE id=?",
            (severity, weeks_ahead, json.dumps(facts), title, body, json.dumps(actions), alert_id),
        )
        self._conn.commit()

    def list_alerts(self, business_id: int, open_only: bool = True) -> list[Alert]:
        query = "SELECT * FROM alerts WHERE business_id=?"
        if open_only:
            query += " AND dismissed=0 AND resolved=0"
        rows = self._conn.execute(query + " ORDER BY id DESC", (business_id,)).fetchall()
        return [self._row_to_alert(r) for r in rows]

    def unread_alert_count(self, business_id: int) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM alerts WHERE business_id=? AND read_at IS NULL AND dismissed=0 AND resolved=0",
            (business_id,),
        ).fetchone()
        return int(row["n"])

    def mark_alert_read(self, alert_id: int) -> None:
        self._conn.execute("UPDATE alerts SET read_at=? WHERE id=? AND read_at IS NULL", (_now(), alert_id))
        self._conn.commit()

    def dismiss_alert(self, alert_id: int) -> None:
        self._conn.execute("UPDATE alerts SET dismissed=1 WHERE id=?", (alert_id,))
        self._conn.commit()

    def resolve_alerts(self, business_id: int, alert_type: str) -> int:
        cur = self._conn.execute(
            "UPDATE alerts SET resolved=1 WHERE business_id=? AND type=? AND dismissed=0 AND resolved=0",
            (business_id, alert_type),
        )
        self._conn.commit()
        return cur.rowcount

    @staticmethod
    def _row_to_alert(r: sqlite3.Row) -> Alert:
        return Alert(
            id=r["id"],
            type=r["type"],
            severity=r["severity"],
            weeks_ahead=r["weeks_ahead"],
            title=r["title"],
            body=r["body"],
            actions=json.loads(r["actions_json"] or "[]"),
            facts=json.loads(r["facts_json"] or "{}"),
            created_at=r["created_at"],
            read_at=r["read_at"],
            dismissed=bool(r["dismissed"]),
            resolved=bool(r["resolved"]),
        )

    # --------------------------------------------------------------- scenarios
    def save_scenario(
        self, business_id: int, name: str, adjustments: list[dict], result: dict, saved_as_plan: bool
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO scenarios (business_id, name, adjustments_json, created_at, result_json, saved_as_plan) "
            "VALUES (?,?,?,?,?,?)",
            (business_id, name, json.dumps(adjustments), _now(), json.dumps(result), int(saved_as_plan)),
        )
        self._conn.commit()
        return cur.lastrowid

    def list_scenarios(self, business_id: int) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, name, adjustments_json, created_at, result_json, saved_as_plan FROM scenarios "
            "WHERE business_id=? ORDER BY id DESC",
            (business_id,),
        ).fetchall()
        return [
            {
                **dict(r),
                "adjustments": json.loads(r["adjustments_json"]),
                "result": json.loads(r["result_json"]),
            }
            for r in rows
        ]

    # ------------------------------------------------------------------- chat
    def add_chat_message(
        self, business_id: int, role: str, content: str, tool_names: list[str] | None = None
    ) -> None:
        self._conn.execute(
            "INSERT INTO chat_messages (business_id, role, content, tool_calls_json, created_at) VALUES (?,?,?,?,?)",
            (business_id, role, content, json.dumps(tool_names or []), _now()),
        )
        self._conn.commit()

    def list_chat_messages(self, business_id: int, limit: int = 40) -> list[dict]:
        rows = self._conn.execute(
            "SELECT role, content, tool_calls_json FROM chat_messages WHERE business_id=? ORDER BY id DESC LIMIT ?",
            (business_id, limit),
        ).fetchall()
        return [
            {"role": r["role"], "content": r["content"], "tools": json.loads(r["tool_calls_json"])}
            for r in reversed(rows)
        ]

    def clear_chat(self, business_id: int) -> None:
        self._conn.execute("DELETE FROM chat_messages WHERE business_id=?", (business_id,))
        self._conn.commit()

    # ------------------------------------------------------------------ admin
    def reset(self) -> None:
        """Wipe everything (Settings → 'Reset demo')."""
        for table in (
            "uploaded_files",
            "insights",
            "payee_rules",
            "business_profile",
            "chat_messages",
            "scenarios",
            "alerts",
            "forecast_points",
            "forecast_runs",
            "scheduled_items",
            "transactions",
            "accounts",
            "businesses",
        ):
            self._conn.execute(f"DELETE FROM {table}")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
