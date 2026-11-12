"""Small reusable UI pieces (cards, pills, lists). HTML is built from trusted app data only."""

from __future__ import annotations

import html

import streamlit as st

from aheadly.timefmt import format_local
from aheadly.ui import copy


def money(value: float) -> str:
    value = round(value)
    return f"-${-value:,}" if value < 0 else f"${value:,}"


def day(d) -> str:
    """Nov 10, 2026 (no zero padding, works on every operating system)."""
    return f"{d:%b} {d.day}, {d.year}"


def browser_time_zone() -> str | None:
    """The visitor's time zone as their browser reports it ("America/New_York"), if known."""
    try:
        return st.context.timezone
    except Exception:  # older Streamlit, or no browser (tests): unknown
        return None


def local_time(value) -> str:
    """A stored time (UTC) in the visitor's own time zone."""
    return format_local(value, browser_time_zone())


def statement_notice(end, start, lag_days: int, example_name: str | None = None) -> None:
    """Say when the statement stops before yesterday, so the forecast can't start today.
    The example business always says it is an example instead (its statement is fixed)."""
    if example_name:
        st.info(copy.EXAMPLE_NOTICE.format(name=example_name, end=day(end), start=day(start)))
    elif lag_days >= 7:
        st.warning(copy.STATEMENT_OLD.format(end=day(end), start=day(start), days=lag_days + 1))
    elif lag_days > 0:
        st.info(copy.STATEMENT_BEHIND.format(end=day(end), start=day(start)))


def weeks(n: int) -> str:
    return "1 week" if n == 1 else f"{n} weeks"


def stat_card(label: str, value: str, sub: str = "", tone: str = "", background: str = "lav") -> None:
    st.markdown(
        f'<div class="ah-card {background}"><div class="ah-label">{html.escape(label)}</div>'
        f'<div class="ah-value {tone}">{html.escape(value)}</div>'
        f'<div class="ah-sub">{html.escape(sub)}</div></div>',
        unsafe_allow_html=True,
    )


def card(body_html: str, background: str = "") -> None:
    st.markdown(f'<div class="ah-card {background}">{body_html}</div>', unsafe_allow_html=True)


def info_card(title: str, body_html: str, background: str = "", icon: str = "", tall: bool = True) -> None:
    """Titled card used for the alert blocks (storyboard frame 4)."""
    icon_html = f'<span class="ah-icon">{html.escape(icon)}</span>' if icon else ""
    classes = f"ah-card {background} {'tall' if tall else ''}"
    st.markdown(
        f'<div class="{classes}"><div class="ah-card-title">{icon_html}{html.escape(title)}</div>{body_html}</div>',
        unsafe_allow_html=True,
    )


def section_title(title: str) -> None:
    st.markdown(f'<div class="ah-card-title">{html.escape(title)}</div>', unsafe_allow_html=True)


def check_list_html(items: list[tuple[str, str]]) -> str:
    rows = "".join(
        f'<li><span class="ah-tick">✓</span><div><b>{html.escape(label)}</b>'
        f'<div class="ah-muted">{html.escape(detail)}</div></div></li>'
        for label, detail in items
    )
    return f'<ul class="ah-list">{rows}</ul>'


def rows_html(rows: list[tuple[str, str]]) -> str:
    return "".join(
        f'<div class="ah-row"><span>{html.escape(label)}</span><b>{html.escape(value)}</b></div>'
        for label, value in rows
    )


def alert_list_html(alerts) -> str:
    items = "".join(
        f'<li><span class="ah-dot {a.severity}">!</span><div><b>{html.escape(a.title)}</b>'
        f'<div class="ah-muted">in {weeks(a.weeks_ahead)}</div></div></li>'
        for a in alerts
    )
    return f'<ul class="ah-list">{items}</ul>'


def banner(text: str, icon: str = "✦") -> None:
    st.markdown(
        f'<div class="ah-banner"><span class="ah-icon">{icon}</span>{html.escape(text)}</div>',
        unsafe_allow_html=True,
    )


def severity_pill(severity: str) -> str:
    return f'<span class="ah-pill {severity}">{severity.upper()}</span>'


