"""All user-facing strings (English for the MVP; es-CO can be added here later)."""

APP_NAME = "Aheadly"
TAGLINE = "Clarity today. A brighter tomorrow."

NAV = {
    "dashboard": "Dashboard",
    "questions": "Questions",
    "alerts": "Alerts",
    "ask": "Ask Aheadly",
    "whatif": "What-if",
    "accounts": "Accounts",
    "basis": "How we built it",
    "settings": "Settings",
}

WELCOME_TITLE = "Know what's coming."
WELCOME_BODY = (
    "Upload your bank statement and Aheadly shows what's coming, warns you weeks before cash runs low, "
    "and answers your questions in plain words."
)
ALL_SET = "All set. We'll check your money every time you open Aheadly."
NOT_CONNECTED = "No data yet. Upload your bank statement on **Accounts** to get started."
GO_TO_ACCOUNTS = "Upload my bank statement"
UPLOAD_TITLE = "Upload your bank statements"
UPLOAD_HELP = (
    "CSV or Excel exports from your bank with Date, Description and Amount (or Debit and Credit). "
    "If they have a Balance column, we read your current balance from them. You can add several files at "
    "once: your other accounts, your business credit card, or older periods of the same account."
)
BUSINESS_NAME = "Business name"
OWNER_NAME = "Your name (optional)"
STATEMENT_FILE = "Bank statements (CSV or Excel, one or more)"
UPCOMING_FILE = "Other files you keep (optional, CSV or Excel, one or more)"
UPCOMING_HELP = (
    "Upcoming payments, money customers owe you, your employee list, a ledger or your inventory, in "
    "whatever layout you use. We'll show you what we found in each before using it."
)
LOW_CASH_LINE_INPUT = "Lowest balance you're comfortable with ($)"
BALANCE_INPUT = "Current balance ($, only if your statement has no Balance column)"
BALANCE_PLACEHOLDER = "Read from the statement"
UPLOAD_BUTTON = "Upload and analyse"
UPLOAD_SPINNER = "Reading your statement and building your forecast…"
UPLOAD_FAILED = "We couldn't read that file: {error}"
MULTI_NO_BALANCE = (
    "One of your statements has no Balance column. When you upload several files, each needs one. "
    "Upload that statement on its own and type its current balance."
)
EXAMPLE_TITLE = "No files at hand? Try an example business"
EXAMPLE_HELP = (
    "Load Panadería La Esquina, a bakery in Bogotá: a year of bank statements plus the payments its owner "
    "knows are coming (a new oven, a big flour order, two Christmas orders). Nothing of yours is uploaded. "
    "To use your own files afterwards, go to Settings and click Start over."
)
EXAMPLE_BUTTON = "Try the example bakery"
EXAMPLE_SPINNER = "Loading the example bakery and building its forecast…"
EXAMPLE_NOTICE = (
    "This is an example business, {name}. Its statement ends {end}, so Aheadly shows it as of {start}. "
    "To use your own files, go to Settings and click Start over."
)
OWNER_FILES_TITLE = "Files you keep"
OWNER_FILES_HELP = (
    "Upcoming payments, money customers owe you, your employee list, a ledger or your inventory. Any layout: "
    "we read the column titles and show you what we found before using anything."
)
OWNER_FILES_UPLOAD = "Add files you keep (CSV or Excel)"
OWNER_FILE_KIND = "This file is"
OWNER_FILE_USE = "Use this file"
OWNER_FILE_SKIP = "Skip"
OWNER_FILE_USED = "{name}: added {n} item(s) to your plan."
OWNER_FILE_NOTED = "{name}: noted. It doesn't change the forecast."
OWNER_FILE_AI = (
    "We weren't sure from the column titles; our assistant suggested this kind (it saw only the titles)."
)
OWNER_FILE_ALREADY = "{n} of these are already in your plan and won't be added twice."
OWNER_FILES_USED_LIST = "Files you've added: {names}"
OWNER_COLUMN_PICK = "Which column has the {role}?"
OWNER_SKIPPED = "{n} row(s) skipped: we couldn't read their date or amount."
OWNER_TOTAL_ROWS = "{n} total row(s) left out (they add up the others)."
OWNER_ROLE_NAMES = {
    "date": "date", "due": "due date", "issued": "issue date", "label": "description", "payee": "supplier",
    "customer": "customer", "invoice": "invoice number", "amount": "amount", "type": "in/out type",
    "name": "name", "pay": "pay", "position": "position", "account": "account code", "item": "item",
    "quantity": "quantity", "unit_cost": "unit cost", "reorder": "reorder level",
}  # fmt: skip
OWNER_KIND_NAMES = {
    "upcoming_payments": "Upcoming payments",
    "receivables": "Money customers owe you",
    "employees": "Employee list",
    "ledger": "Accounting ledger",
    "inventory": "Inventory",
}
OWNER_SUMMARY = {
    "upcoming_payments": (
        "{rows} payment(s) or income: {n_in} coming in, {n_out} going out, {first} to {last}. "
        "{past} already past are left out."
    ),
    "receivables": (
        "{rows} invoice(s), {total} owed to you. {overdue} overdue: the ones up to 60 days late are counted "
        "as a maybe in two weeks; {doubtful} older than that are listed but not counted."
    ),
    "employees": (
        "{rows} people, {total} {period} (about {per_month} a month). The payroll in your statement is about "
        "{found} a month. Payroll is already in the forecast from your statement, so this file adds nothing to it."
    ),
    "employees_mismatch": (
        "These don't match by more than 10%. Did someone join or leave, or is part of the pay made another way?"
    ),
    "ledger": (
        "{rows} line(s), balance {total}. Not added to the forecast: this money already shows in your bank "
        "statement."
    ),
    "inventory": "{rows} item(s) worth {total} at cost. {low} below their reorder level{names}.",
}
CATEGORY_NAMES = {
    "sales": "Sales",
    "other_income": "Other income",
    "payroll": "Payroll",
    "owner_pay": "Owner's pay",
    "rent": "Rent",
    "utilities": "Utilities",
    "suppliers": "Suppliers",
    "taxes": "Taxes",
    "loan": "Loan",
    "equipment": "Equipment",
    "bank_fees": "Bank fees",
    "other": "Other",
    "transfer_internal": "Between your accounts",
    "card_payment": "Credit card payment",
}
ACCOUNT_KIND = {"bank": "bank account", "card": "credit card"}
CARD_OWED = "owed {amount}"
CARD_NOT_CASH = "A credit card's balance is money you owe, so it isn't counted as cash."
TRANSFERS_FOUND = (
    "We found {n} transfer(s) between your own accounts. They aren't counted as income or spending."
)
CARD_PAYMENTS_FOUND = (
    "Paying your credit card from the bank isn't counted as spending: the card's purchases already are."
)
BALANCE_BREAKS_IN_FILE = (
    "In {file}, the Balance column doesn't add up in {n} place(s), starting {date}. "
    "Some lines may be missing from that file, so check it before trusting the numbers."
)
JUST_SAY_IT = "Anything coming up? Just say it"
JUST_SAY_IT_PLACEHOLDER = (
    "For example: I'm buying a new oven for $7,500 on Nov 14. A customer owes me $3,200, due Dec 1."
)
JUST_SAY_IT_HELP = (
    "Write it the way you'd tell a friend. We'll show you what we understood before anything is added."
)
READ_IT = "Read it"
READING_IT = "Reading what you wrote…"
NOTHING_UNDERSTOOD = (
    'We couldn\'t find a payment or income in that. Try with the amount and the day, like "$1,650 on Dec 2".'
)
PROPOSAL_INTRO = "Here's what we understood. Fix anything that's off, then press Add."
ADD_TO_PLAN = "Add to my plan"
PLAN_ITEMS_ADDED = "Added {n} item(s) to your plan. The forecast now counts on them."
ADD_PROBLEM = "Not added yet. {problem}"
PROPOSAL_COLUMNS = {
    "label": "What",
    "direction": "In or out",
    "amount": "Amount ($)",
    "due_date": "Date",
    "repeats": "Repeats",
    "maybe": "Not sure yet",
}
DIRECTION_NAMES = {"in": "Coming in", "out": "Going out"}
PLANNED_TITLE = "What we're counting on"
PLANNED_MOVED = (
    "Your regular payments, one-offs and anything you tell us now live on one page, where you can change "
    "them and see what each change does."
)
STATEMENT_UP_TO = "Based on your statement up to {end}."
STATEMENT_BEHIND = (
    "Your statement ends on {end}, so the forecast starts on {start}. "
    "Anything that happened after that isn't counted yet."
)
STATEMENT_OLD = (
    "Your statement ends on {end}, {days} days ago, so the forecast starts on {start}. "
    "Upload a newer statement for a forecast that starts today."
)
BALANCE_BREAKS = (
    "The Balance column of your statement doesn't add up in {n} place(s), starting {date}. "
    "Some lines may be missing from the file, so check it before trusting the numbers."
)
SKIPPED_ROWS = "{n} row(s) of your statement had a date or amount we couldn't read, so we left them out. Check the file if that seems wrong."

