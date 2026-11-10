"""Shared Streamlit plumbing: cached App Core, theme, onboarding gate, page switching."""

from __future__ import annotations

import streamlit as st

from aheadly.ai.forecast_engine import ForecastEngine
from aheadly.config import Settings, load_settings
from aheadly.core.app_core import AppCore
from aheadly.data.repository import Repository
from aheadly.ui import copy
from aheadly.ui.theme import inject_theme

VIEWS = "aheadly/ui/views"
PAGES = {
    name: f"{VIEWS}/{name}.py" for name in ("dashboard", "alerts", "ask", "whatif", "accounts", "settings")
}


@st.cache_resource(show_spinner=False)
def get_settings() -> Settings:
    return load_settings()


@st.cache_resource(show_spinner="Starting Aheadly…")
def get_core() -> AppCore:
    """Heavy objects (SQLite connection, LLM client, forecast model) are created once."""
    settings = get_settings()
    return AppCore(Repository(settings.db_path), ForecastEngine(), settings)


def start_page(title: str) -> AppCore:
    """Common page header. Fails fast (st.error + st.stop) only on configuration errors."""
    inject_theme()
    try:
        get_settings().validate()
    except ValueError as exc:
        st.error(f"Configuration problem: {exc}")
        st.stop()
    core = get_core()
    st.title(title)
    return core


def require_data(core: AppCore) -> None:
    """Pages other than Accounts cannot work before a data source is connected."""
    if core.status().connected:
        return
    st.info(copy.NOT_CONNECTED)
    if st.button(copy.USE_DEMO, type="primary"):
        from aheadly.data.connectors.demo_connector import DemoConnector

        with st.spinner("Loading Panadería La Esquina…"):
            core.connect(DemoConnector())
        st.rerun()
    st.stop()


def go_to(page: str, question: str | None = None) -> None:
    if question:
        st.session_state["pending_question"] = question
    st.switch_page(PAGES[page])
