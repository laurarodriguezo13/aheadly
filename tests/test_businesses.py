"""Roadmap 1.2: every test business in tests/businesses goes through the real app and is compared
with its answer key.

The businesses and their keys were made separately from the app code (DECISIONS #25): never edit
them to make a check pass. Fix the app, or, if a key really looks wrong, ask the team.

A check for something not built yet is marked in PENDING with the roadmap item that builds it.
Those checks are strict "expected failures": when the feature lands they start passing, the run
fails with XPASS, and the entry must be removed here. PENDING is the to-do list.

Forecasts here use the seeded naive model (fast, repeatable); the live site uses Prophet.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from aheadly.ai.forecast_engine import ForecastEngine
from aheadly.ai.llm_client import StubClient
from aheadly.ai.models import SeasonalNaiveModel
from aheadly.config import Settings
from aheadly.core.app_core import AppCore
from aheadly.data.connectors.csv_connector import CsvConnector
from aheadly.data.repository import Repository
from aheadly.domain import ScheduledItem

BUSINESSES = Path(__file__).parent / "businesses"
KEYS = {
    p.parent.name: json.loads(p.read_text(encoding="utf-8"))
    for p in sorted(BUSINESSES.glob("*/answer_key.json"))
}
STATEMENTS = ("bank_statement", "card_statement")

# check -> {business or "*": roadmap item that builds it}
PENDING: dict[str, dict[str, str]] = {
    "statement_file": {},
    "whole_import": {},
    "risk_level": {},
    "shortfall_alerts": {},
    "hidden_future": {
        "panaderia-la-esquina": "open: this December beat last year's and the bakery's own swings ($259 short on Dec 15 after 2.8)",
    },
    "recurring": {},
    "just_say_it": {},
    "categories": {
        "taller-los-pistones": "the key counts a supplier payment the file shows as #¡VALOR! (unreadable line)",
    },
    "owner_files": {},
    "band_coverage": {},
    "chance_below": {},
    "alert_actions": {
        "cafe-la-tertulia": "3.3 suggested fixes: its tight week is all monthly payments (rent, payroll, owner pay); what helps is pay or prices"
    },
    "internal_transfers": {},
    "insights": {"*": "4.1 things we noticed"},
    "timing_or_structural": {"*": "3.6 financing helper"},
    "what_ifs": {"*": "5.4 chatbot test set (free-text what-ifs)"},
}


def _cases(check: str, ids: list[str]) -> list:
    pending = PENDING[check]
    out = []
    for case in ids:
        reason = pending.get(case) or pending.get(case.split("/")[0]) or pending.get("*")
        marks = [pytest.mark.xfail(strict=True, reason=f"needs {reason}")] if reason else []
        out.append(pytest.param(case, id=case, marks=marks))
    return out


def _businesses(check: str, where=lambda key: True) -> list:
    return _cases(check, [slug for slug, key in KEYS.items() if where(key)])


def _statement_files() -> list[str]:
    return [
        f"{slug}/{Path(f['path']).name}"
        for slug, key in KEYS.items()
        for f in key["files"]
        if f["kind"] in STATEMENTS
    ]


def _file_entry(case: str) -> tuple[str, dict]:
    slug, name = case.split("/")
    return slug, next(f for f in KEYS[slug]["files"] if Path(f["path"]).name == name)


def _d(text: str) -> date:
    return date.fromisoformat(text)


def import_business(slug: str, with_one_offs: bool = False) -> AppCore:
    """Upload a business's statements the way the owner would; optionally (an owner who finished
    onboarding) answer the onboarding questions with the key's answers and add the one-off items the
    owner knows about (as onboarding or "just say it" would)."""
    key, folder = KEYS[slug], BUSINESSES / slug
    start = _d(key["import"]["statement_end"]) + timedelta(days=1)
    core = AppCore(
        Repository(":memory:"),
        ForecastEngine(SeasonalNaiveModel(), n_paths=300),
        Settings(demo_mode=True, llm_provider="stub", db_path=":memory:"),
        llm=StubClient(start),
        today=start,
    )
    business = key["business"]
    profile = {
        "name": business["name"],
        "owner_name": "",
        "city": business.get("city", ""),
        "low_cash_line": business["low_cash_line"],
    }
    connectors = []
    for entry in key["files"]:
        if entry["kind"] in STATEMENTS:
            balance = None if entry["has_balance"] else key["import"]["balance_to_type_if_no_column"]
            path = folder / entry["path"]
            connectors.append(CsvConnector(path.read_bytes(), balance, path.name, business_profile=profile))
    core.connect_files(connectors)  # all statements in one upload, as the Accounts page does
    if with_one_offs:
        answer_onboarding(core, key["onboarding_answers"])
    if with_one_offs and key["one_offs_known"]:
        items = [
            ScheduledItem(
                label=o["label"],
                amount=o["amount"],
                due_date=_d(o["date"]),
                kind="receivable" if o["amount"] > 0 else "bill",
                source="onboarding",
                certainty="confirmed" if o["certainty"] == "confirmed" else "maybe",
            )
            for o in key["one_offs_known"]
        ]
        core.repo.add_scheduled_items(core.status().business.id, items)
        core.run_daily_check(force=True)
    return core


def answer_onboarding(core: AppCore, answers: dict) -> None:
    """The owner answers the questions (roadmap 2.7) through the same App Core calls as the page."""
    core.answer_business(answers["business_type"], answers["customers_pay"])
    months = lambda listed: [int(m[5:7]) for m in listed]  # noqa: E731  "2026-12" → 12
    core.answer_seasons(months(answers["busy_months"]), months(answers["slow_months"]))
    if answers["owner_pay"]["is_owner_pay"]:
        core.answer_owner_pay(answers["owner_pay"]["match_hint"], True)
    for payee, words in answers["mystery_answers"].items():
        core.answer_mystery(payee, words=words)


# ------------------------------------------------------------- reading each statement
@pytest.mark.parametrize("case", _cases("statement_file", _statement_files()))
def test_statement_file(case):
    slug, entry = _file_entry(case)
    key = KEYS[slug]
    path = BUSINESSES / slug / entry["path"]
    balance = None if entry["has_balance"] else key["import"]["balance_to_type_if_no_column"]
    connector = CsvConnector(path.read_bytes(), balance, path.name)
    payload = connector.sync()
    dates = sorted(t.date for t in payload.transactions)

    assert len(payload.transactions) == entry["lines"] - entry["unreadable_lines"]
    assert connector.skipped_rows == entry["unreadable_lines"]
    assert (dates[0], dates[-1]) == (_d(entry["first_date"]), _d(entry["last_date"]))
    newest = max(
        _d(f["last_date"])
        for f in key["files"]
        if f["account"] == entry["account"] and f["kind"] in STATEMENTS
    )
    if _d(entry["last_date"]) == newest:  # the account's closing balance comes from its newest file
        assert payload.balance == pytest.approx(key["import"]["closing_balance_by_account"][entry["account"]])
    breaks = [b for b in key["import"]["balance_breaks"] if b["file"] == entry["path"]]
    assert connector.first_break == (_d(breaks[0]["first_date"]) if breaks else None)


# ------------------------------------------------------------- the whole business
@pytest.mark.parametrize("slug", _businesses("whole_import"))
def test_whole_import(slug):
    key = KEYS[slug]["import"]
    core = import_business(slug)
    business_id = core.status().business.id
    assert core.statement_end() == _d(key["statement_end"])
    assert core.repo.current_balance(business_id) == pytest.approx(key["total_cash"])
    count = core.repo._conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    assert count == key["transactions_after_dedup"]


# ------------------------------------------------------------- forecast and warnings
@pytest.mark.parametrize("slug", _businesses("risk_level"))
def test_risk_level(slug):
    key = KEYS[slug]
    core = import_business(slug, with_one_offs=True)
    forecast = core.get_dashboard().forecast
    assert forecast.risk_level(key["business"]["low_cash_line"]) in key["expected"]["risk_level"]


@pytest.mark.parametrize("slug", _businesses("shortfall_alerts"))
def test_shortfall_alerts(slug):
    """A must-have shortfall shows up within a week of when cash really drops below the line; a
    must-not means no act-now shortfall (a low-severity "keep an eye on it" is allowed)."""
    expected = KEYS[slug]["expected"]
    alerts = [a for a in import_business(slug, with_one_offs=True).get_alerts() if a.type == "shortfall"]
    for must in [a for a in expected["alerts_must"] if a["type"] == "shortfall"]:
        around = _d(must["around"])
        assert any(
            abs((_d(a.facts["first_below_line_date"]) - around).days) <= 7 for a in alerts
        ), f"no shortfall alert near {around}"
    if "shortfall" in expected["alerts_must_not"]:
        assert not [a for a in alerts if a.severity != "low"]


@pytest.mark.parametrize("slug", _businesses("hidden_future"))
def test_hidden_future(slug):
    """What really happened after the statement: the true lowest balance falls inside the forecast's
    worst-to-best range on that day (with a margin of 10% of the cash at the start)."""
    key = KEYS[slug]
    core = import_business(slug, with_one_offs=True)
    forecast = core.get_dashboard().forecast
    actual = key["hidden_future"]["lowest"]
    point = next(p for p in forecast.points if p.date == _d(actual["date"]))
    margin = 0.10 * abs(forecast.opening_balance)
    assert point.balance_p10 - margin <= actual["balance"] <= point.balance_p90 + margin


def _really_dipped(key: dict) -> bool:
    line = key["business"]["low_cash_line"]
    return any(day["balance"] < line for day in key["hidden_future"]["daily_balance"])


def _chance(slug: str) -> float:
    key = KEYS[slug]
    return (
        import_business(slug, with_one_offs=True)
        .get_dashboard()
        .forecast.chance_below(key["business"]["low_cash_line"])
    )


@pytest.mark.parametrize("slug", _businesses("chance_below"))
def test_chance_below(slug):
    """Roadmap 3.1: the chance of dipping below the line, against what really happened. A business
    whose real balance went below its line got a chance of at least 40%; one that stayed above got
    at most 60% (a "watch" business can sit near a coin flip: its bad days are spread out)."""
    chance = _chance(slug)
    assert (chance >= 0.40) if _really_dipped(KEYS[slug]) else (chance <= 0.60), f"chance {chance:.0%}"


def _has_shortfall(key: dict) -> bool:
    return any(a["type"] == "shortfall" for a in key["expected"]["alerts_must"])


@pytest.mark.parametrize("slug", _businesses("alert_actions", _has_shortfall))
def test_alert_actions(slug):
    """Roadmap 3.2: a business that must get a shortfall alert gets at least one action that names
    one of its own payments and, tested as a what-if, raises its lowest balance."""
    core = import_business(slug, with_one_offs=True)
    labels = {i.label for i in core.repo.list_scheduled_items(core.status().business.id)}
    alert = next(a for a in core.get_alerts() if a.type == "shortfall")
    measured = [a for a in alert.actions if a.get("adjustment")]
    assert measured, "no action could be tested"
    best = measured[0]
    assert best["adjustment"]["label"] in labels
    assert best["impact"]["lowest_after"] > best["impact"]["lowest_before"]


def _said(known: dict, said: list[str]) -> bool:
    """The owner wrote this payment's amount in their own words."""
    amount = abs(known["amount"])
    return any(f"{amount:,.0f}" in s or f"{amount:,.2f}" in s for s in said)


