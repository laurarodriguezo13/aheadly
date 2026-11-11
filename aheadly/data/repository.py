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
    def add_account(self, business_id: int, source: str, name: str, balance: float) -> int:
        cur = self._conn.execute(
            "INSERT INTO accounts (business_id, source, name, balance, last_synced_at) VALUES (?,?,?,?,?)",
            (business_id, source, name, balance, _now()),
        )
        self._conn.commit()
        return cur.lastrowid

    def list_accounts(self, business_id: int) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM accounts WHERE business_id=?", (business_id,)).fetchall()
        return [dict(r) for r in rows]

    def current_balance(self, business_id: int) -> float:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(balance), 0) AS total FROM accounts WHERE business_id=?", (business_id,)
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

    def daily_net_flow(self, business_id: int, exclude_categories: Iterable[str] = ()) -> pd.DataFrame:
        """Daily sum of transactions as a continuous series (missing days = 0).

        `exclude_categories` drops money that the forecast adds back as scheduled items
        (payroll, rent...), so it is never counted twice.
        """
        query = "SELECT date, SUM(amount) AS net_flow FROM transactions WHERE business_id=?"
        params: list = [business_id]
        excluded = sorted(set(exclude_categories))
        if excluded:
            query += f" AND category NOT IN ({','.join('?' * len(excluded))})"
            params.extend(excluded)
        query += " GROUP BY date ORDER BY date"
        df = pd.read_sql_query(query, self._conn, params=params, parse_dates=["date"])
        if df.empty:
            return df
        full_index = pd.date_range(df["date"].min(), df["date"].max(), freq="D")
        return df.set_index("date").reindex(full_index, fill_value=0.0).rename_axis("date").reset_index()

    def flow_totals(self, business_id: int, since: date) -> dict[str, float]:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(CASE WHEN amount > 0 THEN amount END), 0) AS money_in, "
            "COALESCE(SUM(CASE WHEN amount < 0 THEN -amount END), 0) AS money_out "
            "FROM transactions WHERE business_id=? AND date >= ?",
            (business_id, since.isoformat()),
        ).fetchone()
        return {"money_in": float(row["money_in"]), "money_out": float(row["money_out"])}

    # --------------------------------------------------------- scheduled items
    def add_scheduled_items(self, business_id: int, items: list[ScheduledItem]) -> None:
        self._conn.executemany(
            "INSERT INTO scheduled_items (business_id, kind, label, amount, due_date, recurrence, source, active) "
            "VALUES (?,?,?,?,?,?,?,1)",
            [
                (business_id, i.kind, i.label, i.amount, i.due_date.isoformat(), i.recurrence, i.source)
                for i in items
            ],
        )
        self._conn.commit()

    def list_scheduled_items(self, business_id: int) -> list[ScheduledItem]:
        rows = self._conn.execute(
            "SELECT * FROM scheduled_items WHERE business_id=? AND active=1 ORDER BY due_date", (business_id,)
        ).fetchall()
        return [
            ScheduledItem(
                id=r["id"],
                label=r["label"],
                amount=r["amount"],
                due_date=date.fromisoformat(r["due_date"]),
                kind=r["kind"],
                recurrence=r["recurrence"],
                source=r["source"],
            )
            for r in rows
        ]

    def replace_scheduled_items(self, business_id: int, items: list[ScheduledItem]) -> None:
        """Used when a scenario is saved as the plan."""
        self._conn.execute("UPDATE scheduled_items SET active=0 WHERE business_id=?", (business_id,))
        self.add_scheduled_items(business_id, items)

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
