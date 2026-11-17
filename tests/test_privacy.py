"""Roadmap 5.2: the privacy page says what's true for what is connected, and Delete my data works."""

import pytest

from aheadly.config import load_settings
from aheadly.ui import copy
from tests.test_businesses import import_business
from tests.test_sidebar_groups import _bootstrap_names


def test_the_privacy_page_sits_next_to_settings():
    pages, groups = _bootstrap_names()
    assert groups["settings"] == ("settings", "privacy")
    assert "privacy" in pages and copy.NAV["privacy"] == "Privacy"


@pytest.mark.parametrize(
    "provider, paid, says",
    [
        ("stub", False, "nothing leaves Aheadly"),
        ("gemini", False, "people at Google may read it"),
        ("gemini", True, "isn't used to improve Google's products"),
        ("anthropic", True, "isn't used to train its models"),
    ],
)
def test_what_the_page_says_about_the_ai_depends_on_what_is_connected(provider, paid, says):
    assert says in copy.privacy_ai(provider, paid)


def test_the_paid_tier_is_off_unless_said(monkeypatch):
    monkeypatch.delenv("LLM_PAID_TIER", raising=False)
    assert load_settings().llm_paid_tier is False
    monkeypatch.setenv("LLM_PAID_TIER", "true")
    assert load_settings().llm_paid_tier is True


def test_what_the_page_says_is_sent_matches_the_app():
    """The page promises at most 50 transactions per chat question: the code holds to it whatever the
    model asks for."""
    core = import_business("panaderia-la-esquina")
    assert len(core.recent_transactions(limit=500)) == 50
    assert "up to 50 of your transactions" in copy.PRIVACY_SENT


def test_delete_my_data_leaves_nothing_behind():
    core = import_business("panaderia-la-esquina", with_one_offs=True)
    core.ask("How much can I safely spend?")
    core.reset()
    assert core.repo.get_business() is None
    assert not core.status().connected
    for table in ("transactions", "scheduled_items", "chat_messages", "business_profile", "alerts"):
        assert core.repo._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
