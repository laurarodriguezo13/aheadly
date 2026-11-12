"""How much to trust the forecast (roadmap 2.8): high, medium or low, with the two biggest reasons
in plain words. Each check is computed from the owner's own data; the level is the weakest picture
they give together (any weak check: at most medium; two or more: low)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Check:
    name: str
    grade: int  # 2 good, 1 fair, 0 weak
    text: str  # what it means, in plain words


def history_check(days: int) -> Check:
    months = days / 30.4
    if days >= 300:
        return Check("history", 2, f"About {months:.0f} months of statements to learn from.")
    if days >= 90:
        return Check(
            "history", 1, f"Only about {months:.0f} months of statements: a full year would show the seasons."
        )
    return Check("history", 0, f"Only {days} days of statements: the forecast has little to learn from.")


def unidentified_check(share: float) -> Check:
    if share <= 0.05:
        return Check("unidentified", 2, "Almost every payment has a clear description.")
    grade = 1 if share <= 0.15 else 0
    return Check(
        "unidentified",
        grade,
        f"{share:.0%} of recent payments have no clear description (answering the questions fixes this).",
    )


def statement_check(breaks: int) -> Check:
    if breaks == 0:
        return Check("statement", 2, "The statement's running balance adds up line by line.")
    return Check(
        "statement", 0, f"The running balance doesn't add up in {breaks} place(s): some lines may be missing."
    )


def backtest_check(error: float | None) -> Check:
    """`error`: average daily miss when forecasting the last four weeks from the weeks before, as a
    share of the typical day's money in and out."""
    if error is None:
        return Check("backtest", 1, "Too little history to test the forecast on your own past.")
    if error <= 0.35:
        return Check(
            "backtest", 2, f"Tested on your last four weeks, it missed a typical day by about {error:.0%}."
        )
    grade = 1 if error <= 0.6 else 0
    return Check(
        "backtest",
        grade,
        f"Tested on your last four weeks, it missed a typical day by about {error:.0%}: your days vary a lot.",
    )


def answers_check(answered: int, total: int) -> Check:
    """Questions actually answered (skipped ones don't count) out of all asked."""
    if total and answered >= total:
        return Check("answers", 2, "You answered the questions about your business.")
    if answered:
        return Check("answers", 1, f"You answered {answered} of {total} questions about your business.")
    return Check(
        "answers", 1, "The questions about your business aren't answered yet (busy months, your own pay)."
    )


def level(checks: list[Check]) -> dict:
    weak = sum(c.grade == 0 for c in checks)
    fair = sum(c.grade == 1 for c in checks)
    name = "low" if weak >= 2 else "medium" if weak or fair >= 2 else "high"
    reasons = [c.text for c in sorted(checks, key=lambda c: c.grade)[:2]]
    if name == "high":
        reasons = [c.text for c in checks if c.grade == 2][:2]
    return {"level": name, "reasons": reasons, "checks": checks}