DASHBOARD_TITLE = "Dashboard"
CURRENT_CASH = "Current cash"
AVAILABLE_TODAY = "Available today"
ON_STATEMENT_DAY = "On {end}, the last day of your statement"
CHART_FORECAST_STARTS = "Forecast starts"
LOWEST_PROJECTED = "Lowest projected"
LOWEST_IS_TODAY = "Today: no lower point ahead"
NEXT_PAYMENT = "Next big payment"
CHART_TITLE = "Cash flow forecast, next 8 weeks"
UPCOMING_ALERTS = "Upcoming alerts"
NO_ALERTS = "No alerts. Your cash looks healthy for the next 8 weeks."
WATCH_NO_ALERTS = (
    "No alerts, but in a bad month your cash could dip to {worst}, below your {line} line. Keep an eye on it."
)
ASK_BOX = "Ask Aheadly"
ASK_PLACEHOLDER = "Ask a question…"

ALERTS_TITLE = "Alerts"
WHY_IT_MATTERS = "Why it matters"
WHAT_YOU_CAN_DO = "What you can do"
TOP_OUTFLOWS = "Top cash outflows in {weeks}"
SEE_WHY = "See why"
TEST_WHAT_IF = "Test a what-if"
DISMISS = "Dismiss"
ALERT_FOOTER = "Plan ahead and take action now to stay on track."

