-- Aheadly SQLite schema (matches AHEADLY_APP_SPEC.md section 5, see DECISIONS.md for additions)
CREATE TABLE IF NOT EXISTS businesses (
  id INTEGER PRIMARY KEY, name TEXT, owner_name TEXT, city TEXT,
  currency TEXT DEFAULT 'USD', low_cash_line REAL DEFAULT 2000,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS accounts (
  id INTEGER PRIMARY KEY, business_id INTEGER REFERENCES businesses(id),
  source TEXT CHECK (source IN ('plaid','quickbooks','demo','csv')),
  name TEXT, external_id TEXT, access_token_enc TEXT,
  balance REAL DEFAULT 0, last_synced_at TEXT);

CREATE TABLE IF NOT EXISTS transactions (
  id INTEGER PRIMARY KEY, business_id INTEGER, account_id INTEGER,
  external_id TEXT UNIQUE, date TEXT NOT NULL, amount REAL NOT NULL,
  description TEXT, category TEXT, counterparty TEXT, source TEXT);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(business_id, date);

CREATE TABLE IF NOT EXISTS scheduled_items (
  id INTEGER PRIMARY KEY, business_id INTEGER,
  kind TEXT CHECK (kind IN ('bill','payroll','rent','receivable','planned_purchase','other')),
  label TEXT, amount REAL NOT NULL, due_date TEXT, recurrence TEXT,
  source TEXT, active INTEGER DEFAULT 1);

CREATE TABLE IF NOT EXISTS forecast_runs (
  id INTEGER PRIMARY KEY, business_id INTEGER, run_at TEXT, horizon_days INTEGER,
  model TEXT, scenario_id INTEGER NULL, opening_balance REAL,
  min_p50 REAL, min_p50_date TEXT, min_p10 REAL, min_p90 REAL);

CREATE TABLE IF NOT EXISTS forecast_points (
  run_id INTEGER REFERENCES forecast_runs(id), date TEXT,
  balance_p10 REAL, balance_p50 REAL, balance_p90 REAL, net_flow_p50 REAL,
  PRIMARY KEY (run_id, date));

CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY, business_id INTEGER, run_id INTEGER,
  type TEXT CHECK (type IN ('shortfall','idle_cash')),
  severity TEXT, weeks_ahead INTEGER, facts_json TEXT,
  title TEXT, body TEXT, actions_json TEXT, created_at TEXT, read_at TEXT,
  dismissed INTEGER DEFAULT 0, resolved INTEGER DEFAULT 0);

CREATE TABLE IF NOT EXISTS scenarios (
  id INTEGER PRIMARY KEY, business_id INTEGER, name TEXT, adjustments_json TEXT,
  created_at TEXT, result_json TEXT, saved_as_plan INTEGER DEFAULT 0);

CREATE TABLE IF NOT EXISTS chat_messages (
  id INTEGER PRIMARY KEY, business_id INTEGER, role TEXT, content TEXT,
  tool_calls_json TEXT, created_at TEXT);
