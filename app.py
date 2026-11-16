"""Aheadly: Streamlit entry point.

`st.set_page_config` must be the first Streamlit call. Page scripts live in `aheadly/ui/views/`
and are registered with `st.navigation` so the sidebar shows titles, icons and
the open-alert badge.
"""

import streamlit as st

st.set_page_config(
    page_title="Aheadly", page_icon="assets/favicon_64.png", layout="wide", initial_sidebar_state="expanded"
)

try:
    from aheadly.version import forget_old_code  # noqa: E402
except ImportError:  # an old copy of version.py is still in memory (roadmap issue 19, after PR #5)
    import sys

    for _name in [m for m in sys.modules if m == "aheadly" or m.startswith("aheadly.")]:
        del sys.modules[_name]
    from aheadly.version import forget_old_code  # noqa: E402

forget_old_code()  # after an update, load the new code everywhere (roadmap issue 19)

from aheadly.ui import copy  # noqa: E402  (imports after set_page_config on purpose)
from aheadly.ui.bootstrap import PAGES, get_core, get_settings  # noqa: E402


def alerts_badge() -> str:
    """Counts open alerts: one stays counted until it is dismissed or solved, not just seen."""
    try:
        get_settings().validate()
        count = get_core().open_alert_count()
    except (ValueError, RuntimeError):
        count = 0
    return f"{copy.NAV['alerts']} ({count})" if count else copy.NAV["alerts"]


def questions_badge() -> str:
    try:
        get_settings().validate()
        left = get_core().questions_left()
    except (ValueError, RuntimeError):
        left = None
    return f"{copy.NAV['questions']} ({left})" if left else copy.NAV["questions"]


pages = [
    st.Page(PAGES["dashboard"], title=copy.NAV["dashboard"], icon=":material/home:", default=True),
    st.Page(PAGES["questions"], title=questions_badge(), icon=":material/quiz:"),
    st.Page(PAGES["alerts"], title=alerts_badge(), icon=":material/notifications:"),
    st.Page(PAGES["insights"], title=copy.NAV["insights"], icon=":material/insights:"),
    st.Page(PAGES["basis"], title=copy.NAV["basis"], icon=":material/fact_check:"),
    st.Page(PAGES["ask"], title=copy.NAV["ask"], icon=":material/chat:"),
    st.Page(PAGES["whatif"], title=copy.NAV["whatif"], icon=":material/science:"),
    st.Page(PAGES["accounts"], title=copy.NAV["accounts"], icon=":material/account_balance:"),
    st.Page(PAGES["settings"], title=copy.NAV["settings"], icon=":material/settings:"),
]

st.logo("assets/logo_wordmark_transparent.png", icon_image="assets/logo_mark_transparent.png", size="large")
st.sidebar.caption(copy.TAGLINE)

st.navigation(pages).run()