def hero(title: str, body: str) -> None:
    st.markdown(
        f'<div class="ah-hero"><h2>{html.escape(title)}</h2><p>{html.escape(body)}</p></div>',
        unsafe_allow_html=True,
    )


def scenario_metrics(result) -> None:
    """Best / Base / Worst lowest balance of a what-if (storyboard frame 5 result card)."""
    scen = result.scenario
    cols = st.columns(3)
    values = [
        (copy.BEST_CASE, scen.min_p90, "teal"),
        (copy.BASE_CASE, scen.lowest.balance_p50, "purple"),
        (copy.WORST_CASE, scen.min_p10, ""),
    ]
    for col, (label, value, tone) in zip(cols, values):
        tone = "red" if value < result.low_cash_line else tone
        with col:
            stat_card(label, money(value), copy.LOWEST_BALANCE, tone, "sky" if tone != "red" else "rose")


def proposal_card(core, items, key: str) -> int:
    """Roadmap 2.4: plan items read from the owner's words, editable, saved only on Add.
    Returns how many were added (0 if not yet)."""
    names = {v: k for k, v in copy.DIRECTION_NAMES.items()}
    cols = copy.PROPOSAL_COLUMNS
    st.caption(copy.PROPOSAL_INTRO)
    rows = [
        {
            cols["label"]: i.label,
            cols["direction"]: copy.DIRECTION_NAMES[i.direction],
            cols["amount"]: i.amount,
            cols["due_date"]: i.due_date,
            cols["repeats"]: i.repeats,
            cols["maybe"]: i.certainty == "maybe",
        }
        for i in items
    ]
    edited = st.data_editor(
        rows,
        key=f"{key}-editor",
        hide_index=True,
        num_rows="dynamic",
        width="stretch",
        column_config={
            cols["direction"]: st.column_config.SelectboxColumn(options=list(copy.DIRECTION_NAMES.values())),
            cols["amount"]: st.column_config.NumberColumn(min_value=0.0, format="dollar"),
            cols["due_date"]: st.column_config.DateColumn(format="MMM D, YYYY"),
            cols["repeats"]: st.column_config.SelectboxColumn(
                options=["once", "weekly", "every two weeks", "monthly"]
            ),
        },
    )
    for item in items:
        if item.problem:
            st.caption(f"⚠ {item.label or 'An item'}: {item.problem}")
    if not st.button(copy.ADD_TO_PLAN, key=f"{key}-add", type="primary"):
        return 0
    chosen = [
        {
            "label": row.get(cols["label"]),
            "direction": names.get(row.get(cols["direction"]), "out"),
            "amount": row.get(cols["amount"]),
            "date": row.get(cols["due_date"]),
            "repeats": row.get(cols["repeats"]) or "once",
            "certainty": "maybe" if row.get(cols["maybe"]) else "sure",
        }
        for row in edited
        if row.get(cols["label"]) or row.get(cols["amount"])
    ]
    try:
        return core.add_plan_items(chosen)
    except ValueError as exc:
        st.error(copy.ADD_PROBLEM.format(problem=exc))
        return 0


