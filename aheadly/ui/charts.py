"""Plotly charts styled with the brand tokens.

Design choice: the lines show the *lowest balance of each week* (history and forecast),
not every day. Daily balances of a bakery saw-tooth with the weekly rhythm of sales and
supplier payments; the weekly low is what alerts care about and it reads like the mockups.
The red dot is the overall lowest day and always sits on the line.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go

from aheadly.domain import ForecastResult
from aheadly.ui.theme import TOKENS

_LAYOUT = dict(
    template="plotly_white",
    height=400,
    margin=dict(l=10, r=20, t=56, b=10),
    font=dict(family="Inter, system-ui, sans-serif", color=TOKENS["navy"], size=13),
    legend=dict(orientation="h", yanchor="bottom", y=1.1, x=0, font=dict(size=12), traceorder="normal"),
    hovermode="x unified",
    hoverlabel=dict(bgcolor="#fff", bordercolor=TOKENS["line"], font=dict(color=TOKENS["navy"])),
    xaxis=dict(showgrid=False, dtick=14 * 86_400_000, tickformat="%b %d", ticks="", zeroline=False),
    yaxis=dict(gridcolor="#F0EDFA", zeroline=False, ticks=""),
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
)
_LINE = dict(width=3.5, shape="spline", smoothing=0.6)
_HOVER = "%{customdata}: %{y:$,.0f}<extra></extra>"


def _money(value: float) -> str:
    value = round(value)
    return f"-${-value:,}" if value < 0 else f"${value:,}"


def _short(value: float) -> str:
    if value == 0:
        return "$0"
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value) / 1000:g}k"


def _weekly_lows(frame: pd.DataFrame, value: str, today: date) -> pd.DataFrame:
    """One row per 7-day bin counted from today: the day with the lowest `value` in that bin."""
    frame = frame.assign(date=pd.to_datetime(frame["date"]))
    bins = (frame["date"] - pd.Timestamp(today)).dt.days // 7
    rows = frame.loc[frame.groupby(bins)[value].idxmin()].sort_values("date")
    return rows.assign(customdata=rows["date"].dt.strftime("%a %b %d"))


def _forecast_frame(forecast: ForecastResult) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": [p.date for p in forecast.points],
            "p10": [p.balance_p10 for p in forecast.points],
            "p50": [p.balance_p50 for p in forecast.points],
            "p90": [p.balance_p90 for p in forecast.points],
        }
    )


def _with_today(
    rows: pd.DataFrame, today: date, balance: float, first: bool, label: str = "Today"
) -> pd.DataFrame:
    anchor = pd.DataFrame({"date": [pd.Timestamp(today)], "customdata": [label]})
    for column in ("balance", "p10", "p50", "p90"):
        if column in rows:
            anchor[column] = balance
    return pd.concat([anchor, rows] if first else [rows, anchor], ignore_index=True)


def _band(fig: go.Figure, rows: pd.DataFrame, color: str, name: str) -> None:
    fig.add_trace(
        go.Scatter(
            x=rows["date"],
            y=rows["p90"],
            mode="lines",
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=rows["date"],
            y=rows["p10"],
            mode="lines",
            fill="tonexty",
            fillcolor=color,
            line=dict(width=0),
            name=name,
            hoverinfo="skip",
        )
    )


def _regions(
    fig: go.Figure,
    low_cash_line: float,
    today: date,
    end: date,
    y_min: float,
    y_max: float,
    label: str = "Today",
) -> None:
    """Soft background: forecast window in lavender, the zone under the low cash line in rose."""
    fig.add_vrect(
        x0=pd.Timestamp(today), x1=pd.Timestamp(end), fillcolor="rgba(123,77,255,0.045)", line_width=0
    )
    if y_min < low_cash_line:
        fig.add_hrect(y0=y_min, y1=low_cash_line, fillcolor="rgba(239,79,95,0.05)", line_width=0)
    fig.add_hline(
        y=low_cash_line,
        line=dict(color=TOKENS["red"], dash="dot", width=1.5),
        annotation_text="Low cash line",
        annotation_position="bottom right",
        annotation_font=dict(color=TOKENS["red"], size=11),
    )
    fig.add_vline(
        x=pd.Timestamp(today),
        line=dict(color="#B9B3D9", dash="dot", width=1),
        annotation_text=label,
        annotation_position="top",
        annotation_font=dict(color=TOKENS["ink"], size=11),
    )
    step = 5000 if y_max - y_min > 15000 else 2500
    ticks = list(range(int(y_min // step) * step, int(y_max // step) * step + step + 1, step))
    fig.update_yaxes(tickvals=ticks, ticktext=[_short(t) for t in ticks], range=[y_min, y_max])


def forecast_chart(
    history: pd.DataFrame,
    forecast: ForecastResult | None,
    low_cash_line: float,
    today: date,
    balance: float,
    start_label: str = "Today",
) -> go.Figure:
    """`start_label`: what the line where the forecast begins is called ("Today" unless the
    statement ends earlier)."""
    fig = go.Figure()
    values = [balance, low_cash_line]
    end = today + timedelta(days=56)
    if not history.empty:
        past = _with_today(
            _weekly_lows(history, "balance", today), today, balance, first=False, label=start_label
        )
        values += list(past["balance"])
        fig.add_trace(
            go.Scatter(
                x=past["date"],
                y=past["balance"],
                name="Past",
                customdata=past["customdata"],
                hovertemplate=_HOVER,
                mode="lines",
                line=dict(color=TOKENS["purple"], **_LINE),
            )
        )
    if forecast:
        future = _with_today(
            _weekly_lows(_forecast_frame(forecast), "p50", today),
            today,
            balance,
            first=True,
            label=start_label,
        )
        values += list(future["p10"]) + list(future["p90"])
        end = forecast.horizon_end
        _band(fig, future, "rgba(123,77,255,0.12)", "Best / worst case")
        fig.add_trace(
            go.Scatter(
                x=future["date"],
                y=future["p50"],
                name="Forecast",
                customdata=future["customdata"],
                hovertemplate=_HOVER,
                mode="lines",
                line=dict(color=TOKENS["purple"], dash="dash", **_LINE),
            )
        )
        low = forecast.lowest
        fig.add_trace(
            go.Scatter(
                x=[low.date],
                y=[low.balance_p50],
                mode="markers+text",
                name="Lowest point",
                marker=dict(color=TOKENS["red"], size=13, line=dict(color="#fff", width=2)),
                text=[_money(low.balance_p50)],
                textposition="bottom center",
                textfont=dict(color=TOKENS["red"], size=13, family="Inter, system-ui, sans-serif"),
                hoverinfo="skip",
            )
        )
    pad = 0.12 * (max(values) - min(values) or 1000)
    _regions(fig, low_cash_line, today, end, min(values) - pad, max(values) + pad, start_label)
    fig.update_layout(**_LAYOUT)
    return fig


def scenario_chart(baseline: ForecastResult, scenario: ForecastResult, low_cash_line: float) -> go.Figure:
    today = baseline.points[0].date - timedelta(days=1)
    balance = baseline.opening_balance
    base = _with_today(_weekly_lows(_forecast_frame(baseline), "p50", today), today, balance, first=True)
    scen = _with_today(_weekly_lows(_forecast_frame(scenario), "p50", today), today, balance, first=True)
    fig = go.Figure()
    _band(fig, scen, "rgba(44,196,184,0.14)", "Scenario range")
    fig.add_trace(
        go.Scatter(
            x=base["date"],
            y=base["p50"],
            name="Today's plan",
            customdata=base["customdata"],
            hovertemplate=_HOVER,
            mode="lines",
            line=dict(color=TOKENS["purple"], dash="dash", **_LINE),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=scen["date"],
            y=scen["p50"],
            name="Scenario",
            customdata=scen["customdata"],
            hovertemplate=_HOVER,
            mode="lines",
            line=dict(color=TOKENS["teal"], **_LINE),
        )
    )
    values = [low_cash_line, balance] + list(base["p50"]) + list(scen["p10"]) + list(scen["p90"])
    pad = 0.12 * (max(values) - min(values) or 1000)
    _regions(fig, low_cash_line, today, scenario.horizon_end, min(values) - pad, max(values) + pad)
    fig.update_layout(**{**_LAYOUT, "height": 330})
    return fig