CHAT_TITLE = "Ask Aheadly"
CHAT_INTRO = "Ask about your balance, what's coming, or test a decision before you make it."
CHAT_SUGGESTIONS = ["How am I doing this month?", "Will I have enough cash next month?"]
MOVE_PAYMENT_QUESTION = "What if I move the {name} payment to next month?"
SPEND_QUESTION = "What if I spend $2,000 next week?"
CHAT_INPUT = "Ask in your own words…"
CHAT_THINKING = "Looking at your numbers…"
FALLBACK_NOTE = "Built directly from your numbers (the assistant's wording was not used this time)."
CLEAR_CHAT = "Clear conversation"

WHATIF_TITLE = "What-if"
WHATIF_INTRO = "Model a purchase or a change before you decide. Same engine as the chat."
WHATIF_TYPES = {
    "Buy something": "one_time_expense",
    "Move a payment": "move_item",
    "Change sales": "revenue_change",
}
RUN_SCENARIO = "Run scenario"
SAVE_PLAN = "Save as my plan"
PLAN_SAVED = "Plan saved. You're on track."
BEST_CASE, BASE_CASE, WORST_CASE = "Best case", "Base case", "Worst case"
LOWEST_BALANCE = "lowest balance"
CHANCE_SCENARIO = "With this change: {after} in the next 8 weeks (today: {before}%)."

SETTINGS_TITLE = "Settings"
LOW_CASH_LINE = "Low cash line"
LOW_CASH_HELP = "Your safety buffer. Below this line Aheadly warns you."
RUN_CHECK = "Run today's check"
RESET_DEMO = "Start over"
BACKTEST = "Compare forecast models (backtest)"


