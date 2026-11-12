"""All user-facing strings (English for the MVP; es-CO can be added here later)."""

APP_NAME = "Aheadly"
TAGLINE = "Clarity today. A brighter tomorrow."

NAV = {
    "dashboard": "Dashboard",
    "alerts": "Alerts",
    "ask": "Ask Aheadly",
    "whatif": "What-if",
    "accounts": "Accounts",
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
RECURRING_TITLE = "Regular payments and income we found ({n})"
RECURRING_HELP = (
    'Found in your statement. "On its dates": the forecast puts it on the day it\'s due (rent on the '
    '15th, payroll on Fridays). "In the daily pattern": it changes too much from one time to the next '
    "(card sales, weekly supplier orders), so the forecast learns it with the rest of your daily ups and downs. "
    "≈ means the amount varies; we use a typical recent amount."
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
PLANNED_HELP = (
    "These upcoming payments and income come from your upcoming-payments file, what you tell us below, "
    "and any plan you save. "
    "Regular payments like payroll and rent are learned from your statement, so they are not listed here."
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

SETTINGS_TITLE = "Settings"
LOW_CASH_LINE = "Low cash line"
LOW_CASH_HELP = "Your safety buffer. Below this line Aheadly warns you."
RUN_CHECK = "Run today's check"
RESET_DEMO = "Start over"
BACKTEST = "Compare forecast models (backtest)"
