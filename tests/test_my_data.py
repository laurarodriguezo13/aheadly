"""Roadmap 5.1: Download / Load my data. The file brings a visit back exactly as it was."""

import io
import json
import zipfile
from datetime import timedelta

import pytest

from aheadly.ai.forecast_engine import ForecastEngine, SeasonalNaiveModel
from aheadly.ai.llm_client import StubClient
from aheadly.config import Settings
from aheadly.core import data_file
from aheadly.core.app_core import AppCore
from aheadly.data.connectors.csv_connector import CsvConnector
from aheadly.data.repository import Repository
from tests.test_businesses import BUSINESSES, KEYS, _d, import_business

SLUG = "panaderia-la-esquina"
START = _d(KEYS[SLUG]["import"]["statement_end"]) + timedelta(days=1)


def empty_core() -> AppCore:
    """A new visit: nothing uploaded yet."""
    return AppCore(
        Repository(":memory:"),
        ForecastEngine(SeasonalNaiveModel(), n_paths=300),
        Settings(llm_provider="stub", db_path=":memory:"),
        llm=StubClient(START),
        today=START,
    )


@pytest.fixture(scope="module")
def visit():
    """An owner who did a fair amount: answered the questions, said no to a suggestion, told us a
    limit and a note, dismissed an alert, saved a plan and asked the chat something."""
    core = import_business(SLUG, with_one_offs=True)
    core.keep_anything_else([{"kind": "price", "quote": "My prices are fixed"}], ["Customers are offices"])
    fix = core.suggested_fixes()[0]
    core.decline_suggestion(fix, "wont_agree")
    alert = core.repo.list_alerts(core._business().id)[0]
    core.dismiss_alert(alert.id)
    core.save_suggestion(core.suggested_fixes()[0]["adjustments"], "Plan from a suggestion")
    core.ask("How much can I safely spend?")
    name, content = core.export_data()
    return core, name, content


def snapshot(core: AppCore) -> dict:
    """What the owner sees, page by page."""
    business = core._business()
    forecast = core.repo.latest_forecast(business.id)
    return {
        "business": (business.name, business.low_cash_line),
        "balance": core.repo.current_balance(business.id),
        "lowest": (round(forecast.lowest.balance_p50), forecast.lowest.date, round(forecast.min_p10)),
        "alerts": [
            (a.type, a.title, a.dismissed) for a in core.repo.list_alerts(business.id, open_only=False)
        ],
        "told_us": core.told_us(),
        "declined": core.declined_suggestions(),
        "questions_left": core.questions_left(),
        "plan": sorted(
            (i.label, i.amount, str(i.due_date)) for i in core.repo.list_scheduled_items(business.id)
        ),
        "chat": [(m["role"], m["content"]) for m in core.repo.list_chat_messages(business.id)],
        "suggestions": sorted(s["id"] for s in core.all_suggestions()),
        "insights": [c["title"] for c in core.insight_cards()],
        "safe": core.safe_numbers(),
        "example": core.example(),
    }


def test_a_loaded_file_brings_the_visit_back_as_it_was(visit):
    core, _, content = visit
    later = empty_core()
    summary = later.load_data(content)
    assert summary["business_name"] == core._business().name
    assert summary["transactions"] > 1000
    assert snapshot(later) == snapshot(core)


def test_the_file_is_named_after_the_business_and_the_day(visit):
    _, name, _ = visit
    assert name.startswith("aheadly-panaderia-la-esquina-") and name.endswith(".aheadly")
    assert data_file.file_name("Café La Tertulia!", START) == f"aheadly-cafe-la-tertulia-{START}.aheadly"


def test_a_newer_statement_after_loading_adds_only_its_new_lines(visit):
    _, _, content = visit
    later = empty_core()
    later.load_data(content)
    before = len(later.repo.list_transactions(later._business().id, limit=100_000))
    entry = next(e for e in KEYS[SLUG]["files"] if e["kind"] == "bank_statement")
    path = BUSINESSES / SLUG / entry["path"]
    later.connect_files([CsvConnector(path.read_bytes(), None, path.name)])
    assert len(later.repo.list_transactions(later._business().id, limit=100_000)) == before


def _file(payload: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(data_file.MEMBER, json.dumps(payload))
    return buffer.getvalue()


def _payload(content: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        return json.loads(archive.read(data_file.MEMBER))


@pytest.mark.parametrize(
    "change, reason",
    [
        (lambda p: p.update(schema_version=p["schema_version"] + 1), "newer"),
        (lambda p: p.update(format="something-else"), "not_ours"),
        (lambda p: p["tables"].update(passwords=[]), "broken"),
        (lambda p: p["tables"]["transactions"][0].update(script="x"), "broken"),
        (lambda p: p["tables"]["transactions"][0].update(amount={"$gt": 0}), "broken"),
        (lambda p: p["tables"]["businesses"].append(dict(p["tables"]["businesses"][0], id=99)), "broken"),
        (lambda p: p["tables"]["transactions"][0].update(business_id=99), "broken"),
    ],
)
def test_a_wrong_file_is_refused_and_nothing_changes(visit, change, reason):
    core, _, content = visit
    payload = _payload(content)
    change(payload)
    other = import_business("cafe-la-tertulia")
    before = snapshot(other)
    with pytest.raises(data_file.DataFileError) as refused:
        other.load_data(_file(payload))
    assert refused.value.reason == reason
    assert snapshot(other) == before


def test_files_that_arent_ours_are_refused(visit, monkeypatch):
    core, _, content = visit
    empty = empty_core()
    for junk, reason in [
        (b"Date,Description,Amount\n2026-11-01,Rent,-900\n", "not_ours"),  # a statement, not a data file
        (b"PK\x03\x04 not really a zip", "not_ours"),
        (_zip_with("notes.txt", "hello"), "not_ours"),
        (_zip_with(data_file.MEMBER, "{not json"), "broken"),
    ]:
        with pytest.raises(data_file.DataFileError) as refused:
            empty.load_data(junk)
        assert refused.value.reason == reason
    monkeypatch.setattr(data_file, "MAX_BYTES", 1000)
    with pytest.raises(data_file.DataFileError) as refused:
        empty.load_data(content)
    assert refused.value.reason == "too_big"


def _zip_with(name: str, text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, text)
    return buffer.getvalue()


def test_a_file_from_an_older_version_loads(visit):
    """A file saved before migration 2 has no first due date for planned payments."""
    _, _, content = visit
    payload = _payload(content)
    payload["schema_version"] = 1
    for row in payload["tables"]["scheduled_items"]:
        row.pop("first_due_date")
    later = empty_core()
    later.load_data(_file(payload))
    items = later.repo.list_scheduled_items(later._business().id)
    assert items and all(i.first_due for i in items if i.due_date)


def test_a_bank_connections_token_never_goes_in_the_file(visit):
    _, _, content = visit
    assert all("access_token_enc" not in row for row in _payload(content)["tables"]["accounts"])
