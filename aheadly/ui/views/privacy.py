"""Privacy (roadmap 5.2): what Aheadly keeps, what goes to the AI, and Delete my data now."""

import streamlit as st

from aheadly.ui import copy
from aheadly.ui.bootstrap import get_settings, go_to, reset_core, start_page
from aheadly.ui.components import section_title

start_page(copy.PRIVACY_TITLE)
settings = get_settings()  # what is connected decides what's true to say (works before any upload too)

st.caption(copy.PRIVACY_INTRO)

with st.container(border=True):
    section_title(copy.PRIVACY_KEPT_TITLE)
    st.markdown(copy.PRIVACY_KEPT)
    if not settings.per_visitor_data:
        st.markdown(copy.PRIVACY_KEPT_LOCAL.format(path=settings.db_path))

with st.container(border=True):
    section_title(copy.PRIVACY_SENT_TITLE)
    if settings.llm_provider == "stub":
        st.markdown(copy.privacy_ai("stub", False))
    else:
        st.markdown(copy.PRIVACY_SENT)
        st.info(copy.privacy_ai(settings.llm_provider, settings.llm_paid_tier))
        st.caption(copy.PRIVACY_SENT_GONE)

with st.container(border=True):
    section_title(copy.PRIVACY_DELETE_TITLE)
    st.caption(copy.PRIVACY_DELETE_HELP)
    sure = st.checkbox(copy.PRIVACY_DELETE_SURE, key="privacy-sure")
    if st.button(copy.PRIVACY_DELETE, type="primary", disabled=not sure):
        reset_core()  # the database, the page's memory and this visit's App Core (with its cached words)
        st.session_state["data_deleted"] = True
        go_to("accounts")
