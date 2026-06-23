import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS grants(
  funder_ein TEXT, funder_name TEXT, funder_type TEXT,
  recipient_name TEXT, recipient_ein TEXT, recipient_city TEXT, recipient_state TEXT,
  purpose TEXT, amount INTEGER, source TEXT, tax_year INTEGER, resolved_score REAL
);
CREATE TABLE IF NOT EXISTS orgs(
  ein TEXT PRIMARY KEY, name TEXT, ntee TEXT, city TEXT, state TEXT,
  asset_amt INTEGER, income_amt INTEGER, revenue_amt INTEGER,
  foundation_code TEXT, subsection TEXT
);
"""


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path):
    conn = connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def create_indexes(conn):
    conn.execute("CREATE INDEX IF NOT EXISTS idx_grants_rein ON grants(recipient_ein)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orgs_state_name ON orgs(state, name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orgs_ntee ON orgs(ntee)")
    conn.commit()
