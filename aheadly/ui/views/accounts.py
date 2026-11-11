"""Accounts / onboarding (storyboard frames 1 and 2): upload your bank statement once."""

import html

import streamlit as st

from aheadly.data.connectors.csv_connector import CsvConnector
from aheadly.ui import copy
from aheadly.ui.bootstrap import go_to, start_page
from aheadly.ui.components import card, day, hero, section_title, statement_notice

core = start_page(copy.NAV["accounts"])
status = core.status()

if not status.connected:
    hero(copy.WELCOME_TITLE, copy.WELCOME_BODY)
    st.write("")
    with st.container(border=True):
        section_title(copy.UPLOAD_TITLE)
        st.caption(copy.UPLOAD_HELP)
        name_col, owner_col = st.columns(2)
        name = name_col.text_input(copy.BUSINESS_NAME)
        owner = owner_col.text_input(copy.OWNER_NAME)
        statement = st.file_uploader(copy.STATEMENT_FILE, type=["csv", "xlsx"])
        upcoming = st.file_uploader(copy.UPCOMING_FILE, type=["csv", "xlsx"])
        st.caption(copy.UPCOMING_HELP)
        line_col, balance_col = st.columns(2)
        line = line_col.number_input(
            copy.LOW_CASH_LINE_INPUT, min_value=0.0, value=2000.0, step=100.0, format="%.0f"
        )
        balance = balance_col.number_input(
            copy.BALANCE_INPUT,
            min_value=0.0,
            value=None,
            step=100.0,
            format="%.0f",
            placeholder=copy.BALANCE_PLACEHOLDER,
        )
        ready = statement is not None and bool(name.strip())
        if st.button(copy.UPLOAD_BUTTON, type="primary", disabled=not ready):
            profile = {"name": name.strip(), "owner_name": owner.strip(), "city": "", "low_cash_line": line}
            connector = CsvConnector(
                statement.getvalue(),
                balance,
                statement.name,
                business_profile=profile,
                upcoming=upcoming.getvalue() if upcoming else None,
                upcoming_filename=upcoming.name if upcoming else "upcoming.csv",
            )
            try:
                with st.spinner(copy.UPLOAD_SPINNER):
                    core.connect(connector)
            except Exception as exc:  # a bad file must never crash onboarding
                core.reset()
                st.error(copy.UPLOAD_FAILED.format(error=exc))
            else:
                st.session_state["skipped_rows"] = connector.skipped_rows
                st.session_state["balance_breaks"] = (connector.balance_breaks, connector.first_break)
                st.rerun()
else:
    rows = "".join(
        f'<div class="ah-row"><span><span class="ah-check">✔</span>&nbsp; <b>{html.escape(a["name"])}</b>'
        f' · {html.escape(a["source"])}</span><span>last synced {a["last_synced_at"][:16].replace("T", " ")}</span></div>'
        for a in status.accounts
    )
    card(f'<div class="ah-card-title">✓ {html.escape(copy.ALL_SET)}</div>{rows}', "mint")
    if core.statement_end():
        st.caption(copy.STATEMENT_UP_TO.format(end=day(core.statement_end())))
    statement_notice(core.statement_end(), core.today, core.statement_lag_days())
    if st.session_state.get("skipped_rows"):
        st.warning(copy.SKIPPED_ROWS.format(n=st.session_state["skipped_rows"]))
    breaks, first_break = st.session_state.get("balance_breaks", (0, None))
    if breaks:
        st.warning(copy.BALANCE_BREAKS.format(n=breaks, date=day(first_break)))
    with st.container(border=True):
        section_title(copy.PLANNED_TITLE)
        planned = core.planned_items()
        if planned:
            st.dataframe(
                planned,
                hide_index=True,
                width="stretch",
                column_config={
                    "date": "Date",
                    "description": "What",
                    "amount": st.column_config.NumberColumn("Amount", format="dollar"),
                    "repeats": "Repeats",
                },
            )
        st.caption(copy.PLANNED_HELP)
    with st.container(border=True):
        section_title("Recent transactions")
        st.dataframe(
            core.repo.list_transactions(status.business.id, limit=20),
            hide_index=True,
            width="stretch",
            column_config={
                "date": "Date",
                "description": "Description",
                "category": "Category",
                "counterparty": "Counterparty",
                "amount": st.column_config.NumberColumn("Amount", format="dollar"),
            },
        )
    if st.button("Go to dashboard", type="primary"):
        go_to("dashboard")