# ---------------------------------------------------------------- how we built your forecast (2.6)
BASIS_TITLE = "How we built your forecast"
BASIS_INTRO = (
    "Everything the forecast counts on, in one place. Change anything that's wrong and you'll see "
    "what it does to your lowest balance."
)
BASIS_LINK = "How we built this forecast"
BASIS_START = "Where it starts"
BASIS_START_ROWS = {
    "balance": "Cash on the statement's last day",
    "statement": "Statement up to",
    "history": "History we learned from",
    "lines": "Transactions read",
    "accounts": "Accounts",
}
BASIS_UNIDENTIFIED = "{n} transactions have no clear description; they still count in your normal week."
BASIS_RHYTHM = "Your normal week"
BASIS_RHYTHM_BODY = (
    "Apart from the payments listed below, money in is usually **{in_low} to {in_high}** a week and money "
    "out **{out_low} to {out_high}** a week (the middle half of your last {weeks} weeks). "
    "{busiest} is your busiest day for money in, {slowest} the slowest. The forecast repeats this rhythm, "
    "with the ups and downs your past weeks had."
)
BASIS_REGULAR = "Regular payments"
BASIS_REGULAR_HELP = (
    "Each one goes on its own dates. ≈ means the amount varies; we use a typical recent amount."
)
BASIS_ONE_OFFS = "One-off payments"
BASIS_ONE_OFFS_HELP = "Things you told us about, from your files, or added below."
BASIS_NO_ONE_OFFS = "None yet. Tell us below about anything coming up."
BADGES = {
    "statement": "Found in your statement",
    "confirmed": "Confirmed by you",
    "file": "From your file",
    "owner": "Added by you",
    "example": "Part of the example",
}
BASIS_COLUMNS = {
    "label": "What",
    "amount": "Amount",
    "how_often": "How often",
    "next": "Next",
    "badge": "Where it comes from",
    "note": "Note",
}
BASIS_PAUSED = "Paused"
BASIS_ENDS = "Ends {date}"
BASIS_MAYBE = "Maybe: counted in 3 of 4 scenarios"
BASIS_EDIT = "Change a payment"
BASIS_PICK = "Which one?"
BASIS_AMOUNT = "Amount"
BASIS_NEXT_DATE = "Date"
BASIS_HAS_END = "It stops on a date"
BASIS_END_DATE = "Last date (used only if it stops)"
BASIS_SAVE = "Save changes"
BASIS_PAUSE = "Pause"
BASIS_RESUME = "Resume"
BASIS_REMOVE = "Remove"
BASIS_LOOKS_RIGHT = "Looks right"
BASIS_CONFIRMED = "Marked as confirmed. It won't be changed by a new upload."
BASIS_EFFECT = "{what}. Lowest balance: {before} → {after}."
BASIS_RISK_CHANGED = " Your status went from {before} to {after}."
RISK_NAMES = {"act_now": "act now", "watch": "watch", "safe": "on track"}
BASIS_SAVED = "Saved {label}"
BASIS_PAUSED_DONE = "Paused {label}"
BASIS_RESUMED_DONE = "{label} counts again"
BASIS_REMOVED_DONE = "Removed {label}"
BASIS_PAST_DUE = "{label} ({amount}) was due {date}. Did it happen?"
BASIS_HAPPENED = "Yes, it happened"
BASIS_NOT_YET = "Not yet: move it a week"
BASIS_SUGGESTION = (
    "{label}: your statement shows {found} lately, you set {planned}. Use the statement's amount?"
)
BASIS_USE_FOUND = "Use {found}"
BASIS_NOT_COUNTED = "What we're not counting on"
BASIS_OWN_MOVES = "{n} moves between your own accounts (not income or spending)"
BASIS_CARD_PAYMENTS = "{n} credit card payments (the card purchases already count)"
BASIS_SOME_MONTHS = "Only some months of the year, so not repeated: {labels}"
BASIS_PAUSED_LIST = "Paused by you: {labels}"
BASIS_SWITCHED_OFF = {"removed": "Removed by you", "doubtful": "Too old to count on"}
BASIS_NOTHING_LEFT_OUT = "Nothing left out."
BASIS_NEXT_MONTH = "{month} at a glance"
BASIS_NEXT_MONTH_ROWS = {
    "rhythm": "Your normal weeks",
    "recurring_in": "Regular money in",
    "recurring_out": "Regular payments",
    "one_off_in": "One-off money in",
    "one_off_out": "One-off payments",
    "total": "Net change in cash",
}
BASIS_MAYBE_NOTE = "Plus {amount} of maybe money in, counted only in some scenarios."
BASIS_PARTIAL_MONTH = "The forecast reaches {last}, so this covers {first} to {last}."


