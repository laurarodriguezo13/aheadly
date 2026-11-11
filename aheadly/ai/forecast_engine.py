"""Forecast Engine: projects the cash balance 8 weeks ahead (component "Run Forecast").

Pipeline: residual daily net flow (history without scheduled-type payments)
→ model samples N future paths → add known scheduled items on their due dates
→ cumulate from today's balance → worst / base / best case = p10 / p50 / p90.
Sampled residual paths are cached per history, so a what-if (which only changes
the scheduled items) is instant.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd

from aheadly.ai.recurring import month_rule_dates
from aheadly.ai.models import ForecastModel, ProphetModel, SeasonalNaiveModel, prophet_available
from aheadly.domain import ForecastPoint, ForecastResult, ScheduledItem

logger = logging.getLogger(__name__)

RECURRENCE_DAYS = {"weekly": 7, "biweekly": 14}


def expand_scheduled_items(
    items: list[ScheduledItem], start: date, end: date
) -> list[tuple[date, float, str]]:
    """Turn (possibly recurring) scheduled items into dated cash events in [start, end]."""
    events: list[tuple[date, float, str]] = []
    for item in items:
        if not item.active:
            continue
        if item.recurrence and item.recurrence.startswith("month_day:"):
            # a day of the month every N months, weekends moved (roadmap 2.3)
            for event in month_rule_dates(item.recurrence, item.due_date, end):
                if event >= start:
                    events.append((event, item.amount, item.label))
            continue
        due = item.due_date
        while due <= end:
            if due >= start:
                events.append((due, item.amount, item.label))
            if item.recurrence in RECURRENCE_DAYS:
                due += timedelta(days=RECURRENCE_DAYS[item.recurrence])
            elif item.recurrence and item.recurrence.startswith("every:"):
                due += timedelta(days=max(1, int(item.recurrence.split(":")[1])))
            elif item.recurrence == "monthly":
                due = _add_month(due)
            else:
                break
    return sorted(events)


def _add_month(d: date) -> date:
    month = d.month % 12 + 1
    year = d.year + (d.month == 12)
    return d.replace(year=year, month=month)


def _default_model(n_paths: int) -> ForecastModel:
    if prophet_available():
        return ProphetModel(n_paths=n_paths)
    logger.warning("Prophet not installed; using the seasonal naive model")
    return SeasonalNaiveModel()


class ForecastEngine:
    def __init__(self, model: ForecastModel | None = None, n_paths: int = 500, seed: int = 7):
        self.n_paths = n_paths
        self.seed = seed
        self._model = model or _default_model(n_paths)
        self._paths_cache: dict[str, np.ndarray] = {}

    @property
    def model_name(self) -> str:
        return self._model.name

    # ------------------------------------------------------------- public API
    def forecast(
        self,
        history: pd.DataFrame,
        opening_balance: float,
        scheduled_items: list[ScheduledItem],
        start: date,
        horizon_days: int = 56,
    ) -> ForecastResult:
        if history.empty or len(history) < 14:
            raise ValueError("Need at least two weeks of history to forecast")
        dates = [start + timedelta(days=i) for i in range(horizon_days)]
        residual_paths = self._residual_paths(history, horizon_days)  # (n_paths, horizon)

        events = expand_scheduled_items(scheduled_items, start, dates[-1])
        scheduled_flow = np.zeros(horizon_days)
        for event_date, amount, _label in events:
            scheduled_flow[(event_date - start).days] += amount

        daily_flow = residual_paths + scheduled_flow
        balances = opening_balance + np.cumsum(daily_flow, axis=1)
        p10, p50, p90 = np.percentile(balances, [10, 50, 90], axis=0)
        flow_p50 = np.median(daily_flow, axis=0)
        points = [
            ForecastPoint(dates[i], float(p10[i]), float(p50[i]), float(p90[i]), float(flow_p50[i]))
            for i in range(horizon_days)
        ]
        return ForecastResult(
            opening_balance=opening_balance, points=points, model=self.model_name, scheduled=events
        )

    def backtest(self, history: pd.DataFrame, holdout_days: int = 28) -> dict[str, float]:
        """Mean absolute error of daily net flow on the last `holdout_days`, per model."""
        train, test = history.iloc[:-holdout_days], history.iloc[-holdout_days:]
        actual = test["net_flow"].to_numpy()
        results: dict[str, float] = {}
        for model in (SeasonalNaiveModel(), self._model.__class__()):
            predicted = model.fit(train).predict(holdout_days)
            results[model.name] = float(np.mean(np.abs(actual - predicted)))
        return results

    # --------------------------------------------------------------- internals
    def _residual_paths(self, history: pd.DataFrame, horizon_days: int) -> np.ndarray:
        key = self._history_key(history, horizon_days)
        if key not in self._paths_cache:
            rng = np.random.default_rng(self.seed)
            self._model.fit(history)
            self._paths_cache = {key: self._model.sample_paths(horizon_days, self.n_paths, rng)}
        return self._paths_cache[key]

    @staticmethod
    def _history_key(history: pd.DataFrame, horizon_days: int) -> str:
        digest = hashlib.md5(
            pd.util.hash_pandas_object(history["net_flow"], index=False).to_numpy().tobytes()
        )
        return f"{history['date'].iloc[-1].date()}-{len(history)}-{horizon_days}-{digest.hexdigest()}"


def history_balances(history: pd.DataFrame, current_balance: float, days: int = 56) -> pd.DataFrame:
    """Reconstruct past end-of-day balances backwards from today's balance (for the chart)."""
    recent = history.tail(days).copy()
    future_flows = recent["net_flow"][::-1].cumsum()[::-1].shift(-1, fill_value=0.0)
    recent["balance"] = current_balance - future_flows
    return recent[["date", "balance"]]