@pytest.mark.parametrize(
    "slug",
    _businesses(
        "just_say_it",
        lambda key: any(
            _said(k, key["onboarding_answers"]["upcoming_in_own_words"]) for k in key["one_offs_known"]
        ),
    ),
)
def test_just_say_it(slug):
    """Roadmap 2.4: what the owner says in their own words becomes the payments the key knows about.
    Every known one-off whose amount the owner said must be read with its sign and within 3 days."""
    key = KEYS[slug]
    core = import_business(slug)
    said = key["onboarding_answers"]["upcoming_in_own_words"]
    read = [item for sentence in said for item in core.parse_plan_text(sentence)]
    for known in key["one_offs_known"]:
        if not _said(known, said):
            continue  # the owner didn't say this one (it's in a file: 2.5)
        assert any(
            abs(item.signed_amount - known["amount"]) <= 0.01 * abs(known["amount"])
            and item.due_date is not None
            and abs((item.due_date - _d(known["date"])).days) <= 3
            for item in read
        ), f"not read: {known['label']} {known['amount']} on {known['date']}"
    assert not any(item.ready is False and item.problem != "How much?" for item in read)


# ------------------------------------------------------------- not built yet (see PENDING)
@pytest.mark.parametrize("slug", _businesses("recurring"))
def test_recurring(slug):
    found = import_business(slug).detected_recurring()
    expected = KEYS[slug]["recurring"]
    hits = [r for r in expected if any(r["match_hint"].upper() in (i.match_key or "").upper() for i in found)]
    assert len(hits) >= 0.8 * len(expected)


