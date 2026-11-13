"""Roadmap 1.4, two fixes from the live check: an update must never meet objects built by the old
code (the live site crashed after PR #1 until it was rebooted), and times show in the visitor's zone."""

from datetime import datetime

from aheadly.data.repository import Repository
from aheadly.timefmt import format_local
from aheadly.version import code_version


# ------------------------------------------------------------- a fingerprint of the code
def test_code_version_is_stable_while_the_code_does_not_change(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    assert code_version(tmp_path) == code_version(tmp_path)


def test_code_version_changes_when_any_file_changes(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("x = 1\n")
    before = code_version(tmp_path)
    (tmp_path / "pkg" / "a.py").write_text("x = 2\n")
    assert code_version(tmp_path) != before


def test_the_app_has_a_code_version():
    version = code_version()
    assert len(version) == 12 and version == code_version()


# ------------------------------------------------------------- times
def test_times_are_stored_in_utc():
    repo = Repository(":memory:")
    business = repo.create_business(name="Test", owner_name="", city="", low_cash_line=2000.0)
    repo.add_account(business.id, "csv", "Imported file", 100.0)
    assert repo.list_accounts(business.id)[0]["last_synced_at"].endswith("+00:00")


def test_last_run_is_a_time_with_a_zone(connected_core):
    last = connected_core.repo.last_run_at(connected_core.status().business.id)
    assert last is not None and last.tzinfo is not None


def test_a_utc_time_shows_in_the_visitors_zone():
    assert format_local("2026-11-11T15:03:00+00:00", "America/New_York") == "Nov 11, 2026, 10:03"
    assert format_local("2026-11-11T15:03:00+00:00", "America/Bogota") == "Nov 11, 2026, 10:03"
    assert format_local("2026-11-11T15:03:00+00:00", "Europe/Madrid") == "Nov 11, 2026, 16:03"


def test_unknown_zone_falls_back_without_crashing():
    assert format_local("2026-11-11T15:03:00+00:00", "Not/AZone").startswith("Nov 11, 2026, ")
    assert format_local("2026-11-11T15:03:00+00:00", None).startswith("Nov 11, 2026, ")


def test_old_times_without_a_zone_still_show():
    assert format_local(datetime(2026, 11, 11, 10, 3), None) == "Nov 11, 2026, 10:03"
