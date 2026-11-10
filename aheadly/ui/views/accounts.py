"""Accounts / onboarding (storyboard frames 1 and 2: connect once)."""

import html
from pathlib import Path

import streamlit as st

from aheadly.data.connectors.base import ConnectorNotConfigured
from aheadly.data.connectors.csv_connector import CsvConnector
from aheadly.data.connectors.demo_connector import DemoConnector
from aheadly.data.connectors.plaid_connector import PlaidConnector
from aheadly.data.connectors.quickbooks_connector import QuickBooksConnector
from aheadly.ui import copy
from aheadly.ui.bootstrap import go_to, start_page
from aheadly.ui.components import card, hero, section_title

SAMPLES = Path(__file__).resolve().parents[3] / "data" / "samples"

core = start_page(copy.NAV["accounts"])
status = core.status()

if not status.connected:
    left, right = st.columns([3, 1])
    with left:
        hero(copy.WELCOME_TITLE, copy.WELCOME_BODY)
    with right:
        st.image(
            "assets/persona_maria_portrait_square.jpg",
            caption="Maria Gómez · Panadería La Esquina",
            width="stretch",
        )
    st.write("")


def connect_card(title: str, button: str, connector, note: str) -> None:
    with st.container(border=True):
        section_title(title)
        if st.button(button, disabled=not connector.configured, width="stretch"):
            try:
                core.connect(connector)
            except (ConnectorNotConfigured, NotImplementedError) as exc:
                st.warning(str(exc))
        st.caption(note)


c1, c2, c3 = st.columns(3)
with c1:
    connect_card(copy.CONNECT_BANK, "Connect bank", PlaidConnector(), copy.CONNECT_LATER)
with c2:
    connect_card(copy.CONNECT_QBO, "Connect QuickBooks", QuickBooksConnector(), copy.CONNECT_LATER)
with c3, st.container(border=True):
    section_title(copy.USE_DEMO)
    if st.button(copy.USE_DEMO, type="primary", disabled=status.connected, width="stretch"):
        with st.spinner("Syncing 12 months of Panadería La Esquina…"):
            core.connect(DemoConnector())
        st.rerun()
    st.caption("Panadería La Esquina, 12 months of history. No keys needed.")

if status.connected:
    rows = "".join(
        f'<div class="ah-row"><span><span class="ah-check">✔</span>&nbsp; <b>{html.escape(a["name"])}</b>'
        f' · {html.escape(a["source"])}</span><span>last synced {a["last_synced_at"][:16].replace("T", " ")}</span></div>'
        for a in status.accounts
    )
    card(f'<div class="ah-card-title">✓ {html.escape(copy.ALL_SET)}</div>{rows}', "mint")
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

with st.expander("Import a bank export instead (CSV or Excel)"):
    st.caption(
        "Columns: date, description and amount (or debit and credit). Category is optional. "
        "Try it with the sample export below."
    )
    sample = SAMPLES / "bancolombia_export_panaderia_la_esquina.xlsx"
    if sample.exists():
        st.download_button(
            "Download sample bank export (.xlsx)",
            data=sample.read_bytes(),
            file_name=sample.name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    upload = st.file_uploader("Bank export", type=["csv", "xlsx"])
    balance = st.number_input(
        "Current bank balance ($)", min_value=0.0, value=8200.0, step=100.0, format="%.0f"
    )
    if upload is not None and st.button("Import file", type="primary"):
        try:
            added = core.connect(CsvConnector(upload.getvalue(), balance, upload.name))
            st.success(f"Imported {added} transactions.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
