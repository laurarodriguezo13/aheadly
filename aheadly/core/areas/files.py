"""The owner's files: bank statements, the examples, the saved file, files they keep (2.1, 2.5, 5.1, 5.6)."""

from __future__ import annotations

import logging


from aheadly.ai import categorizer
from aheadly import version
from aheadly.core import data_file
from aheadly.core.examples import DEFAULT_EXAMPLE, example_names, load_example
from aheadly.data.connectors.base import Connector
from aheadly.data.connectors import owner_files
from aheadly.data.connectors.csv_connector import CsvConnector, describe_statement

from aheadly.core.areas.shared import (
    CARD_PAYMENT,
    _from_statement,
    _already_planned,
)

logger = logging.getLogger(__name__)


class FilesMixin:
    """Part of `AppCore` (issue 14): the owner's files: bank statements, the examples, the saved file, files they keep (2.1, 2.5, 5.1, 5.6)."""

    def connect(self, connector: Connector) -> int:
        """Feature 1: link a data source once; transactions then live in the repository."""
        return self.connect_files([connector])

    @staticmethod
    def balances_needed(files: list[tuple[str, bytes]]) -> list[dict]:
        """The statements whose balance today can't be read anywhere in the file (no Balance column, no
        "Saldo actual" above the table): the page asks the owner for each, what's owed for a card."""
        needed = []
        for name, content in files:
            try:
                info = describe_statement(content, name)
            except ValueError:  # a file we can't read at all: the upload itself says why
                continue
            if not info["balance_found"]:
                needed.append({"name": name, "card": info["card"]})
        return needed

    def connect_statements(self, files: list[tuple[str, bytes]], balances: dict, profile: dict) -> list:
        """The upload page's statements: (file name, content) each, a typed balance by file name for
        those that need one, and the business's profile. Returns the connectors (what they found)."""
        connectors = [
            CsvConnector(content, balances.get(name), name, business_profile=profile)
            for name, content in files
        ]
        self.connect_files(connectors)
        return connectors

    def connect_files(self, connectors: list[Connector]) -> int:
        """Upload one or more statements. A statement that shares lines with an account already here
        is another period of that account (its balance is the newest file's); any other file is a
        new account (bank or credit card). Then transfers between the owner's own accounts are
        found, and the forecast runs once. Returns how many new transactions came in."""
        if not connectors:
            raise ValueError("Choose at least one bank statement.")
        profile = {"low_cash_line": self.settings.default_low_cash_line, **connectors[0].business_profile()}
        business = self.repo.get_business() or self.repo.create_business(**profile)
        if self._pending_time_zone:
            self.set_time_zone(self._pending_time_zone)
        added = 0
        for connector in connectors:
            payload = connector.sync()
            newest = max((t.date for t in payload.transactions), default=None)
            account_id = self.repo.account_with_any(
                business.id, [t.external_id for t in payload.transactions]
            )
            if account_id is None:
                account_id = self.repo.add_account(
                    business.id, connector.source, payload.account_name, payload.balance, payload.account_kind
                )
            else:
                last = self.repo.account_last_date(account_id)
                if newest is not None and (last is None or newest >= last):
                    self.repo.set_account_balance(account_id, payload.balance)
            added += self.repo.add_transactions(business.id, account_id, payload.transactions)
            if getattr(payload, "holder", None) and not self.repo.get_profile(business.id).get(
                "statement_holder"
            ):
                self.repo.save_profile(business.id, {"statement_holder": payload.holder})  # owner's pay hint
            if payload.scheduled_items:
                self.repo.add_scheduled_items(business.id, payload.scheduled_items)
        self._mark_internal_transfers(business.id)
        self._categorize(business.id)
        self._detect_recurring(business.id)
        logger.info("connected %s file(s): %s transactions", len(connectors), added)
        self.run_daily_check(force=True)
        breaks = sum(getattr(c, "balance_breaks", 0) or 0 for c in connectors)
        self.repo.save_profile(business.id, {"balance_breaks": breaks})  # for the confidence check (2.8)
        return added

    def load_example(self, slug: str = DEFAULT_EXAMPLE) -> int:
        """Roadmap 1.5 / 5.6: replace whatever is here with one of the example businesses, read exactly
        like an owner's upload (its statements) plus the upcoming payments its owner knows about."""
        example = load_example(slug)
        self.reset()
        business = self.repo.create_business(**example.profile)
        self.repo.save_profile(business.id, {"example": example.slug})
        self.repo.add_scheduled_items(business.id, example.upcoming)
        return self.connect_files(
            [
                CsvConnector(content, example.balances.get(name), name, business_profile=example.profile)
                for name, content in example.statements
            ]
        )

    # ------------------------------------------------- download / load my data (roadmap 5.1)
    def export_data(self) -> tuple[str, bytes]:
        """Everything this visit knows about the business, as one file: (file name, content)."""
        business = self._business()
        tables = self.repo.export_tables(business.id, data_file.TABLES, data_file.LEFT_OUT)
        content = data_file.pack(tables, self.repo.schema_version(), version.LOADED, business.name)
        return data_file.file_name(business.name, self.real_today()), content

    def load_data(self, content: bytes) -> dict:
        """Replace this visit's data with a downloaded file's, then check the forecast again as
        if it had just been uploaded. Raises `data_file.DataFileError` (nothing changed) for a file
        that isn't one of ours, is damaged, too big, or comes from a newer version of the app."""
        loaded = data_file.unpack(
            content, self.repo.schema_version(), self.repo.table_columns(data_file.TABLES)
        )
        self.repo.import_tables(loaded.tables)
        self._clear_caches()
        self.run_daily_check(force=True)
        return {
            "business_name": loaded.business_name,
            "transactions": len(loaded.tables["transactions"]),
            "saved_on": loaded.exported_at[:10],
        }

    @staticmethod
    def examples() -> dict[str, str]:
        """The example businesses anyone can try (roadmap 5.6): slug → name, in the picker's order."""
        return example_names()

    def example(self) -> str | None:
        """The example business being shown, or None for the owner's own data."""
        business = self.repo.get_business()
        return self.repo.get_profile(business.id).get("example") if business else None

    # ------------------------------------------------------------ owner's files (roadmap 2.5)
    def read_owner_file(
        self, content: bytes, filename: str, kind: str | None = None, columns: dict[str, str] | None = None
    ) -> owner_files.OwnerFile:
        """Read a file the owner keeps and say what it is and what it would add. Saves nothing.
        `kind`: what the owner says it is, when the app guessed wrong or couldn't tell; `columns`:
        which of the file's columns holds what (role → title), when the titles didn't say."""
        read = owner_files.read_owner_file(content, filename, self.today, kind, columns)
        if read.kind is None and kind is None and read.headers and not read.details.get("looks_like"):
            guess = self.translator.classify_owner_file(read.headers)
            if guess:
                kind_guess, columns = guess
                read = owner_files.read_owner_file(content, filename, self.today, kind_guess, columns)
                read.details["kind_from"] = "ai"
        if read.kind == "employees" and not read.problem:
            read.details["payroll_found_per_month"] = self._payroll_per_month()
        if read.items and any(a["kind"] == "card" for a in self.repo.list_accounts(self._business().id)):
            # the card's statement is here: its purchases already count as spending, so paying the
            # card from the bank must not count again (DECISIONS #62)
            card = [i for i in read.items if i.amount < 0 and CARD_PAYMENT.search(categorizer.plain(i.label))]
            read.items = [i for i in read.items if i not in card]
            if card:
                read.details["card_payments_left_out"] = len(card)
        if read.items:
            planned = [
                i for i in self.repo.list_scheduled_items(self._business().id) if not _from_statement(i)
            ]
            read.details["already_planned"] = sum(1 for i in read.items if _already_planned(i, planned))
        return read

    def use_owner_file(self, read: owner_files.OwnerFile) -> int:
        """The owner confirmed the file: its payments go into the plan (skipping ones already there)
        and the file is remembered. Returns how many items were added."""
        if read.problem or read.kind is None:
            raise ValueError(read.problem or "Pick what this file is first.")
        business = self._business()
        planned = [i for i in self.repo.list_scheduled_items(business.id) if not _from_statement(i)]
        new = [i for i in read.items if not _already_planned(i, planned)]
        self.repo.add_scheduled_items(business.id, new)
        self.repo.record_uploaded_file(business.id, read.name, read.kind, read.columns)
        if new:
            self.run_daily_check(force=True)
        return len(new)

    def uploaded_files(self) -> list[dict]:
        return self.repo.uploaded_files(self._business().id)

    def _payroll_per_month(self) -> float:
        """Pay found in the statement as payroll (wages, not bonuses or social security), per month."""
        per_month = {"weekly": 52 / 12, "every two weeks": 26 / 12, "twice a month": 2.0, "monthly": 1.0}
        total = 0.0
        for r in self.detected_recurring():
            wages = any(
                w in r.match_key for w in ("nomina", "payroll", "salari", "sueldo", "wages", "planilla")
            )
            extra = any(
                w in r.match_key
                for w in ("prima", "pila", "aportes", "temporada", "bonus", "css", "xiii", "decimo")
            )
            if r.category == "payroll" and wages and not extra and not r.seasonal and r.cadence in per_month:
                total += -r.amount * per_month[r.cadence]
        return round(total, 2)