def owner_file_card(core, entry: dict, key: str) -> str | None:
    """Roadmap 2.5: one file the owner keeps: what we found, the kind (they can change it), and
    Use / Skip. `entry` = {"name", "content", "read"}. Returns "used", "skipped" or None."""
    read = entry["read"]
    kinds = list(copy.OWNER_KIND_NAMES)
    with st.container(border=True):
        st.markdown(f"**{html.escape(read.name)}**")
        current = kinds.index(read.kind) if read.kind in kinds else None
        picked = st.selectbox(
            copy.OWNER_FILE_KIND,
            kinds,
            index=current,
            format_func=lambda k: copy.OWNER_KIND_NAMES[k],
            key=f"{key}-kind",
            placeholder="Pick what this file is",
        )
        if picked and picked != read.kind:
            read = entry["read"] = core.read_owner_file(
                entry["content"], read.name, picked, entry.get("columns")
            )
        if read.details.get("kind_from") == "ai":
            st.caption(copy.OWNER_FILE_AI)
        if read.problem:
            st.warning(read.problem)
        missing = read.details.get("missing_roles", [])
        if missing:  # the titles didn't say: the owner points at the columns
            samples = read.details.get("samples", {})
            hint = dict(entry.get("columns") or {})
            for col, role in zip(st.columns(len(missing)), missing):
                choice = col.selectbox(
                    copy.OWNER_COLUMN_PICK.format(role=copy.OWNER_ROLE_NAMES.get(role, role)),
                    read.headers,
                    index=None,
                    format_func=lambda h: f"{h} (e.g. {samples[h]})" if samples.get(h) else h,
                    key=f"{key}-col-{role}",
                )
                if choice:
                    hint[role] = choice
            if hint != (entry.get("columns") or {}):
                entry["columns"] = hint
                entry["read"] = core.read_owner_file(entry["content"], read.name, picked or read.kind, hint)
                st.rerun()
        elif read.kind:
            st.write(owner_file_summary(read))
            if read.details.get("skipped"):
                st.caption(copy.OWNER_SKIPPED.format(n=read.details["skipped"]))
            if read.details.get("total_rows"):
                st.caption(copy.OWNER_TOTAL_ROWS.format(n=read.details["total_rows"]))
            if read.items:
                st.dataframe(
                    [
                        {"What": i.label, "Date": day(i.due_date), "Amount": money(i.amount),
                         "Sure?": "maybe" if i.certainty == "maybe" else "yes"}
                        for i in read.items
                    ],
                    hide_index=True,
                    width="stretch",
                )  # fmt: skip
            if read.details.get("already_planned"):
                st.caption(copy.OWNER_FILE_ALREADY.format(n=read.details["already_planned"]))
        use_col, skip_col = st.columns([1, 4])
        if use_col.button(copy.OWNER_FILE_USE, key=f"{key}-use", type="primary", disabled=bool(read.problem)):
            added = core.use_owner_file(read)
            st.session_state.setdefault("owner_file_notes", []).append(
                copy.OWNER_FILE_USED.format(name=read.name, n=added)
                if read.items
                else copy.OWNER_FILE_NOTED.format(name=read.name)
            )
            return "used"
        if skip_col.button(copy.OWNER_FILE_SKIP, key=f"{key}-skip"):
            return "skipped"
    return None


def owner_file_summary(read) -> str:
    """One plain sentence or two about what a file holds."""
    d = read.details
    if read.kind == "upcoming_payments":
        dates = sorted(i.due_date for i in read.items) or [None]
        return copy.OWNER_SUMMARY["upcoming_payments"].format(
            rows=read.rows,
            n_in=sum(1 for i in read.items if i.amount > 0),
            n_out=sum(1 for i in read.items if i.amount < 0),
            first=day(dates[0]) if dates[0] else "-",
            last=day(dates[-1]) if dates[-1] else "-",
            past=d.get("already_past", 0),
        )
    if read.kind == "receivables":
        return copy.OWNER_SUMMARY["receivables"].format(
            rows=read.rows,
            total=money(read.total),
            overdue=read.overdue_rows,
            doubtful=len(d.get("doubtful", [])),
        )
    if read.kind == "employees":
        text = copy.OWNER_SUMMARY["employees"].format(
            rows=read.rows,
            total=money(read.total),
            period=d["period"],
            per_month=money(d["per_month"]),
            found=money(d.get("payroll_found_per_month", 0)),
        )
        found = d.get("payroll_found_per_month", 0)
        if found and abs(found - d["per_month"]) > 0.1 * d["per_month"]:
            text += " " + copy.OWNER_SUMMARY["employees_mismatch"]
        return text
    if read.kind == "ledger":
        return copy.OWNER_SUMMARY["ledger"].format(rows=read.rows, total=money(read.total))
    low = d.get("below_reorder", [])
    names = f": {', '.join(low[:5])}" if low else ""
    return copy.OWNER_SUMMARY["inventory"].format(
        rows=read.rows, total=money(read.total), low=len(low), names=names
    )
