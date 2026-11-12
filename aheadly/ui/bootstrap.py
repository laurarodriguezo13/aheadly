"""Shared Streamlit plumbing: per-visitor App Core, theme, onboarding gate, page switching."""

from __future__ import annotations

import streamlit as st

from aheadly.ai.forecast_engine import ForecastEngine
from aheadly.ai.llm_client import create_llm_client
from aheadly.config import Settings, load_settings
from aheadly.core.app_core import AppCore
from aheadly.core.session import new_core
from aheadly.ui import copy
from aheadly.ui.components import browser_time_zone
from aheadly.ui.theme import inject_theme
from aheadly.version import code_version

VIEWS = "aheadly/ui/views"
PAGES = {
    name: f"{VIEWS}/{name}.py"
    for name in ("dashboard", "questions", "alerts", "basis", "ask", "whatif", "accounts", "settings")
}


def get_settings() -> Settings:
    """Read on every run (it's cheap), so an update that changes Settings never meets an old copy."""
    return load_settings()


# The cached objects below take the code's fingerprint as an argument: after an update it changes,
# so Streamlit builds fresh ones instead of handing the new code objects made by the old code.


@st.cache_resource(show_spinner=False)
def get_engine(version: str) -> ForecastEngine:
    """The forecast model is slow to build and holds no business data, so all visitors share it."""
    return ForecastEngine()


@st.cache_resource(show_spinner=False)
def get_llm(version: str):
    """The LLM client holds no business data either, so all visitors share it."""
    return create_llm_client(get_settings())


@st.cache_resource(show_spinner="Starting Aheadly…")
def _shared_core(version: str) -> AppCore:
    """Only used when PER_VISITOR_DATA is off: one database file for everyone."""
    return new_core(get_settings(), get_engine(version), llm=get_llm(version))


def get_core() -> AppCore:
    """Each visitor (browser session) gets their own App Core and empty database. A visitor whose
    session was started by older code starts over: their objects don't fit the new code."""
    version = code_version()
    settings = get_settings()
    if not settings.per_visitor_data:
        return _shared_core(version)
    if "core" in st.session_state and st.session_state.get("core_version") != version:
        st.session_state.clear()
    if "core" not in st.session_state:
        st.session_state["core"] = new_core(settings, get_engine(version), llm=get_llm(version))
        st.session_state["core_version"] = version
    return st.session_state["core"]


def reset_core() -> None:
    """Settings → 'Start over': wipe this visitor's data and start again from onboarding."""
    get_core().reset()
    _shared_core.clear()
    st.session_state.clear()


def start_page(title: str) -> AppCore:
    """Common page header. Fails fast (st.error + st.stop) only on configuration errors."""
    inject_theme()
    try:
        get_settings().validate()
    except ValueError as exc:
        st.error(f"Configuration problem: {exc}")
        st.stop()
    core = get_core()
    core.set_time_zone(browser_time_zone())  # "today" is the owner's date, not the server's
    st.title(title)
    return core


def require_data(core: AppCore) -> None:
    """Pages other than Accounts cannot work before a data source is connected."""
    if core.status().connected:
        return
    st.info(copy.NOT_CONNECTED)
    if st.button(copy.GO_TO_ACCOUNTS, type="primary"):
        go_to("accounts")
    st.stop()


def go_to(page: str, question: str | None = None) -> None:
    if question:
        st.session_state["pending_question"] = question
    st.switch_page(PAGES[page])
