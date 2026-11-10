"""Application settings.

All secrets and tunables come from environment variables (loaded from `.env`
with python-dotenv). Nothing in this module talks to the network or the UI.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

VALID_PROVIDERS = ("stub", "gemini", "anthropic")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of the configuration the app runs with."""

    demo_mode: bool = True
    llm_provider: str = "stub"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    db_path: Path = PROJECT_ROOT / "data" / "aheadly.db"
    currency: str = "USD"
    horizon_days: int = 56
    default_low_cash_line: float = 2000.0
    daily_run_max_age_hours: int = 24

    @property
    def api_key_for_provider(self) -> str:
        if self.llm_provider == "gemini":
            return self.gemini_api_key
        if self.llm_provider == "anthropic":
            return self.anthropic_api_key
        return ""

    @property
    def model_for_provider(self) -> str:
        if self.llm_provider == "gemini":
            return self.gemini_model
        if self.llm_provider == "anthropic":
            return self.anthropic_model
        return "template"

    def validate(self) -> None:
        """LBYL check run once at startup; raises instead of failing later."""
        if self.llm_provider not in VALID_PROVIDERS:
            raise ValueError(f"LLM_PROVIDER must be one of {VALID_PROVIDERS}, got '{self.llm_provider}'")
        if self.llm_provider != "stub" and not self.api_key_for_provider:
            raise ValueError(
                f"LLM_PROVIDER is '{self.llm_provider}' but its API key is missing. "
                "Add it to .env or set LLM_PROVIDER=stub."
            )


def load_settings() -> Settings:
    """Build Settings from the environment (call once, cache the result)."""
    return Settings(
        demo_mode=_env_bool("DEMO_MODE", True),
        llm_provider=os.getenv("LLM_PROVIDER", "stub").strip().lower(),
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
        db_path=Path(os.getenv("DB_PATH", str(PROJECT_ROOT / "data" / "aheadly.db"))),
        currency=os.getenv("CURRENCY", "USD"),
        horizon_days=int(os.getenv("HORIZON_DAYS", "56")),
        default_low_cash_line=float(os.getenv("LOW_CASH_LINE", "2000")),
    )
