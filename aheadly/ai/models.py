"""Forecasting models behind the Forecast Engine.

Both models share the same small interface (fit / predict / sample_paths), so
the engine can swap them and the backtest can compare them. The course rule
"never forecast without a naive baseline" is why there are two.
"""

from __future__ import annotations

import logging
from typing import Protocol

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class ForecastModel(Protocol):
    name: str

    def fit(self, history: pd.DataFrame) -> "ForecastModel": ...

    def predict(self, horizon_days: int) -> np.ndarray: ...

    def sample_paths(self, horizon_days: int, n_paths: int, rng: np.random.Generator) -> np.ndarray: ...


class SeasonalNaiveModel:
    """Baseline: average of the same weekday over the last N weeks, bootstrap noise."""

    name = "seasonal_naive"

    def __init__(self, weeks: int = 12):
        self.weeks = weeks
        self._weekday_mean = np.zeros(7)
        self._residuals = np.zeros(1)
        self._last_date: pd.Timestamp | None = None

    def fit(self, history: pd.DataFrame) -> "SeasonalNaiveModel":
        recent = history.tail(self.weeks * 7).copy()
        recent["weekday"] = recent["date"].dt.weekday
        self._weekday_mean = (
            recent.groupby("weekday")["net_flow"].mean().reindex(range(7)).fillna(0).to_numpy()
        )
        self._residuals = (recent["net_flow"] - self._weekday_mean[recent["weekday"]]).to_numpy()
        self._last_date = recent["date"].iloc[-1]
        return self

    def predict(self, horizon_days: int) -> np.ndarray:
        weekdays = self._future_weekdays(horizon_days)
        return self._weekday_mean[weekdays]

    def sample_paths(self, horizon_days: int, n_paths: int, rng: np.random.Generator) -> np.ndarray:
        noise = rng.choice(self._residuals, size=(n_paths, horizon_days), replace=True)
        return self.predict(horizon_days) + noise

    def _future_weekdays(self, horizon_days: int) -> np.ndarray:
        start = self._last_date + pd.Timedelta(days=1)
        return pd.date_range(start, periods=horizon_days, freq="D").weekday.to_numpy()


class ProphetModel:
    """Prophet with weekly seasonality and Colombian holidays (the production model)."""

    name = "prophet"

    def __init__(self, n_paths: int = 500):
        self.n_paths = n_paths
        self._model = None
        self._last_date: pd.Timestamp | None = None

    def fit(self, history: pd.DataFrame) -> "ProphetModel":
        from prophet import Prophet  # imported lazily: heavy and optional

        logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
        logging.getLogger("prophet").setLevel(logging.WARNING)
        months_of_history = (history["date"].iloc[-1] - history["date"].iloc[0]).days / 30.4
        model = Prophet(
            growth="flat",  # a bakery's weekly cash flow is level + seasonality, not a trend
            weekly_seasonality=True,
            yearly_seasonality=months_of_history >= 18,
            daily_seasonality=False,
            interval_width=0.8,
            uncertainty_samples=self.n_paths,
        )
        model.add_country_holidays(country_name="CO")
        model.fit(history.rename(columns={"date": "ds", "net_flow": "y"}))
        self._model = model
        self._last_date = history["date"].iloc[-1]
        return self

    def predict(self, horizon_days: int) -> np.ndarray:
        forecast = self._model.predict(self._future(horizon_days))
        return forecast["yhat"].to_numpy()

    def sample_paths(self, horizon_days: int, n_paths: int, rng: np.random.Generator) -> np.ndarray:
        samples = self._model.predictive_samples(self._future(horizon_days))["yhat"]  # (horizon, n)
        paths = samples.T
        if paths.shape[0] >= n_paths:
            return paths[:n_paths]
        extra = rng.choice(paths.shape[0], size=n_paths - paths.shape[0])
        return np.vstack([paths, paths[extra]])

    def _future(self, horizon_days: int) -> pd.DataFrame:
        start = self._last_date + pd.Timedelta(days=1)
        return pd.DataFrame({"ds": pd.date_range(start, periods=horizon_days, freq="D")})


def prophet_available() -> bool:
    try:
        import prophet  # noqa: F401
    except ImportError:
        return False
    return True
