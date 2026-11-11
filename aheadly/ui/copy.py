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
UPLOAD_TITLE = "Upload your bank statement"
UPLOAD_HELP = (
    "A CSV or Excel export from your bank with Date, Description and Amount (or Debit and Credit). "
    "If it has a Balance column, we read your current balance from it."
)
BUSINESS_NAME = "Business name"
OWNER_NAME = "Your name (optional)"
STATEMENT_FILE = "Bank statement (CSV or Excel)"
UPCOMING_FILE = "Upcoming payments (optional, CSV or Excel)"
UPCOMING_HELP = (
    "Only one-off things your bank can't know yet: a planned purchase, a big supplier order, a customer "
    "payment you expect. Columns: Date, Description, Amount (minus for money going out). Regular payments "
    "like payroll and rent are learned from your statement, so don't list them here."
)
LOW_CASH_LINE_INPUT = "Lowest balance you're comfortable with ($)"
BALANCE_INPUT = "Current balance ($)"
BALANCE_PLACEHOLDER = "Read from the statement"
UPLOAD_BUTTON = "Upload and analyse"
UPLOAD_SPINNER = "Reading your statement and building your forecast…"
UPLOAD_FAILED = "We couldn't read that file: {error}"
PLANNED_TITLE = "What we're counting on"
PLANNED_HELP = (
    "These upcoming payments and income come from your upcoming-payments file and any plan you save. "
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
