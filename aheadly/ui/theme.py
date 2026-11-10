"""Brand theme on top of `.streamlit/config.toml`.

The config file carries fonts, colours and radii (Streamlit's native theme options).
This module only adds the brand pieces Streamlit has no option for: pastel cards,
severity pills, the gradient hero and a few spacing tweaks.
"""

from __future__ import annotations

import streamlit as st

TOKENS = {
    "navy": "#13134A",
    "ink": "#3B3F6B",
    "purple": "#7B4DFF",
    "blue": "#1E9BFF",
    "teal": "#2CC4B8",
    "red": "#EF4F5F",
    "lav": "#F2EDFF",
    "sky": "#E9F4FF",
    "mint": "#E5F7F4",
    "rose": "#FDECEE",
    "line": "#E6E0FA",
}

_CSS = """
<style>
:root {{ --navy:{navy}; --ink:{ink}; --purple:{purple}; --blue:{blue}; --teal:{teal}; --red:{red};
        --lav:{lav}; --sky:{sky}; --mint:{mint}; --rose:{rose}; --line:{line};
        --gradient: linear-gradient(135deg, {purple} 0%, {blue} 100%); --radius-card: 20px;
        --shadow-card: 0 24px 60px rgba(80,60,180,.10), 0 3px 10px rgba(80,60,180,.05); }}

/* layout */
.block-container {{ padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1180px; }}
header[data-testid="stHeader"] {{ background: transparent; }}
h1 {{ letter-spacing: -0.03em; margin-bottom: .4rem; }}
h2, h3 {{ letter-spacing: -0.02em; }}
[data-testid="stLogo"] {{ height: 2.6rem; width: auto; max-width: 100%; margin: .4rem 0 .6rem .2rem; }}

/* Streamlit bordered containers become brand cards */
[data-testid="stVerticalBlockBorderWrapper"] > div:first-child {{
  border-radius: var(--radius-card) !important; border-color: var(--line) !important;
  box-shadow: var(--shadow-card); padding: 1.1rem 1.3rem !important; background: #fff; }}
[data-testid="stForm"] {{ border-radius: var(--radius-card); border-color: var(--line);
  box-shadow: var(--shadow-card); padding: 1.3rem 1.5rem; }}

/* buttons */
.stButton > button[kind="primary"], [data-testid="stFormSubmitButton"] button,
[data-testid="stBaseButton-primaryFormSubmit"] {{
  background: var(--gradient); border: none; font-weight: 600; padding: .55rem 1.4rem;
  box-shadow: 0 8px 20px rgba(123,77,255,.25); }}
.stButton > button[kind="secondary"] {{ border: 1px solid var(--line); color: var(--navy); font-weight: 500;
  background: #fff; }}
.stButton > button[kind="secondary"]:hover {{ border-color: var(--purple); color: var(--purple); background: var(--lav); }}

/* chat */
[data-testid="stChatMessage"] {{ border-radius: var(--radius-card); padding: 1rem 1.2rem; }}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {{ background: var(--lav); }}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarCustom"]) {{
  background: #fff; border: 1px solid var(--line); box-shadow: var(--shadow-card); }}

/* brand components */
.ah-card {{ background: #fff; border: 1px solid var(--line); border-radius: var(--radius-card);
  box-shadow: var(--shadow-card); padding: 1.25rem 1.4rem; margin-bottom: 1rem; }}
.ah-card.lav {{ background: var(--lav); }} .ah-card.sky {{ background: var(--sky); }}
.ah-card.mint {{ background: var(--mint); }} .ah-card.rose {{ background: var(--rose); }}
.ah-card.tall {{ min-height: 240px; }}
.ah-card p {{ margin: 0; color: var(--ink); line-height: 1.5; }}
.ah-card h3 {{ margin: .5rem 0 .4rem; font-size: 1.45rem; }}
.ah-label {{ font-size: .85rem; font-weight: 600; color: var(--ink); margin-bottom: .3rem; }}
.ah-value {{ font-size: 2.3rem; font-weight: 800; line-height: 1.1; color: var(--navy); letter-spacing: -0.03em; }}
.ah-value.purple {{ color: var(--purple); }} .ah-value.red {{ color: var(--red); }} .ah-value.teal {{ color: #15807A; }}
.ah-sub {{ font-size: .9rem; color: var(--ink); margin-top: .4rem; }}
.ah-card-title {{ font-size: 1.05rem; font-weight: 700; color: var(--navy); margin-bottom: .8rem;
  display: flex; align-items: center; gap: .6rem; }}
.ah-icon {{ display: inline-flex; width: 1.9rem; height: 1.9rem; border-radius: 999px; align-items: center;
  justify-content: center; background: var(--gradient); color: #fff; font-size: .95rem; font-weight: 700;
  font-style: normal; }}
.ah-pill {{ display:inline-block; border-radius: 999px; padding: .2rem .75rem; font-size: .72rem; font-weight: 700;
  letter-spacing: .04em; }}
.ah-pill.high {{ background: var(--rose); color: var(--red); }} .ah-pill.medium {{ background: #FFF4E0; color: #B26A00; }}
.ah-pill.low {{ background: var(--mint); color: #15807A; }} .ah-pill.info {{ background: var(--sky); color: #0B6FC2; }}
.ah-hero {{ background: var(--gradient); color: #fff; border-radius: var(--radius-card); padding: 1.8rem 2rem;
  box-shadow: var(--shadow-card); }}
.ah-hero h2, .ah-hero p {{ color: #fff !important; margin: 0; }}
.ah-hero h2 {{ font-size: 1.9rem; margin-bottom: .5rem; }}
.ah-hero p {{ font-size: 1.05rem; opacity: .95; }}
.ah-list {{ list-style: none; padding: 0; margin: 0; }}
.ah-list li {{ display: flex; gap: .7rem; align-items: flex-start; padding: .45rem 0; }}
.ah-list li + li {{ border-top: 1px solid var(--line); }}
.ah-list b {{ color: var(--navy); font-weight: 600; }}
.ah-tick {{ color: var(--teal); font-weight: 800; font-size: 1.1rem; line-height: 1.3; }}
.ah-row {{ display: flex; justify-content: space-between; gap: 1rem; padding: .5rem 0; color: var(--ink); }}
.ah-row b {{ white-space: nowrap; }}
.ah-row + .ah-row {{ border-top: 1px solid var(--line); }}
.ah-row b {{ color: var(--navy); font-weight: 700; }}
.ah-dot {{ display: inline-flex; width: 1.6rem; height: 1.6rem; border-radius: 999px; align-items: center;
  justify-content: center; color: #fff; font-weight: 800; font-size: .9rem; flex: none; }}
.ah-dot.high {{ background: var(--red); }} .ah-dot.medium {{ background: #F5A623; }}
.ah-dot.low, .ah-dot.info {{ background: var(--teal); }}
.ah-banner {{ background: var(--lav); border-radius: var(--radius-card); padding: 1rem 1.3rem; display: flex;
  align-items: center; gap: .9rem; font-weight: 600; color: var(--navy); margin: .5rem 0 1rem; }}
.ah-check {{ color: var(--teal); font-weight: 800; }}
.ah-muted {{ color: var(--ink); font-size: .9rem; }}
</style>
"""


def inject_theme() -> None:
    st.markdown(_CSS.format(**TOKENS), unsafe_allow_html=True)
