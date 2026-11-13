"""Settings: low cash line, provider status, daily check, backtest, demo reset."""

import pandas as pd
import streamlit as st

from aheadly.ui import copy
from aheadly.ui.bootstrap import require_data, reset_core, start_page
from aheadly.ui.components import local_time, section_title

core = start_page(copy.SETTINGS_TITLE)
require_data(core)
status = core.status()

left, right = st.columns(2)
with left, st.container(border=True):
    section_title(copy.SETTINGS_BUFFER)
    line = st.number_input(
        copy.LOW_CASH_LINE,
        min_value=0.0,
        value=float(status.business.low_cash_line),
        step=100.0,
        format="%.0f",
        help=copy.LOW_CASH_HELP,
    )
    if st.button(copy.SAVE_ANSWER):
        core.set_low_cash_line(line)
        st.success(copy.SETTINGS_SAVED)

with right, st.container(border=True):
    section_title(copy.SETTINGS_CHECK)
    st.write(
        copy.SETTINGS_LAST_RUN.format(when=local_time(status.last_run_at))
        if status.last_run_at
        else copy.SETTINGS_NEVER_RUN
    )
    if st.button(copy.RUN_CHECK, type="primary"):
        with st.spinner(copy.SETTINGS_RUNNING):
            summary = core.run_daily_check(force=True)
        st.success(
            copy.SETTINGS_RAN.format(
                raised=summary.alerts_raised, updated=summary.alerts_updated, resolved=summary.alerts_resolved
            )
        )

with st.container(border=True):
    section_title(copy.SETTINGS_AI)
    st.write(
        copy.SETTINGS_MODELS.format(
            provider=copy.PROVIDER_NAMES.get(status.llm_provider, status.llm_provider)
            + ("" if status.llm_provider == "stub" else f" ({status.llm_model})"),
            forecast=copy.FORECAST_NAMES.get(status.forecast_model, status.forecast_model),
        )
    )
    # known issue 21: owners saw ".env" and "LLM_PROVIDER=…" here
    st.caption(copy.SETTINGS_AI_STUB if status.llm_provider == "stub" else copy.SETTINGS_AI_LIVE)
    if st.button(copy.BACKTEST):
        with st.spinner(copy.SETTINGS_BACKTESTING):
            scores = core.backtest()
        st.dataframe(
            pd.DataFrame(
                {copy.BACKTEST_MODEL: list(scores), copy.BACKTEST_ERROR: [round(v) for v in scores.values()]}
            ),
            hide_index=True,
        )
        st.caption(copy.BACKTEST_NOTE)

with st.container(border=True):
    section_title(copy.RESET_DEMO)
    st.caption(copy.RESET_HELP)
    if st.button(copy.RESET_DEMO):
        reset_core()
        st.rerun()
