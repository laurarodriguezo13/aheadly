"""Accounts / onboarding (storyboard frames 1 and 2): upload your bank statement once."""

import html

import streamlit as st

from aheadly.data.connectors.csv_connector import CsvConnector
from aheadly.ui import copy
from aheadly.ui.bootstrap import go_to, start_page
from aheadly.ui.components import (
    card,
    day,
    hero,
    local_time,
    money,
    owner_file_card,
    section_title,
    statement_notice,
)

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
        statements = st.file_uploader(copy.STATEMENT_FILE, type=["csv", "xlsx"], accept_multiple_files=True)
        kept = st.file_uploader(copy.UPCOMING_FILE, type=["csv", "xlsx"], accept_multiple_files=True)
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
        ready = bool(statements) and bool(name.strip())
        if st.button(copy.UPLOAD_BUTTON, type="primary", disabled=not ready):
            profile = {"name": name.strip(), "owner_name": owner.strip(), "city": "", "low_cash_line": line}
            several = len(statements) > 1
            connectors = [
                CsvConnector(
                    file.getvalue(),
                    None if several else balance,  # a typed balance only makes sense for one file
                    file.name,
                    business_profile=profile,
                )
                for file in statements
            ]
            try:
                with st.spinner(copy.UPLOAD_SPINNER):
                    core.connect_files(connectors)
            except Exception as exc:  # a bad file must never crash onboarding
                core.reset()
                if several and "Balance column" in str(exc):
                    st.error(copy.MULTI_NO_BALANCE)
                else:
                    st.error(copy.UPLOAD_FAILED.format(error=exc))
            else:
                st.session_state["skipped_rows"] = sum(c.skipped_rows for c in connectors)
                # the owner's other files: read now, shown on the next screen to confirm one by one
                st.session_state["owner_files"] = [
                    {
                        "name": f.name,
                        "content": f.getvalue(),
                        "read": core.read_owner_file(f.getvalue(), f.name),
                    }
                    for f in kept or []
                ]
                st.session_state["balance_breaks"] = [
                    (file.name, c.balance_breaks, c.first_break)
                    for file, c in zip(statements, connectors)
                    if c.balance_breaks
                ]
                st.rerun()
    st.write("")
    with st.container(border=True):
        section_title(copy.EXAMPLE_TITLE)
        st.caption(copy.EXAMPLE_HELP)
        if st.button(copy.EXAMPLE_BUTTON):
            try:
                with st.spinner(copy.EXAMPLE_SPINNER):
                    core.load_example()
            except Exception as exc:  # never leave a half-loaded example behind
                core.reset()
                st.error(copy.UPLOAD_FAILED.format(error=exc))
            else:
                go_to("questions")
else:

    def _account_row(a: dict) -> str:
        kind = a.get("kind") or "bank"
        amount = copy.CARD_OWED.format(amount=money(-a["balance"])) if kind == "card" else money(a["balance"])
        return (
            f'<div class="ah-row"><span><span class="ah-check">✔</span>&nbsp; <b>{html.escape(a["name"])}</b>'
            f" · {html.escape(copy.ACCOUNT_KIND.get(kind, kind))} · {html.escape(amount)}</span>"
            f'<span>last synced {local_time(a["last_synced_at"])}</span></div>'
        )

    rows = "".join(_account_row(a) for a in status.accounts)
    card(f'<div class="ah-card-title">✓ {html.escape(copy.ALL_SET)}</div>{rows}', "mint")
    left = core.questions_left()
    if left is None or left:  # just uploaded (not worked out yet) or questions still open
        note, go = st.columns([4, 1])
        note.info(copy.QUESTIONS_BANNER.format(n=left) if left else copy.QUESTIONS_INTRO)
        if go.button(copy.QUESTIONS_GO, key="accounts-questions", type="primary"):
            go_to("questions")
    if core.statement_end():
        st.caption(copy.STATEMENT_UP_TO.format(end=day(core.statement_end())))
    statement_notice(
        core.statement_end(),
        core.today,
        core.statement_lag_days(),
        status.business.name if core.example() else None,
    )
    if st.session_state.get("skipped_rows"):
        st.warning(copy.SKIPPED_ROWS.format(n=st.session_state["skipped_rows"]))
    if any((a.get("kind") or "bank") == "card" for a in status.accounts):
        st.caption(copy.CARD_NOT_CASH)
    moves = core.internal_transfer_counts()
    if moves["transfers"]:
        st.caption(copy.TRANSFERS_FOUND.format(n=moves["transfers"]))
    if moves["card_payments"]:
        st.caption(copy.CARD_PAYMENTS_FOUND)
    breaks = st.session_state.get("balance_breaks") or []
    for file_name, n, first in breaks:
        if len(status.accounts) > 1:
            st.warning(copy.BALANCE_BREAKS_IN_FILE.format(file=file_name, n=n, date=day(first)))
        else:
            st.warning(copy.BALANCE_BREAKS.format(n=n, date=day(first)))
    with st.container(border=True):
        section_title(copy.PLANNED_TITLE)
        st.caption(copy.PLANNED_MOVED)
        if st.button(copy.BASIS_LINK, key="accounts-basis"):
            go_to("basis")
    with st.container(border=True):
        section_title(copy.OWNER_FILES_TITLE)
        st.caption(copy.OWNER_FILES_HELP)
        for note in st.session_state.pop("owner_file_notes", []):
            st.success(note)
        used = core.uploaded_files()
        if used:
            st.caption(copy.OWNER_FILES_USED_LIST.format(names=", ".join(f["name"] for f in used)))
        pending = st.session_state.setdefault("owner_files", [])
        new_files = st.file_uploader(
            copy.OWNER_FILES_UPLOAD,
            type=["csv", "xlsx"],
            accept_multiple_files=True,
            key=f"owner-upload-{st.session_state.get('owner_upload_round', 0)}",
        )
        if new_files:
            pending.extend(
                {"name": f.name, "content": f.getvalue(), "read": core.read_owner_file(f.getvalue(), f.name)}
                for f in new_files
            )
            st.session_state["owner_upload_round"] = st.session_state.get("owner_upload_round", 0) + 1
            st.rerun()
        for index, entry in enumerate(list(pending)):
            if owner_file_card(core, entry, f"owner-{index}-{entry['name']}"):
                pending.remove(entry)
                st.rerun()
    with st.container(border=True):
        section_title("Recent transactions")
        recent = core.repo.list_transactions(status.business.id, limit=20)
        recent["category"] = recent["category"].map(lambda c: copy.CATEGORY_NAMES.get(c, c))
        st.dataframe(
            recent,
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
