"""Download / Load my data (roadmap 5.1), shared by Connect accounts and Settings."""

from __future__ import annotations

import streamlit as st

from aheadly.core.data_file import DataFileError
from aheadly.ui import copy
from aheadly.ui.bootstrap import go_to
from aheadly.ui.components import section_title

KEEP = ("core", "core_version")  # what a load keeps from the page's own memory: the rest was the old data's


def download(core, key: str) -> None:
    name, content = core.export_data()
    st.download_button(
        copy.MY_DATA_DOWNLOAD,
        data=content,
        file_name=name,
        mime="application/octet-stream",
        key=f"{key}-download",
        type="primary",
        on_click="ignore",  # downloading changes nothing, so the page doesn't run again
    )
    st.caption(copy.MY_DATA_PRIVATE)


def load(core, key: str, replaces: bool) -> None:
    upload = st.file_uploader(copy.LOAD_FILE, type=["aheadly"], key=f"{key}-file")
    if replaces:
        st.caption(copy.LOAD_REPLACES)
    if st.button(copy.LOAD_BUTTON, key=f"{key}-load", disabled=upload is None) and upload is not None:
        try:
            with st.spinner(copy.LOAD_SPINNER):
                loaded = core.load_data(upload.getvalue())
        except DataFileError as refused:
            st.error(copy.LOAD_ERRORS[refused.reason])
        else:
            for name in [k for k in st.session_state if k not in KEEP]:
                del st.session_state[name]
            st.session_state["data_loaded"] = loaded
            go_to("dashboard")


def card(core, key: str) -> None:
    """Settings: download what's here, or load a file in its place."""
    with st.container(border=True):
        section_title(copy.MY_DATA_TITLE)
        st.caption(copy.MY_DATA_HELP)
        download(core, key)
        st.write("")
        load(core, key, replaces=True)
