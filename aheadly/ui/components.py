"""Small reusable UI pieces (cards, pills, lists). HTML is built from trusted app data only."""

from __future__ import annotations

import html

import streamlit as st

from aheadly.timefmt import format_local
from aheadly.ui import copy


def money(value: float) -> str:
    value = round(value)
    return f"-${-value:,}" if value < 0 else f"${value:,}"


def day(d) -> str:
    """Nov 10, 2026 (no zero padding, works on every operating system)."""
    return f"{d:%b} {d.day}, {d.year}"


def local_time(value) -> str:
    """A stored time (UTC) in the visitor's own time zone, read from their browser."""
    try:
        zone = st.context.timezone
    except Exception:  # older Streamlit or no browser (tests): the server's zone
        zone = None
    return format_local(value, zone)


def statement_notice(end, start, lag_days: int) -> None:
    """Say when the statement stops before yesterday, so the forecast can't start today."""
    if lag_days >= 7:
        st.warning(copy.STATEMENT_OLD.format(end=day(end), start=day(start), days=lag_days + 1))
    elif lag_days > 0:
        st.info(copy.STATEMENT_BEHIND.format(end=day(end), start=day(start)))


def weeks(n: int) -> str:
    return "1 week" if n == 1 else f"{n} weeks"


def stat_card(label: str, value: str, sub: str = "", tone: str = "", background: str = "lav") -> None:
    st.markdown(
        f'<div class="ah-card {background}"><div class="ah-label">{html.escape(label)}</div>'
        f'<div class="ah-value {tone}">{html.escape(value)}</div>'
        f'<div class="ah-sub">{html.escape(sub)}</div></div>',
        unsafe_allow_html=True,
    )


def card(body_html: str, background: str = "") -> None:
    st.markdown(f'<div class="ah-card {background}">{body_html}</div>', unsafe_allow_html=True)


def info_card(title: str, body_html: str, background: str = "", icon: str = "", tall: bool = True) -> None:
    """Titled card used for the alert blocks (storyboard frame 4)."""
    icon_html = f'<span class="ah-icon">{html.escape(icon)}</span>' if icon else ""
    classes = f"ah-card {background} {'tall' if tall else ''}"
    st.markdown(
        f'<div class="{classes}"><div class="ah-card-title">{icon_html}{html.escape(title)}</div>{body_html}</div>',
        unsafe_allow_html=True,
    )


def section_title(title: str) -> None:
    st.markdown(f'<div class="ah-card-title">{html.escape(title)}</div>', unsafe_allow_html=True)


def check_list_html(items: list[tuple[str, str]]) -> str:
    rows = "".join(
        f'<li><span class="ah-tick">✓</span><div><b>{html.escape(label)}</b>'
        f'<div class="ah-muted">{html.escape(detail)}</div></div></li>'
        for label, detail in items
    )
    return f'<ul class="ah-list">{rows}</ul>'


def rows_html(rows: list[tuple[str, str]]) -> str:
    return "".join(
        f'<div class="ah-row"><span>{html.escape(label)}</span><b>{html.escape(value)}</b></div>'
        for label, value in rows
    )


def alert_list_html(alerts) -> str:
    items = "".join(
        f'<li><span class="ah-dot {a.severity}">!</span><div><b>{html.escape(a.title)}</b>'
        f'<div class="ah-muted">in {weeks(a.weeks_ahead)}</div></div></li>'
        for a in alerts
    )
    return f'<ul class="ah-list">{items}</ul>'


def banner(text: str, icon: str = "✦") -> None:
    st.markdown(
        f'<div class="ah-banner"><span class="ah-icon">{icon}</span>{html.escape(text)}</div>',
        unsafe_allow_html=True,
    )


def severity_pill(severity: str) -> str:
    return f'<span class="ah-pill {severity}">{severity.upper()}</span>'


def hero(title: str, body: str) -> None:
    st.markdown(
        f'<div class="ah-hero"><h2>{html.escape(title)}</h2><p>{html.escape(body)}</p></div>',
        unsafe_allow_html=True,
    )


def scenario_metrics(result) -> None:
    """Best / Base / Worst lowest balance of a what-if (storyboard frame 5 result card)."""
    scen = result.scenario
    cols = st.columns(3)
    values = [
        (copy.BEST_CASE, scen.min_p90, "teal"),
        (copy.BASE_CASE, scen.lowest.balance_p50, "purple"),
        (copy.WORST_CASE, scen.min_p10, ""),
    ]
    for col, (label, value, tone) in zip(cols, values):
        tone = "red" if value < result.low_cash_line else tone
        with col:
            stat_card(label, money(value), copy.LOWEST_BALANCE, tone, "sky" if tone != "red" else "rose")