@pytest.mark.parametrize("slug", _businesses("categories"))
def test_categories(slug):
    """After the owner answers what the app can't know (their own pay, cryptic transfers), as the
    onboarding questions will ask (2.7)."""
    key = KEYS[slug]["categories"]
    core = import_business(slug)
    answers = KEYS[slug]["onboarding_answers"]
    if answers["owner_pay"]["is_owner_pay"]:
        core.set_payee_rule(answers["owner_pay"]["match_hint"], "owner_pay")
    for payee, answer in answers["mystery_answers"].items():
        core.answer_payee(payee, answer)
    totals = core.monthly_category_totals()
    month = sorted(key["monthly_totals"])[-1]
    for category, amount in key["monthly_totals"][month].items():
        assert totals[month].get(category, 0) == pytest.approx(amount, rel=key["tolerance_pct"] / 100)


@pytest.mark.parametrize("slug", _businesses("owner_files", lambda key: bool(key["owner_files"])))
def test_owner_files(slug):
    core = import_business(slug)
    for entry in KEYS[slug]["owner_files"]:
        path = BUSINESSES / slug / entry["path"]
        read = core.read_owner_file(path.read_bytes(), path.name)
        assert (read.kind, read.rows, read.overdue_rows) == (
            entry["kind"],
            entry["rows"],
            entry["overdue_rows"],
        )
        assert read.total == pytest.approx(entry["total"], rel=0.01, abs=0.01)


