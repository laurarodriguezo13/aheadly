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
    "Connect your accounts once and Aheadly checks your money every time you open it, "
    "warns you weeks before cash runs low, and answers your questions in plain words."
)
CONNECT_BANK = "Connect bank (Plaid sandbox)"
CONNECT_QBO = "Connect QuickBooks"
USE_DEMO = "Use demo data"
CONNECT_LATER = "Connect later: no sandbox keys found. Demo data works without any keys."
ALL_SET = "All set. We'll check your money every time you open Aheadly."
NOT_CONNECTED = "No data yet. Go to **Accounts** and choose a data source to get started."

DASHBOARD_TITLE = "Dashboard"
CURRENT_CASH = "Current cash"
AVAILABLE_TODAY = "Available today"
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
CHAT_SUGGESTIONS = [
    "How am I doing this month?",
    "Will I have enough cash next month?",
    "What if I buy the new oven next month instead?",
]
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
RESET_DEMO = "Reset demo"
BACKTEST = "Compare forecast models (backtest)"