# ---------------------------------------------------------------- onboarding questions (2.7)
QUESTIONS_TITLE = "A few questions"
QUESTIONS_INTRO = (
    "We already read your statement. These are the things it can't tell us. Every question is optional, "
    "and you can stop and come back."
)
QUESTIONS_PROGRESS = "{done} of {total} answered"
QUESTIONS_DONE = "That's everything for now. The forecast uses your answers."
QUESTIONS_BANNER = "{n} quick question(s) will make your forecast better."
QUESTIONS_GO = "Answer them"
QUESTIONS_EXAMPLE = (
    "This is the example business, so its owner's answers are filled in. Change anything you like."
)
WHY_LABEL = "Why we ask: "
SAVE_ANSWER = "Save"
SKIP = "Skip"
BUSINESS_TYPE = "What does your business do?"
BUSINESS_TYPE_PLACEHOLDER = "For example: a bakery, a hardware store, a design studio"
CUSTOMERS_PAY = "How do your customers pay you?"
CUSTOMERS_PAY_PLACEHOLDER = (
    "For example: card every day; two cafés pay weekly by transfer; some invoices at 30 days"
)
BUSY_MONTHS = "Busy months"
SLOW_MONTHS = "Slow months"
SEASON_FOUND = "Last {month}, {pct} {more_less} money came in than in a normal month."
SEASON_DISAGREES = (
    "Last {month}, {pct} {more_less} money came in than in a normal month, so we won't change the forecast "
    "unless you type your own estimate."
)
SEASON_NOT_IN_STATEMENT = "Your statement doesn't cover a {month} yet. How different is it, roughly?"
SEASON_ESTIMATE = "{month}: % more (+) or less (−) money in than a normal month"
SEASON_HOW = (
    "A slow month lowers every scenario. A busy month's extra money mostly raises the best case: the main "
    "forecast counts on only a little of it repeating."
)
SEASONS_TITLE = "Busy and slow months"
SEASONS_NONE = "You haven't told us about busy or slow months, so every month is treated alike."
SEASONS_USED = "{month} ({kind}): {pct}"
SEASONS_CHANGE = "Change busy and slow months"
SEASONS_SAVED = "Saved. The forecast uses your busy and slow months."
OWNER_PAY_YES = "Yes, that's my pay"
OWNER_PAY_NO = "No"
MYSTERY_GUESS = "Our guess: **{category}**. {reason}"
MYSTERY_PICK = "What kind of payment is it?"
MYSTERY_NOT_SURE = "Pick one"
MYSTERY_WORDS = "Or say what it is in your own words"
MYSTERY_WORDS_PLACEHOLDER = "For example: my accountant's monthly fee"
MYSTERY_SAVED = "Saved: {payee} is now {category}, in past and future statements."
NOTHING_ELSE = "Nothing else for now"


# ---------------------------------------------------------------- forecast confidence (2.8)
CONFIDENCE_TITLE = "How much to trust this forecast: {level}"
CONFIDENCE_LEVELS = {"high": "high", "medium": "medium", "low": "low"}
CONFIDENCE_ALL = "All the checks"
NOTHING_PLANNED = "This forecast assumes no big one-off payments in the next 8 weeks. Planning any?"
NOTHING_PLANNED_GO = "Tell us"


# ---------------------------------------------------------------- chance below the line (3.1)
def chance_words(pct: int | None) -> str:
    """64 → '64% chance of dipping below your line' (empty when there's no chance to show)."""
    if pct is None:
        return ""
    if pct <= 0:
        return "no scenario dips below your line"
    if pct >= 100:
        return "every scenario dips below your line"
    return f"{pct}% chance of dipping below your line"


# ---------------------------------------------------------------- actions (3.2)
ACTIONS_TITLE = "Try one"
ACTION_IMPACT = "Lowest balance {before} → {after} · {risk_before} → {risk_after} · chance of dipping below your line {chance_before}% → {chance_after}%"
ACTION_TEST = "Test this"
ACTION_HOW = "How to do it"
ACTION_DRAFT = "Draft a message"
ACTION_DRAFT_NOTE = "Copy it and send it yourself: Aheadly never sends messages."
ACTION_SAVED = "Plan saved. The forecast and alerts now use it."
ACTION_AFTER = "Lowest balance after: {after}"
STILL_SHORT = "Even the best change here leaves your base case about {gap} below your line. Covering that may need money from outside the business: talk to your bank or accountant."
WATCH_FIXES = "Your base case stays above your line, but a bad month could dip below it. These changes, tested on your numbers, would help."
SEE_FIXES = "See what would help"
ACTION_GENERAL = "General advice: we couldn't test this one for you."
