"""Roadmap 1.5 and 5.6: "Try an example business" loads one of the six test businesses (the bakery
first) without any files of your own."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from aheadly.ai.forecast_engine import ForecastEngine
from aheadly.ai.llm_client import StubClient
from aheadly.ai.models import SeasonalNaiveModel
from aheadly.config import Settings
from aheadly.core.app_core import AppCore
from aheadly.core.examples import DEFAULT_EXAMPLE, EXAMPLES, list_examples, load_example
from aheadly.data.connectors.csv_connector import CsvConnector
from aheadly.data.repository import Repository
from aheadly.ui import copy

TEST_BUSINESS = Path(__file__).parent / "businesses" / DEFAULT_EXAMPLE
DAY_AFTER_STATEMENT = date(2026, 11, 11)


def _core(today: date | None = DAY_AFTER_STATEMENT) -> AppCore:
    return AppCore(
        Repository(":memory:"),
        ForecastEngine(SeasonalNaiveModel(), n_paths=300),
        Settings(llm_provider="stub", db_path=":memory:"),
        llm=StubClient(DAY_AFTER_STATEMENT),
        today=today,
    )


def test_example_statements_are_the_checked_test_business():
    """The example must stay the business the automatic checks look at."""
    shipped = sorted((EXAMPLES / DEFAULT_EXAMPLE / "statements").iterdir())
    tested = sorted((TEST_BUSINESS / "statements").iterdir())
    assert [p.name for p in shipped] == [p.name for p in tested]
    same = [_text(a) == _text(b) for a, b in zip(shipped, tested)]
    assert all(same)


def _text(path: Path) -> bytes:
    """File content with Windows line endings ignored (git may convert them on checkout)."""
    return path.read_bytes().replace(b"\r\n", b"\n")


def test_example_loads_without_any_files():
    core = _core()
    core.load_example()
    status = core.status()
    assert status.connected
    assert status.business.name == "Panadería La Esquina"
    assert status.business.low_cash_line == 2000
    assert core.example() == DEFAULT_EXAMPLE
    assert len(status.accounts) == 1
    assert core.cash_summary()["current_balance"] == 8200
    assert core.statement_end() == date(2026, 11, 10)


def test_example_counts_on_what_the_owner_knows_is_coming():
    core = _core()
    core.load_example()
    planned = {p["description"]: p["amount"] for p in core.planned_items()}
    assert planned["New oven"] == -7500.0
    assert planned["Christmas order Café El Tinto Feliz"] == 5500.0
    assert len(planned) == len(load_example().upcoming)


def test_example_shows_the_december_dip():
    """The bakery's story: the oven drains the cushion and cash dips below $2,000 in mid-December."""
    core = _core()
    core.load_example()
    value, low_date = core.get_dashboard().forecast.lowest_with_today()
    assert value < 2000
    assert low_date is not None and date(2026, 12, 1) <= low_date <= date(2026, 12, 20)


def test_example_is_shown_as_of_the_day_after_its_statement():
    """Opened any day after Nov 11, 2026, the example still starts the day after its statement ends."""
    core = _core(today=None)
    core.load_example()
    assert core.today == min(core.real_today(), DAY_AFTER_STATEMENT)


def test_example_replaces_earlier_data():
    core = _core()
    statement = "Date,Description,Amount,Balance\n" + "".join(
        f"2026-10-{d:02d},Sale,100,{1000 + 100 * d}\n" for d in range(1, 29)
    )
    core.connect(
        CsvConnector(
            statement.encode(),
            None,
            "mine.csv",
            business_profile={"name": "Mine", "owner_name": "", "city": ""},
        )
    )
    core.load_example()
    assert core.status().business.name == "Panadería La Esquina"
    assert len(core.status().accounts) == 1


def test_own_upload_is_not_an_example():
    core = _core()
    statement = "Date,Description,Amount,Balance\n" + "".join(
        f"2026-10-{d:02d},Sale,100,{1000 + 100 * d}\n" for d in range(1, 29)
    )
    core.connect(
        CsvConnector(
            statement.encode(),
            None,
            "mine.csv",
            business_profile={"name": "Mine", "owner_name": "", "city": ""},
        )
    )
    assert core.example() is None


def test_unknown_example_is_refused():
    with pytest.raises(ValueError):
        load_example("no-such-business")


# ------------------------------------------------- roadmap 5.6: any of the six test businesses
BUSINESSES = Path(__file__).parent / "businesses"
SLUGS = sorted(p.name for p in BUSINESSES.iterdir() if (p / "answer_key.json").is_file())


def _key(slug: str) -> dict:
    return json.loads((BUSINESSES / slug / "answer_key.json").read_text(encoding="utf-8"))


def test_every_test_business_is_an_example_bakery_first():
    assert sorted(list_examples()) == SLUGS
    assert list_examples()[0] == DEFAULT_EXAMPLE


@pytest.mark.parametrize("slug", SLUGS)
def test_each_example_is_its_checked_test_business(slug):
    """Statements identical to the test business's; what the owner knows is coming and their
    answers taken from its answer key (the builder never edits tests/businesses)."""
    shipped = sorted((EXAMPLES / slug / "statements").iterdir())
    tested = sorted((BUSINESSES / slug / "statements").iterdir())
    assert [p.name for p in shipped] == [p.name for p in tested]
    assert all(_text(a) == _text(b) for a, b in zip(shipped, tested))
    key, example = _key(slug), load_example(slug)
    assert example.profile["name"] == key["business"]["name"]
    assert example.profile["low_cash_line"] == key["business"]["low_cash_line"]
    assert sorted((u.label, u.amount, u.due_date.isoformat()) for u in example.upcoming) == sorted(
        (o["label"], o["amount"], o["date"]) for o in key["one_offs_known"]
    )
    answers = key["onboarding_answers"]
    assert example.answers["business_type"].lower() == answers["business_type"].lower()
    assert example.answers["mystery"] == answers["mystery_answers"]
    assert example.answers["owner_pay"] == [answers["owner_pay"]["match_hint"]]
    assert example.answers["busy_months"] == [int(m[5:7]) for m in answers["busy_months"]]


@pytest.mark.parametrize("slug", SLUGS)
def test_each_example_loads_like_an_upload(slug):
    key = _key(slug)
    core = _core()
    core.load_example(slug)
    assert core.example() == slug
    assert core.status().business.name == key["business"]["name"]
    assert core.cash_summary()["current_balance"] == round(key["import"]["total_cash"])
    assert core.statement_end() == date(2026, 11, 10)
    assert core.example_answers()["business_type"]


def test_each_example_has_its_line_in_the_picker():
    assert set(copy.EXAMPLE_SITUATIONS) == set(list_examples())
    assert all(10 < len(line) < 120 for line in copy.EXAMPLE_SITUATIONS.values())


def test_the_picker_lists_every_example_by_name():
    names = _core().examples()
    assert list(names) == list_examples()
    assert names[DEFAULT_EXAMPLE] == "Panadería La Esquina" and len(names) == 6
