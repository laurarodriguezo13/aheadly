"""Shared Streamlit plumbing: per-visitor App Core, theme, onboarding gate, page switching."""

from __future__ import annotations

import streamlit as st

from aheadly.ai.forecast_engine import ForecastEngine
from aheadly.ai.llm_client import create_llm_client
from aheadly.config import Settings, load_settings
from aheadly.core.app_core import AppCore
from aheadly.core.session import new_core
from aheadly.ui import copy
from aheadly.ui.theme import inject_theme

VIEWS = "aheadly/ui/views"
PAGES = {
    name: f"{VIEWS}/{name}.py" for name in ("dashboard", "alerts", "ask", "whatif", "accounts", "settings")
}


@st.cache_resource(show_spinner=False)
def get_settings() -> Settings:
    return load_settings()


@st.cache_resource(show_spinner=False)
def get_engine() -> ForecastEngine:
    """The forecast model is slow to build and holds no business data, so all visitors share it."""
    return ForecastEngine()


@st.cache_resource(show_spinner=False)
def get_llm():
    """The LLM client holds no business data either, so all visitors share it."""
    return create_llm_client(get_settings())


@st.cache_resource(show_spinner="Starting Aheadly…")
def _shared_core() -> AppCore:
    """Only used when PER_VISITOR_DATA is off: one database file for everyone."""
    return new_core(get_settings(), get_engine(), llm=get_llm())


def get_core() -> AppCore:
    """Each visitor (browser session) gets their own App Core and empty database."""
    settings = get_settings()
    if not settings.per_visitor_data:
        return _shared_core()
    if "core" not in st.session_state:
        st.session_state["core"] = new_core(settings, get_engine(), llm=get_llm())
    return st.session_state["core"]


def reset_core() -> None:
    """Settings → 'Reset demo': wipe this visitor's data and start again from onboarding."""
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
