"""Daily job: `python -m aheadly.jobs.daily_run` (cron-able).

Runs the same pipeline the app runs on load: forecast → alert rules → alerts.
"""

from __future__ import annotations

import logging
import sys

from aheadly.ai.forecast_engine import ForecastEngine
from aheadly.config import load_settings
from aheadly.core.app_core import AppCore
from aheadly.data.repository import Repository


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = load_settings()
    core = AppCore(Repository(settings.db_path), ForecastEngine(), settings)
    if not core.status().connected:
        logging.error("No business connected yet. Open the app and choose a data source first.")
        return 1
    summary = core.run_daily_check(force=True)
    lowest = summary.forecast.lowest
    logging.info(
        "Lowest base-case balance %.0f on %s | alerts raised=%s updated=%s resolved=%s",
        lowest.balance_p50,
        lowest.date,
        summary.alerts_raised,
        summary.alerts_updated,
        summary.alerts_resolved,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
