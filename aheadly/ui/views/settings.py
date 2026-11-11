"""Settings: low cash line, provider status, daily check, backtest, demo reset."""

import pandas as pd
import streamlit as st

from aheadly.ui import copy
from aheadly.ui.bootstrap import require_data, reset_core, start_page
from aheadly.ui.components import section_title

core = start_page(copy.SETTINGS_TITLE)
require_data(core)
status = core.status()

left, right = st.columns(2)
with left, st.container(border=True):
    section_title("Your safety buffer")
    line = st.number_input(
        copy.LOW_CASH_LINE,
        min_value=0.0,
        value=float(status.business.low_cash_line),
        step=100.0,
        format="%.0f",
        help=copy.LOW_CASH_HELP,
    )
    if st.button("Save"):
        core.set_low_cash_line(line)
        st.success("Saved. Forecast and alerts refreshed.")

with right, st.container(border=True):
    section_title("Daily check")
    st.write(f"Last run: {status.last_run_at:%Y-%m-%d %H:%M}" if status.last_run_at else "Never run yet.")
    if st.button(copy.RUN_CHECK, type="primary"):
        with st.spinner("Forecasting the next 8 weeks…"):
            summary = core.run_daily_check(force=True)
        st.success(
            f"Done. Alerts raised: {summary.alerts_raised}, updated: {summary.alerts_updated}, "
            f"resolved: {summary.alerts_resolved}."
        )

with st.container(border=True):
    section_title("AI status")
    st.write(
        f"Language model: **{status.llm_provider}** ({status.llm_model})  ·  "
        f"Forecast model: **{status.forecast_model}**"
    )
    st.caption(
        "Provider and keys are set in `.env` (LLM_PROVIDER=stub|gemini|anthropic). Stub works offline."
    )
    if st.button(copy.BACKTEST):
        with st.spinner("Backtesting on the last 4 weeks…"):
            scores = core.backtest()
        st.dataframe(
            pd.DataFrame(
                {"Model": list(scores), "MAE of daily net flow ($)": [round(v) for v in scores.values()]}
            ),
            hide_index=True,
        )
        st.caption(
            "Lower is better. The course rule: never trust a forecast without comparing it to a naive baseline."
        )

with st.container(border=True):
    section_title("Demo")
    st.caption("Wipes the local database. The next visit to Accounts starts from onboarding again.")
    if st.button(copy.RESET_DEMO):
        reset_core()
        st.rerun()