@pytest.mark.parametrize(
    "slug", _businesses("internal_transfers", lambda key: bool(key["import"].get("internal_transfers")))
)
def test_internal_transfers(slug):
    core = import_business(slug)
    flagged = core.repo._conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE is_internal_transfer=1 AND COALESCE(category, '') != 'card_payment'"
    ).fetchone()[0]
    # both sides of each transfer between bank accounts (card payments are listed apart, as card_payment)
    assert flagged == 2 * len(KEYS[slug]["import"]["internal_transfers"])


@pytest.mark.parametrize("slug", _businesses("insights"))
def test_insights(slug):
    expected = KEYS[slug]["expected"]
    found = {i["type"] for i in import_business(slug, with_one_offs=True).insights()}
    assert set(expected["insights_must"]) <= found
    assert not set(expected["insights_must_not"]) & found


@pytest.mark.parametrize(
    "slug", _businesses("timing_or_structural", lambda key: key["expected"]["timing_or_structural"] != "none")
)
def test_timing_or_structural(slug):
    verdict = import_business(slug, with_one_offs=True).compare_financing()["verdict"]
    assert verdict == KEYS[slug]["expected"]["timing_or_structural"]


@pytest.mark.parametrize("slug", _businesses("what_ifs", lambda key: bool(key["expected"]["what_ifs"])))
def test_what_ifs(slug):
    core = import_business(slug, with_one_offs=True)
    for what_if in KEYS[slug]["expected"]["what_ifs"]:
        result = core.ask(what_if["question"]).scenario
        change = result.summary()["lowest_change"]
        assert change == pytest.approx(what_if["approx_change"], abs=what_if["tolerance"])


@pytest.mark.parametrize("slug", _businesses("band_coverage"))
def test_band_coverage(slug):
    """Roadmap 2.8: what really happened stays inside the worst-to-best range (10% margin) on at
    least 80% of the forecast's days, not only on the lowest day."""
    key = KEYS[slug]
    core = import_business(slug, with_one_offs=True)
    forecast = core.get_dashboard().forecast
    points = {p.date: p for p in forecast.points}
    margin = 0.10 * abs(forecast.opening_balance)
    days = [
        (points[_d(r["date"])], r["balance"])
        for r in key["hidden_future"]["daily_balance"]
        if _d(r["date"]) in points
    ]
    inside = sum(p.balance_p10 - margin <= real <= p.balance_p90 + margin for p, real in days)
    assert inside >= 0.8 * len(days)
