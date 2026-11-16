"""Aheadly: Streamlit entry point.

`st.set_page_config` must be the first Streamlit call. Page scripts live in `aheadly/ui/views/`
and are registered with `st.navigation`; the sidebar shows four entries (roadmap R.2), each with
a row of sub-tabs at the top of its pages, and the counts of open alerts and questions left.
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
from aheadly.ui.bootstrap import GROUPS, PAGES, get_core, get_settings, group_of  # noqa: E402
from aheadly.ui.theme import inject_theme  # noqa: E402

ICONS = {
    "dashboard": ":material/home:",
    "alerts": ":material/notifications:",
    "insights": ":material/insights:",
    "ask": ":material/chat:",
    "whatif": ":material/science:",
    "suggestion": ":material/lightbulb:",
    "surprises": ":material/thunderstorm:",
    "financing": ":material/payments:",
    "accounts": ":material/account_balance:",
    "questions": ":material/quiz:",
    "basis": ":material/fact_check:",
    "settings": ":material/settings:",
}
GROUP_ICONS = {
    "home": ":material/home:",
    "ask": ":material/chat:",
    "business": ":material/storefront:",
    "settings": ":material/settings:",
}


def counts() -> dict[str, int]:
    """Open alerts (counted until dismissed or solved, not just seen) and questions left."""
    try:
        get_settings().validate()
        core = get_core()
        return {"alerts": core.open_alert_count(), "questions": core.questions_left() or 0}
    except (ValueError, RuntimeError):
        return {"alerts": 0, "questions": 0}


def with_count(label: str, n: int) -> str:
    return f"{label} ({n})" if n else label


badges = counts()
group_badges = {"home": badges["alerts"], "business": badges["questions"]}
pages = {
    key: st.Page(
        path,
        title=with_count(copy.NAV[key], badges.get(key, 0)),
        icon=ICONS[key],
        default=key == "dashboard",
    )
    for key, path in PAGES.items()
}

# roadmap R.2: nine sidebar entries became four, each with its own row of sub-tabs
current = st.navigation(list(pages.values()), position="hidden")
here = next((key for key, page in pages.items() if page.url_path == current.url_path), "dashboard")

st.logo("assets/logo_wordmark_transparent.png", icon_image="assets/logo_mark_transparent.png", size="large")
with st.sidebar:
    for group, members in GROUPS.items():
        # the entry opens the page the owner is on when it's in that group, so it shows as active
        target = here if here in members else members[0]
        st.page_link(
            pages[target],
            label=with_count(copy.NAV_GROUPS[group], group_badges.get(group, 0)),
            icon=GROUP_ICONS[group],
        )
    st.caption(copy.TAGLINE)

members = GROUPS[group_of(here)]
if len(members) > 1:
    inject_theme()
    with st.container(horizontal=True, key="subtabs"):
        for key in members:
            st.page_link(pages[key], label=pages[key].title, icon=ICONS[key])

current.run()
