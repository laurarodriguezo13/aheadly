"""The onboarding questions, what the owner tells us, busy and slow months (2.7, R.3c)."""

from __future__ import annotations

import logging
from datetime import timedelta


from aheadly.ai import categorizer, recurring, seasons
from aheadly.ai import owner_notes
from aheadly.core import onboarding
from aheadly.core.examples import load_example

from aheadly.core.areas.shared import (
    _agreeing,
)

logger = logging.getLogger(__name__)


class QuestionsMixin:
    """Part of `AppCore` (issue 14): the onboarding questions, what the owner tells us, busy and slow months (2.7, R.3c)."""

    # ------------------------------------------------------------ onboarding questions (roadmap 2.7)
    def onboarding(self) -> dict:
        """The questions still to answer, in order, and how far the owner got. Answered and skipped
        questions are remembered (the owner can stop and come back)."""
        business = self._business()
        done = self.repo.get_profile(business.id).get("onboarding_done", [])
        pending = [q for q in self._questions() if q.id not in done]
        self.repo.save_profile(business.id, {"questions_left": len(pending)})
        return {"questions": pending, "done": len(done), "total": len(done) + len(pending)}

    def questions_left(self) -> int | None:
        """How many questions are left, for the sidebar: kept since they were last worked out, and
        worked out the first time when there's data (roadmap R.2, issue 17: the sidebar is drawn
        before the Questions page, so the count only showed after the first answer). None without data."""
        business = self.repo.get_business()
        if not business:
            return None
        left = self.repo.get_profile(business.id).get("questions_left")
        if left is None and self.status().connected:
            left = len(self.onboarding()["questions"])
        return left

    def answer_business(self, business_type: str, customers_pay: str = "") -> None:
        changes = {"business_type": business_type.strip(), "customers_pay": customers_pay.strip()}
        self.repo.save_profile(self._business().id, {k: v for k, v in changes.items() if v})
        self._question_done("business")

    def answer_seasons(
        self, busy: list[int], slow: list[int], changes: dict[int, float] | None = None
    ) -> None:
        self.set_seasons(busy, slow, changes)
        self._question_done("seasons")

    def answer_owner_pay(self, payee: str, is_owner_pay: bool) -> None:
        """Yes: every payment to it is the owner's pay (still money out, but one they can change)."""
        if is_owner_pay:
            self.set_payee_rule(payee, "owner_pay")
        self._question_done(f"owner_pay:{categorizer.match_key(payee)}")

    def answer_mystery(
        self, payee: str, category: str | None = None, words: str = "", guess: str | None = None
    ) -> str:
        """What a payee is: a category picked from the list, or the owner's own words (or both).
        The words win when they name a kind of payment (roadmap R.1: on the live site the list,
        still on the AI's guess "Other income", beat "loan repayment"); the list decides otherwise.
        Returns the category used."""
        said = categorizer.category_from_answer(words) if words.strip() else "other"
        # the list still on the AI's guess is not an answer: the owner's own words are ("my
        # accountant's fee" with the guess "Payroll" left in the list is other, practice run)
        if said != "other" or (words.strip() and category in (None, guess)):
            category = said
        if category:
            self.set_payee_rule(payee, category, words or payee)
        else:
            raise ValueError("Pick a category or say in your own words what it is.")
        self._question_done(f"mystery:{categorizer.match_key(payee)}")
        return category

    # ------------------------------------------------- what the owner tells us (roadmap R.3c)
    def read_anything_else(self, text: str) -> dict:
        """'Is there anything else we should know?': payments to confirm (like "just say it"),
        limits for the suggestions and notes for the chat, as understood. Saves nothing."""
        if not text.strip():
            return {"proposals": [], "limits": [], "notes": []}
        sorted_ = self.translator.sort_owner_notes(text, self.scheduled_labels())
        return {"proposals": self.parse_plan_text(text), **sorted_}

    def keep_anything_else(self, limits: list[dict], notes: list[str]) -> None:
        """What the owner confirmed: limits become "Not for me" rules, notes go to the chat."""
        business = self._business()
        profile = self.repo.get_profile(business.id)
        kept_notes = profile.get("owner_notes", []) + [
            {"text": n.strip(), "added": self.today.isoformat()} for n in notes if n.strip()
        ]
        rules = profile.get("declined_suggestions", []) + [owner_notes.as_rule(limit) for limit in limits]
        self.repo.save_profile(business.id, {"owner_notes": kept_notes, "declined_suggestions": rules})
        self._question_done("anything_else")
        if limits:
            self._suggestions_changed()

    def owner_notes(self) -> list[dict]:
        business = self.repo.get_business()
        return self.repo.get_profile(business.id).get("owner_notes", []) if business else []

    def add_owner_note(self, text: str) -> None:
        if not text.strip():
            raise ValueError("Write the note first.")
        business = self._business()
        notes = self.owner_notes() + [{"text": text.strip(), "added": self.today.isoformat()}]
        self.repo.save_profile(business.id, {"owner_notes": notes})

    def remove_owner_note(self, index: int) -> None:
        notes = self.owner_notes()
        del notes[index]
        self.repo.save_profile(self._business().id, {"owner_notes": notes})

    def remove_declined(self, index: int) -> None:
        """One "Not for me" (or limit the owner told us) taken back: it can be suggested again."""
        rules = self.declined_suggestions()
        del rules[index]
        self.repo.save_profile(self._business().id, {"declined_suggestions": rules})
        self._suggestions_changed()

    def bring_back_insight(self, insight_type: str) -> None:
        profile = self.repo.get_profile(self._business().id)
        set_aside = {k: v for k, v in profile.get("insights_set_aside", {}).items() if k != insight_type}
        self.repo.save_profile(self._business().id, {"insights_set_aside": set_aside})

    def change_payee_answer(self, match_key: str, category: str) -> None:
        """'What you told us': another kind for a payee the owner named (the same payee, by its key;
        the owner's own words stay)."""
        if category not in categorizer.CATEGORIES:
            raise ValueError(f"Unknown category {category!r}.")
        business = self._business()
        row = next((r for r in self.repo.payee_rule_rows(business.id) if r["match_key"] == match_key), None)
        if row is None:
            raise ValueError("There's no answer about that payee.")
        self.repo.save_payee_rule(business.id, match_key, category, row["label"])
        if self._categorize(business.id):
            self._detect_recurring(business.id)
            self.run_daily_check(force=True)

    def forget_payee_answer(self, match_key: str) -> None:
        """'That's not right': the owner's answer about a payee goes, and the rules place it again."""
        business = self._business()
        self.repo.delete_payee_rule(business.id, match_key)
        if self._categorize(business.id):
            self._detect_recurring(business.id)
            self.run_daily_check(force=True)

    def told_us(self) -> dict:
        """'What you told us' (roadmap R.3c): every answer the owner gave, to see and change."""
        business = self._business()
        profile = self.repo.get_profile(business.id)
        rules = [
            {
                **r,
                "payee": r["match_key"].upper(),
                "said": r["label"] if r["label"].lower() != r["match_key"] else "",
            }
            for r in self.repo.payee_rule_rows(business.id)
        ]
        titles = {card["type"]: card["title"] for card in self.insight_cards()}
        return {
            "business_type": profile.get("business_type", ""),
            "customers_pay": profile.get("customers_pay", ""),
            "seasons": self.seasons(),
            "owner_pay": [r for r in rules if r["category"] == "owner_pay"],
            "payees": [r for r in rules if r["category"] != "owner_pay"],
            "notes": self.owner_notes(),
            "limits": self.declined_suggestions(),
            "set_aside": [
                {"type": t, "title": titles.get(t, t), "reason": reason}
                for t, reason in profile.get("insights_set_aside", {}).items()
            ],
        }

    def nothing_coming_up(self, question_id: str = "coming_up") -> None:
        """'Nothing else for now' answers the question (nothing big is coming): it counts as answered,
        not skipped (roadmap R.1: the trust box said 4 of 5 after it)."""
        self._question_done(question_id)

    def skip_question(self, question_id: str) -> None:
        """Skipped: not asked again, but not counted as answered (confidence, roadmap 2.8)."""
        business = self._business()
        skipped = list(self.repo.get_profile(business.id).get("onboarding_skipped", []))
        if question_id not in skipped:
            self.repo.save_profile(business.id, {"onboarding_skipped": skipped + [question_id]})
        self._question_done(question_id, skipping=True)

    def example_answers(self) -> dict:
        """The example owner's own answers, to pre-fill the questions when trying the example."""
        example = self.example()
        return load_example(example).answers if example else {}

    def _question_done(self, question_id: str, skipping: bool = False) -> None:
        business = self._business()
        profile = self.repo.get_profile(business.id)
        skipped = profile.get("onboarding_skipped", [])
        if not skipping and question_id in skipped:  # answered after all (e.g. busy months, later)
            self.repo.save_profile(
                business.id, {"onboarding_skipped": [q for q in skipped if q != question_id]}
            )
        done = list(profile.get("onboarding_done", []))
        if question_id not in done:
            done.append(question_id)
        left = self.repo.get_profile(business.id).get("questions_left")
        changes = {"onboarding_done": done}
        if left:
            changes["questions_left"] = left - 1
        self.repo.save_profile(business.id, changes)

    def _questions(self) -> list[onboarding.Question]:
        business = self._business()
        end = self.statement_end() or self.today
        since = end - timedelta(days=90)
        how_often = {}
        for item in self.detected_recurring():
            if item.rules and item.next_dates:
                rule = recurring.recurrence_for(item.rules[0])
                how_often[item.match_key] = recurring.describe(rule, item.next_dates[0])
        # one-off small change isn't worth a question; anything that repeats is (it's in the forecast)
        floor = 0.01 * self.repo.flow_totals(business.id, since)["money_out"]
        payees = [
            p
            for p in self.repo.uncategorized_payees(business.id, since)
            if abs(p["total"]) >= floor or categorizer.match_key(p["description"]) in how_often
        ]
        # every payee that may be asked about, in one call: answering one brings the next into the
        # list, and a call per answer made each answer slow on the free tier (practice run 2)
        names = [p["description"] for p in payees[:20]]
        profile = self.repo.get_profile(business.id)
        owner_words = onboarding.owner_name_words(
            profile.get("statement_holder", ""), business.owner_name or "", business.name or ""
        )
        return onboarding.build(profile, payees, self._category_suggestions(names), how_often, owner_words)

    def _category_suggestions(self, payees: list[str]) -> dict[str, tuple[str, str]]:
        """The connected model's guess for each payee (names only, one call, kept so reruns don't
        call it again). Nothing is applied until the owner confirms."""
        if not payees:
            return {}
        business = self._business()
        kept = self.repo.get_profile(business.id).get("category_suggestions", {})
        missing = [p for p in payees if p not in kept]
        if missing:
            found = self.translator.suggest_categories(missing)
            kept = {**kept, **{p: list(found.get(p, ("", ""))) for p in missing}}
            self.repo.save_profile(business.id, {"category_suggestions": kept})
        return {p: (c, why) for p, (c, why) in kept.items() if p in payees and c}

    # ------------------------------------------------------------ busy and slow months (roadmap 2.7)
    def seasons(self) -> dict:
        """The owner's busy and slow months, what the statement says about each (last time it came,
        how much more or less money came in than in a normal month) and the change the forecast uses."""
        business = self._business()
        profile = self.repo.get_profile(business.id)
        busy, slow = profile.get("busy_months", []), profile.get("slow_months", [])
        money_in = seasons.daily_money_in(self.repo.daily_in_out(business.id))
        found = seasons.month_estimates(money_in, busy, slow)
        own = {int(m): v for m, v in profile.get("season_changes", {}).items()}
        months = [
            {
                "month": m,
                "name": seasons.MONTH_NAMES[m],
                "kind": "busy" if m in busy else "slow",
                "from_statement": found.get(m),
                "owners": own.get(m),
                "used": own[m] if m in own else _agreeing(found.get(m), m in busy),
            }
            for m in sorted(set(busy) | set(slow))
        ]
        return {
            "answered": "busy_months" in profile,
            "months": months,
            "level": seasons.recent_level(money_in),
        }

    def season_estimates(self, busy: list[int], slow: list[int]) -> dict[int, float | None]:
        """What the statement says about months the owner is about to mark (before saving)."""
        money_in = seasons.daily_money_in(self.repo.daily_in_out(self._business().id))
        return seasons.month_estimates(money_in, busy, slow)

    def set_seasons(self, busy: list[int], slow: list[int], changes: dict[int, float] | None = None) -> None:
        """Save the owner's answer. `changes`: their own estimate for a month (+0.5 = 50% more money
        in than a normal month), replacing the one from the statement. The forecast reruns."""
        busy = sorted({int(m) for m in busy})
        slow = sorted({int(m) for m in slow} - set(busy))
        own = {str(m): seasons.clamp(float(v)) for m, v in (changes or {}).items() if v is not None}
        self.repo.save_profile(
            self._business().id, {"busy_months": busy, "slow_months": slow, "season_changes": own}
        )
        self.run_daily_check(force=True)

    def _month_shift(self, business_id: int) -> dict[int, float]:
        profile = self.repo.get_profile(business_id)
        if not profile.get("busy_months") and not profile.get("slow_months"):
            return {}
        info = self.seasons()
        return seasons.daily_shift(info["level"], {m["month"]: m["used"] for m in info["months"]})
