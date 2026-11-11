"""Builds the App Core a visitor works with.

With PER_VISITOR_DATA on (the default), every visitor gets their own empty
in-memory database, so nobody sees or changes anyone else's data. With it off,
everyone shares the database file at DB_PATH (handy for local single-user work).
"""

from __future__ import annotations

from datetime import date

from aheadly.ai.forecast_engine import ForecastEngine
from aheadly.config import Settings
from aheadly.core.app_core import AppCore
from aheadly.data.repository import Repository


def new_repository(settings: Settings) -> Repository:
    """An empty in-memory database per visitor, or the shared database file."""
    if settings.per_visitor_data:
        return Repository(":memory:")
    return Repository(settings.db_path)


def new_core(settings: Settings, engine: ForecastEngine, llm=None, today: date | None = None) -> AppCore:
    """One App Core with its own repository; the engine and LLM client can be shared."""
    return AppCore(new_repository(settings), engine, settings, llm=llm, today=today)
